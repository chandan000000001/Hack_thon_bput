"""LLM provider gateway with a timed fallback chain.

Chain order (strict):
    1. OpenRouter  — settings.openrouter_timeout_seconds (default 100 s)
    2. Groq        — settings.groq_timeout_seconds      (default 60 s)
    3. rule_based  — local template built from the indicator context,
                     instant and never fails

Every provider call is timed; on timeout or any exception the gateway logs
one warning line and continues to the next provider. Results are cached in
explanation_cache (TTL 3600 s, max 256 entries) keyed by a sha256 of the
module name plus normalized input, so identical inputs skip the remote chain
entirely. Worst-case added latency is bounded: 100 s + 60 s + <1 s.
"""

import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.ai import explanation_cache as cache
from app.ai.groq_client import explain_groq
from app.ai.openrouter_client import explain_openrouter, rule_based_explanation

logger = logging.getLogger("cyberguard.llm_gateway")

PROVIDERS: list[tuple[str, Callable[[str, str], Awaitable[dict[str, Any]]]]] = [
    ("openrouter", explain_openrouter),
    ("groq", explain_groq),
]


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
    module: str, system_prompt: str, user_prompt: str, cache_key: str
) -> dict[str, Any]:
    """Explain a detection through the provider chain.

    Returns {"explanation": <parsed strict-JSON contract dict>,
             "provider": "openrouter" | "groq" | "rule_based" | "cache:<orig>",
             "latency_ms": <int>}.
    """
    cached = cache.get(cache_key)
    if cached is not None:
        return {
            "explanation": cached["output"],
            "provider": f"cache:{cached['provider']}",
            "latency_ms": 0,
        }

    for provider_name, provider in PROVIDERS:
        started = time.perf_counter()
        try:
            output = await provider(system_prompt, user_prompt)
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
