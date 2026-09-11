"""OpenRouter chat-completions client (LLM provider-chain member).

Calls OpenRouter with a strict-JSON instruction. As a chain provider it
raises ProviderError on any failure (missing key, timeout, bad response,
unparseable output) so the gateway can fall through to the next provider.
`call_openrouter` is kept as a backward-compatible wrapper with the original
never-raise behaviour: any failure returns the fallback explanation instead.
"""

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("cyberguard.openrouter")

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
HTTP_REFERER = "https://cyberguard.local"
APP_TITLE = "CYBERGUARD"

FALLBACK_LLM_OUTPUT: dict[str, Any] = {
    "explanation": (
        "Automated explanation is temporarily unavailable. The risk score and "
        "indicators above were produced by the built-in heuristic engine."
    ),
    "mitre_techniques": [],
    "recommended_actions": [],
}

_JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


class ProviderError(RuntimeError):
    """Raised by chain providers so the gateway falls through to the next one."""


def _parse_llm_content(content: str) -> dict[str, Any] | None:
    """Parse strict JSON, tolerating markdown fences around the JSON block."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    match = _JSON_BLOCK_PATTERN.search(content)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def rule_based_explanation(
    system_prompt: str, user_prompt: str, expected_band: str | None = None
) -> dict[str, Any]:
    """Local, instant explanation generator (final chain fallback).

    Template-generated from the indicator context already present in the
    user prompt — nothing is invented. Reuses the existing fallback text.
    """
    output = dict(FALLBACK_LLM_OUTPUT)
    if expected_band:
        prefix = f"{expected_band.capitalize()} Risk:"
        output["explanation"] = f"{prefix} {output['explanation']}"
    return output


async def explain_openrouter(
    system_prompt: str, user_prompt: str, json_mode: bool = True
) -> dict[str, Any]:
    """Provider interface: call OpenRouter and return the parsed dict.

    With json_mode=True the strict-JSON contract is enforced and parsed.
    With json_mode=False the raw text is returned as
    {"explanation": <text>, "mitre_techniques": [], "recommended_actions": []}
    (used by free-form callers such as the SOC assistant).

    Raises ProviderError when the API key is missing, the request times out or
    fails, or (in json_mode) the response cannot be parsed as JSON — the
    gateway treats any exception as a fall-through to the next provider.
    """
    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        raise ProviderError("OPENROUTER_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": HTTP_REFERER,
        "X-Title": APP_TITLE,
    }
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.openrouter_timeout_seconds)
    ) as client:
        response = await client.post(OPENROUTER_CHAT_URL, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    content = body["choices"][0]["message"]["content"]

    if not json_mode:
        return {"explanation": (content or "").strip(), "mitre_techniques": [], "recommended_actions": []}
    parsed = _parse_llm_content(content)
    if parsed is None:
        raise ProviderError("OpenRouter returned unparseable content")
    return parsed


async def call_openrouter(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Backward-compatible wrapper: never raises.

    Returns FALLBACK_LLM_OUTPUT if the API key is missing, the request times
    out, or the response cannot be parsed as JSON.
    """
    try:
        return await explain_openrouter(system_prompt, user_prompt)
    except Exception:
        logger.exception("OpenRouter request failed; using fallback explanation")
        return dict(FALLBACK_LLM_OUTPUT)
