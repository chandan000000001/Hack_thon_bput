"""LLM provider gateway with a circuit-breaker-guarded fallback chain.

Chain order (strict — fastest provider first):
    1. Groq        — settings.groq_timeout_seconds      (default 15 s)
    2. OpenRouter  — settings.openrouter_timeout_seconds (default 20 s)
    3. rule_based  — local template built from the indicator context,
                     instant and never fails

Each remote provider is wrapped in its own AsyncCircuitBreaker (threshold 3
consecutive failures, 60 s recovery window). When a breaker is OPEN the
gateway logs one line and immediately falls through to the next provider
without waiting — an LLM outage can never hang the API. Non-open failures
(timeout, bad response, unparseable output) are counted against the breaker
and also fall through.

Results are cached in explanation_cache (TTL 3600 s, max 256 entries) keyed by
a sha256 of the module name plus normalized input, so identical inputs skip
the remote chain entirely.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.ai import explanation_cache as cache
from app.ai.async_circuit_breaker import AsyncCircuitBreaker, CircuitBreakerOpenError
from app.ai.groq_client import explain_groq
from app.ai.openrouter_client import explain_openrouter, rule_based_explanation
from app.core.calibration import get_explanation_calibration

logger = logging.getLogger("cyberguard.llm_gateway")

PROVIDERS: list[tuple[str, Callable[[str, str], Awaitable[dict[str, Any]]]]] = [
    ("groq", explain_groq),
    ("openrouter", explain_openrouter),
]

BREAKER_FAILURE_THRESHOLD = 3
BREAKER_RECOVERY_TIMEOUT_SECONDS = 60.0

# One breaker per remote provider, shared across requests so outage state
# survives between calls.
_BREAKERS: dict[str, AsyncCircuitBreaker] = {
    name: AsyncCircuitBreaker(
        failure_threshold=BREAKER_FAILURE_THRESHOLD,
        recovery_timeout=BREAKER_RECOVERY_TIMEOUT_SECONDS,
        name=f"llm:{name}",
    )
    for name, _ in PROVIDERS
}

LEADING_BAND_PATTERN = re.compile(
    r"^(?:\*{1,2}|#+\s*)?[<\[]?([A-Za-z]+)[>\]]?\s+Risk\s*:(?:\*{1,2})?\s*", re.IGNORECASE
)


def parse_leading_band(text: str) -> str | None:
    """Extract leading band from '<Band> Risk:' if present."""
    if not text:
        return None
    match = LEADING_BAND_PATTERN.match(text.strip())
    if match:
        return match.group(1).lower()
    return None


def enforce_leading_band(text: str, expected_band: str) -> str:
    """Server-side replace or prepend '<Band> Risk:' on the explanation text."""
    expected_token = f"{expected_band.capitalize()} Risk:"
    stripped = text.strip()
    match = LEADING_BAND_PATTERN.match(stripped)
    if match:
        return LEADING_BAND_PATTERN.sub(f"{expected_token} ", stripped, count=1)
    return f"{expected_token} {stripped}"


def _validate_explanation_band(
    output: Any, expected_band: str | None
) -> tuple[bool, Any]:
    """Check if output has matching leading band. Returns (is_valid, cleaned_output)."""
    if not expected_band:
        return True, output

    if isinstance(output, dict):
        exp = str(output.get("explanation") or "")
        parsed = parse_leading_band(exp)
        if parsed == expected_band.lower():
            cleaned = LEADING_BAND_PATTERN.sub(f"{expected_band.capitalize()} Risk: ", exp.strip(), count=1)
            updated = dict(output)
            updated["explanation"] = cleaned
            return True, updated
        return False, output

    exp = str(output or "")
    parsed = parse_leading_band(exp)
    if parsed == expected_band.lower():
        cleaned = LEADING_BAND_PATTERN.sub(f"{expected_band.capitalize()} Risk: ", exp.strip(), count=1)
        return True, cleaned
    return False, output


def _apply_server_side_fix(output: Any, expected_band: str | None) -> Any:
    """Enforce the leading band token on output."""
    if not expected_band:
        return output
    if isinstance(output, dict):
        updated = dict(output)
        exp = str(output.get("explanation") or "")
        updated["explanation"] = enforce_leading_band(exp, expected_band)
        return updated
    return enforce_leading_band(str(output or ""), expected_band)


def _normalize(value: Any) -> Any:
    """Lowercase/collapse strings and sort mappings so equivalent inputs
    produce the same cache key."""
    if isinstance(value, str):
        return " ".join(value.split()).strip().lower()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def make_cache_key(module: str, raw_data: Any) -> str:
    """Stable sha256 cache key: module name + normalized structured input."""
    normalized = json.dumps(_normalize(raw_data), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{module}|{normalized}".encode()).hexdigest()


def make_cache_key_from_bytes(module: str, data: bytes) -> str:
    """Stable sha256 cache key for binary input (e.g. uploaded media bytes)."""
    return hashlib.sha256(module.encode() + b"|" + data).hexdigest()


def _looks_like_timeout(exc: Exception) -> bool:
    """True when a provider failure was caused by a timeout."""
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
        return True
    return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


def _chain_telemetry(outcomes: dict[str, tuple[str, int]], final_provider: str) -> None:
    """Emit the one-line per-call chain telemetry.

    Exact form: LLM chain: groq=<outcome>,<ms> openrouter=<outcome>,<ms>
    final=<provider>. <outcome> is status | timeout | breaker-open | error |
    skipped — skipped,0ms marks a provider the chain never reached; cache hits
    report final=cache:<original_provider>.
    """
    slots = []
    for name in ("groq", "openrouter"):
        outcome, ms = outcomes.get(name, ("skipped", 0))
        slots.append(f"{name}={outcome},{ms}")
    logger.info("LLM chain: %s final=%s", " ".join(slots), final_provider)


async def explain(
    module: str,
    system_prompt: str,
    user_prompt: str,
    cache_key: str,
    json_mode: bool = True,
    expected_band: str | None = None,
    risk_score: int | None = None,
) -> dict[str, Any]:
    """Explain a detection through the provider chain with band consistency.

    json_mode=True enforces the strict-JSON analysis contract; json_mode=False
    (used by the SOC assistant) returns the raw model text wrapped as
    {"explanation": <text>, ...} while still inheriting the chain order,
    circuit breakers and cache.

    If expected_band is provided:
        1. Validates that output starts with '<Band> Risk:'.
        2. On mismatch, retries once with a correction note.
        3. If still mismatched, server-side replaces the leading band token.

    Returns {"explanation": <parsed contract dict or raw text>,
             "provider": "groq" | "openrouter" | "rule_based" | "cache:<orig>",
             "latency_ms": <int>}.
    """
    full_cache_key = f"{cache_key}|band={expected_band}|score={risk_score}|json={json_mode}"
    cached = cache.get(full_cache_key)
    if cached is not None:
        cached_output = cached["output"]
        if expected_band:
            valid, cached_output = _validate_explanation_band(cached_output, expected_band)
            if not valid:
                cached_output = _apply_server_side_fix(cached_output, expected_band)
        _chain_telemetry({}, f"cache:{cached['provider']}")
        return {
            "explanation": cached_output,
            "provider": f"cache:{cached['provider']}",
            "latency_ms": 0,
        }

    # Per-provider outcome for the chain telemetry line:
    # (status | timeout | breaker-open | error, total milliseconds spent).
    outcomes: dict[str, tuple[str, int]] = {}

    for provider_name, provider in PROVIDERS:
        breaker = _BREAKERS[provider_name]
        started = time.perf_counter()
        try:
            output = await breaker.call(provider, system_prompt, user_prompt, json_mode=json_mode)
        except CircuitBreakerOpenError:
            outcomes[provider_name] = ("breaker-open", int((time.perf_counter() - started) * 1000))
            logger.warning(
                "Circuit breaker OPEN for %s, skipping to fallback", provider_name
            )
            continue
        except Exception as exc:  # noqa: BLE001 — any provider failure falls through
            latency_ms = int((time.perf_counter() - started) * 1000)
            outcomes[provider_name] = (
                "timeout" if _looks_like_timeout(exc) else "error",
                latency_ms,
            )
            logger.warning(
                "LLM provider %s failed after %d ms: %s", provider_name, latency_ms, exc
            )
            continue

        latency_ms = int((time.perf_counter() - started) * 1000)
        outcomes[provider_name] = ("status", latency_ms)

        # Validator: check leading band if expected_band is specified
        if expected_band:
            valid, norm_output = _validate_explanation_band(output, expected_band)
            if valid:
                cache.set(full_cache_key, {"output": norm_output, "provider": provider_name})
                _chain_telemetry(outcomes, provider_name)
                return {"explanation": norm_output, "provider": provider_name, "latency_ms": latency_ms}

            # On mismatch: retry once with a correction note
            logger.warning(
                "Leading band mismatch for %s from %s (expected %s); retrying once with correction note",
                module,
                provider_name,
                expected_band,
            )
            score_str = f" ({risk_score}/100)" if risk_score is not None else ""
            correction_note = (
                f"\n\nCORRECTION NOTE: Your previous explanation did not begin with '{expected_band.capitalize()} Risk:' "
                f"or contradicted the final assessed severity of {expected_band.capitalize()} Risk{score_str}. "
                f"You MUST begin your explanation's first sentence with exactly '{expected_band.capitalize()} Risk:' "
                f"and ensure the narrative aligns with this severity level."
            )
            try:
                retry_output = await breaker.call(
                    provider, system_prompt, user_prompt + correction_note, json_mode=json_mode
                )
                valid_retry, norm_retry = _validate_explanation_band(retry_output, expected_band)
                if valid_retry:
                    cache.set(full_cache_key, {"output": norm_retry, "provider": provider_name})
                    _chain_telemetry(outcomes, provider_name)
                    return {"explanation": norm_retry, "provider": provider_name, "latency_ms": latency_ms}

                # Still mismatched after retry: server-side replace the leading band token
                logger.info("Explanation still mismatched after retry; applying server-side token replacement")
                fixed_output = _apply_server_side_fix(retry_output, expected_band)
                cache.set(full_cache_key, {"output": fixed_output, "provider": provider_name})
                _chain_telemetry(outcomes, provider_name)
                return {"explanation": fixed_output, "provider": provider_name, "latency_ms": latency_ms}
            except Exception as retry_exc:
                logger.warning("Retry with correction note failed (%s); applying server-side fix to initial output", retry_exc)
                fixed_output = _apply_server_side_fix(output, expected_band)
                cache.set(full_cache_key, {"output": fixed_output, "provider": provider_name})
                _chain_telemetry(outcomes, provider_name)
                return {"explanation": fixed_output, "provider": provider_name, "latency_ms": latency_ms}

        cache.set(full_cache_key, {"output": output, "provider": provider_name})
        _chain_telemetry(outcomes, provider_name)
        return {"explanation": output, "provider": provider_name, "latency_ms": latency_ms}

    started = time.perf_counter()
    output = rule_based_explanation(system_prompt, user_prompt, expected_band=expected_band)
    if expected_band:
        valid, output = _validate_explanation_band(output, expected_band)
        if not valid:
            output = _apply_server_side_fix(output, expected_band)
    latency_ms = int((time.perf_counter() - started) * 1000)
    logger.warning("LLM providers exhausted; using rule_based explanation")
    cache.set(full_cache_key, {"output": output, "provider": "rule_based"})
    _chain_telemetry(outcomes, "rule_based")
    return {"explanation": output, "provider": "rule_based", "latency_ms": latency_ms}
