"""LLM provider gateway with a circuit-breaker-guarded fallback chain.

Chain order (strict — fastest provider first):
    1. Groq        — settings.groq_timeout_seconds      (default 20 s)
    2. OpenRouter  — settings.openrouter_timeout_seconds (default 60 s)
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

import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.ai import explanation_cache as cache
from app.ai.async_circuit_breaker import AsyncCircuitBreaker, CircuitBreakerOpenError
from app.ai.groq_client import explain_groq
from app.ai.openrouter_client import explain_openrouter, rule_based_explanation

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


async def explain(
    module: str,
    system_prompt: str,
    user_prompt: str,
    cache_key: str,
    json_mode: bool = True,
) -> dict[str, Any]:
    """Explain a detection through the provider chain.

    json_mode=True enforces the strict-JSON analysis contract; json_mode=False
    (used by the SOC assistant) returns the raw model text wrapped as
    {"explanation": <text>, ...} while still inheriting the chain order,
    circuit breakers and cache.

    Returns {"explanation": <parsed contract dict or raw text>,
             "provider": "groq" | "openrouter" | "rule_based" | "cache:<orig>",
             "latency_ms": <int>}.
    """
    cache_key = f"{cache_key}|json={json_mode}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {
            "explanation": cached["output"],
            "provider": f"cache:{cached['provider']}",
            "latency_ms": 0,
        }

    for provider_name, provider in PROVIDERS:
        breaker = _BREAKERS[provider_name]
        started = time.perf_counter()
        try:
            output = await breaker.call(provider, system_prompt, user_prompt, json_mode=json_mode)
        except CircuitBreakerOpenError:
            logger.warning(
                "Circuit breaker OPEN for %s, skipping to fallback", provider_name
            )
            continue
        except Exception as exc:  # noqa: BLE001 — any provider failure falls through
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "LLM provider %s failed after %d ms: %s", provider_name, latency_ms, exc
            )
            continue
        latency_ms = int((time.perf_counter() - started) * 1000)
        cache.set(cache_key, {"output": output, "provider": provider_name})
        return {"explanation": output, "provider": provider_name, "latency_ms": latency_ms}

    started = time.perf_counter()
    output = rule_based_explanation(system_prompt, user_prompt)
    latency_ms = int((time.perf_counter() - started) * 1000)
    logger.warning("LLM providers exhausted; using rule_based explanation")
    cache.set(cache_key, {"output": output, "provider": "rule_based"})
    return {"explanation": output, "provider": "rule_based", "latency_ms": latency_ms}
