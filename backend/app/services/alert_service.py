"""Alert persistence service (Part 3).

Writes alerts, recommended actions, and event status transitions to
Supabase using the service role client.
"""

import logging
import uuid
from typing import Any

from fastapi import HTTPException, status

from app.core.supabase_client import get_supabase

logger = logging.getLogger("cyberguard.alerts")

MODULE_DEFAULT_THREAT_TYPES = {
    "phishing": "phishing_email",
    "url": "malicious_url",
}


def _match_catalog_actions(client: Any, recommended_actions: list[str]) -> list[dict]:
    """Map LLM-recommended actions to the seeded response_catalog entries."""
    catalog_rows = (
        client.table("response_catalog")
        .select("id, action, description, automation_level, requires_approval")
        .execute()
        .data
        or []
    )

    mapped: list[dict] = []
    for action in recommended_actions:
        normalized = str(action).strip().lower()
        exact = next((row for row in catalog_rows if row["action"].lower() == normalized), None)
        partial = None
        if exact is None:
            partial = next(
                (
                    row
                    for row in catalog_rows
                    if normalized in row["action"].lower() or row["action"].lower() in normalized
                ),
                None,
            )
        mapped.append({"raw_action": str(action), "catalog": exact or partial})
    return mapped


def create_alert_in_db(
    event_id: str,
    module: str,
    raw_data: dict[str, Any],
    indicators: list[dict],
    score: int,
    severity: str,
    llm_output: dict[str, Any],
) -> str:
    """Persist the alert, its recommended actions, and mark the event completed.

    Returns the created alert UUID. Raises HTTPException 500 on DB failure.
    """
    client = get_supabase()
    alert_id = str(uuid.uuid4())

    title = raw_data.get("subject") or raw_data.get("url") or f"{module} threat detected"
    threat_type = raw_data.get("threat_type") or MODULE_DEFAULT_THREAT_TYPES.get(module, module)
    explanation = str(llm_output.get("explanation", ""))
    mitre = llm_output.get("mitre_techniques") or []

    try:
        client.table("alerts").insert(
            {
                "id": alert_id,
                "event_id": event_id,
                "title": title,
                "module": module,
                "threat_type": threat_type,
                "severity": severity,
                "risk_score": score,
                "status": "new",
                "summary": explanation,
                "indicators": indicators,
                "explanation": explanation,
                "mitre": mitre,
                "target_user": raw_data.get("target_user"),
                "target_service": raw_data.get("target_service"),
                "source_ip": raw_data.get("source_ip"),
            }
        ).execute()
    except Exception as exc:
        logger.exception("Failed to insert alert for event %s", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save alert",
        ) from exc

    try:
        mapped_actions = _match_catalog_actions(client, llm_output.get("recommended_actions") or [])
        rows = []
        for mapped in mapped_actions:
            catalog = mapped["catalog"]
            rows.append(
                {
                    "alert_id": alert_id,
                    "action": catalog["action"] if catalog else mapped["raw_action"],
                    "description": catalog["description"] if catalog else mapped["raw_action"],
                    "automation_level": catalog["automation_level"] if catalog else "manual",
                    "requires_approval": catalog["requires_approval"] if catalog else False,
                    "priority": severity,
                    "executed": False,
                }
            )
        if rows:
            client.table("recommended_actions").insert(rows).execute()
    except Exception as exc:
        logger.exception("Failed to save recommended actions for alert %s", alert_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save recommended actions",
        ) from exc

    try:
        client.table("events").update({"status": "completed"}).eq("id", event_id).execute()
    except Exception as exc:
        logger.exception("Failed to mark event %s completed", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update event status",
        ) from exc

    return alert_id
