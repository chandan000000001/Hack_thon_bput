"""SOC assistant chat service (Part 6).

Answers analyst questions using recent alerts as context. The chat reply
is plain text; the OpenRouter call reuses the shared client, which
returns strict JSON, so the assistant asks the model for a single-key
JSON object and extracts the text reply from it.
"""

import logging
from collections import Counter
from typing import Any

from fastapi import HTTPException, status

from app.ai.openrouter_client import call_openrouter
from app.ai.prompt_templates import SOC_ASSISTANT_SYSTEM_PROMPT
from app.core.supabase_client import get_supabase
from app.services import audit_service

logger = logging.getLogger("cyberguard.assistant")

CONTEXT_ALERT_COUNT = 20


def _build_context_summary(alerts: list[dict[str, Any]]) -> str:
    """Build a compact threat context block for the LLM prompt."""
    severity_counts = Counter(alert.get("severity") for alert in alerts)
    module_counts = Counter(alert.get("module") for alert in alerts)
    critical_titles = [
        f"- [{alert['id']}] {alert.get('title')} (module: {alert.get('module')})"
        for alert in alerts
        if alert.get("severity") == "critical"
    ]

    lines = [f"Total recent alerts analyzed: {len(alerts)}"]
    lines.append(
        "Alerts by severity: "
        + ", ".join(f"{name}={count}" for name, count in sorted(severity_counts.items()))
    )
    lines.append(
        "Alerts by module: "
        + ", ".join(f"{name}={count}" for name, count in sorted(module_counts.items()))
    )
    if critical_titles:
        lines.append("Critical alert titles:")
        lines.extend(critical_titles)
    else:
        lines.append("No critical alerts in the recent context.")
    return "\n".join(lines)


async def chat_with_assistant(
    user_message: str, user_id: str = "", user_name: str = ""
) -> dict[str, Any]:
    """Answer an analyst question grounded in recent alert context."""
    try:
        alerts = (
            get_supabase()
            .table("alerts")
            .select("id, title, severity, module, status, created_at")
            .order("created_at", desc=True)
            .limit(CONTEXT_ALERT_COUNT)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load alert context for the assistant",
        ) from exc

    context_summary = _build_context_summary(alerts)
    context_used = [alert["id"] for alert in alerts]

    user_prompt = (
        f"Current threat context:\n{context_summary}\n\n"
        f"Analyst question: {user_message}\n\n"
        "Respond with a strict JSON object with a single key 'reply' "
        "containing your full answer as plain text."
    )

    llm_output = await call_openrouter(SOC_ASSISTANT_SYSTEM_PROMPT, user_prompt)
    reply = str(
        llm_output.get("reply")
        or llm_output.get("explanation")
        or "The assistant is temporarily unable to generate a response. "
        "Please review the alerts directly."
    )

    await audit_service.log_action(
        user_id,
        user_name,
        "SOC Assistant query",
        "assistant",
        user_message[:200],
    )
    return {"reply": reply, "context_used": context_used}
