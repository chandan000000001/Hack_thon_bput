"""Alert persistence service.

Writes alerts, recommended actions, and event status transitions to
Supabase using the service role client.

Hardened after the "Failed to query recommended actions" 500:
  - strict type casting before every recommended_actions insert
    (LLMs / JSON round-trips emit 'true'/'1'/'yes' strings and invalid
    enum values like 'AUTO' or 'URGENT')
  - a failed recommended_actions insert is logged and skipped — the alert
    itself is still created and returned (insert happens after the alert)
  - recommended_actions queries fail safe: they return [] instead of
    raising, so the alert always reaches the caller
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

VALID_AUTOMATION_LEVELS = ("automatic", "semi-automatic", "manual")
VALID_PRIORITIES = ("safe", "low", "medium", "high", "critical")


def _strict_bool(value: Any) -> bool:
    """Strict boolean coercion: True/'true'/'1'/'yes' -> True, else False."""
    return str(value).strip().lower() in ("true", "1", "yes")


def _clean_automation_level(value: Any) -> str:
    level = str(value or "").strip().lower()
    return level if level in VALID_AUTOMATION_LEVELS else "manual"


def _clean_priority(value: Any, fallback: str = "low") -> str:
    priority = str(value or "").strip().lower()
    if priority in VALID_PRIORITIES:
        return priority
    return fallback if fallback in VALID_PRIORITIES else "low"


def _clean_action_row(row: dict[str, Any], alert_id: str, severity: str) -> dict[str, Any]:
    """Enforce the exact column types expected by the recommended_actions
    table before insertion."""
    return {
        "alert_id": alert_id,
        "action": str(row.get("action") or "Review alert").strip() or "Review alert",
        "description": str(row.get("description") or ""),
        "automation_level": _clean_automation_level(row.get("automation_level")),
        "requires_approval": _strict_bool(row.get("requires_approval", False)),
        "priority": _clean_priority(row.get("priority"), fallback=severity),
        "executed": _strict_bool(row.get("executed", False)),
    }


def _match_catalog_actions(client: Any, recommended_actions: list[str]) -> list[dict]:
    """Map LLM-recommended actions to the seeded response_catalog entries.
    Catalog lookup failures degrade to unmapped (raw) actions."""
    try:
        catalog_rows = (
            client.table("response_catalog")
            .select("id, action, description, automation_level, requires_approval")
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("response_catalog lookup failed; inserting raw actions: %s", exc)
        catalog_rows = []

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


def _build_action_rows(
    client: Any, llm_actions: list, alert_id: str, severity: str
) -> list[dict[str, Any]]:
    """Build type-safe recommended_actions rows from LLM output + catalog."""
    mapped_actions = _match_catalog_actions(client, llm_actions or [])
    rows = []
    for mapped in mapped_actions:
        catalog = mapped["catalog"]
        rows.append(
            _clean_action_row(
                {
                    "action": catalog["action"] if catalog else mapped["raw_action"],
                    "description": catalog["description"] if catalog else mapped["raw_action"],
                    "automation_level": catalog["automation_level"] if catalog else "manual",
                    "requires_approval": catalog["requires_approval"] if catalog else False,
                    "priority": severity,
                    "executed": False,
                },
                alert_id,
                severity,
            )
        )
    return rows


def fetch_recommended_actions(alert_id: str) -> list[dict[str, Any]]:
    """Safe query: returns the alert's recommended actions, or [] on failure.

    Used by the API response builders so a recommended_actions failure can
    never turn into a 500 — the alert is still returned.
    """
    try:
        response = (
            get_supabase()
            .table("recommended_actions")
            .select("*")
            .eq("alert_id", alert_id)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"❌ Supabase recommended_actions query error: {e}")
        logger.exception("Failed to query recommended actions for alert %s", alert_id)
        return []


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

    The alert row is inserted FIRST; recommended actions are best-effort
    (type-cast, failures logged and skipped). Returns the created alert UUID.
    Raises HTTPException 500 only if the alert itself cannot be saved.
    """
    client = get_supabase()
    alert_id = str(uuid.uuid4())

    title = raw_data.get("subject") or raw_data.get("url") or f"{module} threat detected"
    threat_type = raw_data.get("threat_type") or MODULE_DEFAULT_THREAT_TYPES.get(module, module)
    explanation = str(llm_output.get("explanation", ""))
    mitre = llm_output.get("mitre_techniques") or []

    # 1. The alert itself must exist before recommended actions reference it.
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

    # 2. Recommended actions: type-cast rows, best-effort insert. A failure
    #    here must NOT crash alert creation.
    try:
        rows = _build_action_rows(
            client, llm_output.get("recommended_actions") or [], alert_id, severity
        )
        if rows:
            client.table("recommended_actions").insert(rows).execute()
    except Exception as e:
        print(f"❌ Supabase recommended_actions insert error: {e}")
        logger.exception("Failed to save recommended actions for alert %s", alert_id)

    # 3. Mark the event completed (best-effort; the alert is already saved).
    try:
        client.table("events").update({"status": "completed"}).eq("id", event_id).execute()
    except Exception as exc:
        logger.exception("Failed to mark event %s completed", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update event status",
        ) from exc

    return alert_id
