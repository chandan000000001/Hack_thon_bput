"""OpenRouter chat-completions client.

Calls OpenRouter with a strict-JSON instruction and never raises: any
failure (missing key, timeout, bad response, unparseable output) falls
back to a generic explanation so the heuristic score and alert flow
still work without the LLM.
"""

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("cyberguard.openrouter")

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 15
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


async def call_openrouter(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call OpenRouter chat completions and return a structured dict.

    Returns FALLBACK_LLM_OUTPUT if the API key is missing, the request
    times out, or the response cannot be parsed as JSON.
    """
    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY is not configured; using fallback explanation")
        return dict(FALLBACK_LLM_OUTPUT)

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
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS)) as client:
            response = await client.post(OPENROUTER_CHAT_URL, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("OpenRouter request failed; using fallback explanation")
        return dict(FALLBACK_LLM_OUTPUT)

    parsed = _parse_llm_content(content)
    if parsed is None:
        logger.warning("OpenRouter returned unparseable content; using fallback explanation")
        return dict(FALLBACK_LLM_OUTPUT)
    return parsed
