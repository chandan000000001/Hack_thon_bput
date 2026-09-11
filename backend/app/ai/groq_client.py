"""Groq chat-completions provider (OpenAI-compatible endpoint).

Provider-interface client for the CYBERGUARD LLM fallback chain: raises
ProviderError on any failure (missing key, timeout, bad response, unparseable
output) so the gateway can move on to the next provider immediately.
Message format and strict-JSON parsing are identical to openrouter_client.
"""

import asyncio
from typing import Any

import httpx

from app.ai.openrouter_client import ProviderError, _parse_llm_content
from app.core.config import get_settings

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


async def explain_groq(
    system_prompt: str, user_prompt: str, json_mode: bool = True
) -> dict[str, Any]:
    """Call Groq chat completions and return the parsed dict.

    json_mode=True enforces/parses the strict-JSON contract; json_mode=False
    returns the raw text as {"explanation": <text>, ...} for free-form callers
    (e.g. the SOC assistant).

    Raises ProviderError immediately when GROQ_API_KEY is empty so the
    gateway skips to the rule-based provider without wasting time.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise ProviderError("GROQ_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    sys_content = system_prompt
    if json_mode and "json" not in (system_prompt + user_prompt).lower():
        sys_content = f"{system_prompt}\nRespond strictly in valid JSON format."

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_completion_tokens": 1024,
    }
    if "oss" in settings.groq_model or "o1" in settings.groq_model or "o3" in settings.groq_model:
        payload["reasoning_effort"] = "low"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.groq_timeout_seconds)) as client:
            response = await asyncio.wait_for(
                client.post(GROQ_CHAT_URL, headers=headers, json=payload),
                timeout=settings.groq_timeout_seconds,
            )
            if response.status_code == 429:
                await asyncio.sleep(2.0)
                response = await asyncio.wait_for(
                    client.post(GROQ_CHAT_URL, headers=headers, json=payload),
                    timeout=settings.groq_timeout_seconds,
                )
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        raise ProviderError(f"Groq request failed: {exc}") from exc

    content = body["choices"][0]["message"]["content"]
    if not json_mode:
        return {"explanation": (content or "").strip(), "mitre_techniques": [], "recommended_actions": []}
    parsed = _parse_llm_content(content)
    if parsed is None:
        raise ProviderError("Groq returned unparseable content")
    return parsed
