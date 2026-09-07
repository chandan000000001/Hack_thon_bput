"""Incident management service (Part 6)."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.core.supabase_client import get_supabase
from app.services import audit_service

logger = logging.getLogger("cyberguard.incidents")

VALID_STATUSES = {"open", "investigating", "contained", "closed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_db_error(exc: Exception, detail: str) -> None:
    logger.exception("Incident database error: %s", detail)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail
    ) from exc


def _add_timeline_event(incident_id: str, action: str, actor: str, details: str = "") -> None:
    try:
        get_supabase().table("incident_events").insert(
            {
                "incident_id": incident_id,
                "action": action,
                "actor": actor,
                "details": details,
            }
        ).execute()
    except Exception as exc:
        _raise_db_error(exc, "Failed to add incident timeline event")


async def create_incident(
    title: str, severity: str, linked_alert_ids: list[str], created_by: str
) -> dict[str, Any]:
    """Create an incident, link alerts, add a timeline entry, and audit it."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .insert({"title": title, "severity": severity, "status": "open"})
            .execute()
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to create incident")

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Incident creation returned no data",
        )
    incident = rows[0]
    incident_id = incident["id"]

    if linked_alert_ids:
        try:
            client.table("incident_alerts").insert(
                [{"incident_id": incident_id, "alert_id": alert_id} for alert_id in linked_alert_ids]
            ).execute()
        except Exception as exc:
            _raise_db_error(exc, "Failed to link alerts to incident")

    _add_timeline_event(
        incident_id,
        "Incident Created",
        created_by,
        f"Linked {len(linked_alert_ids)} alert(s)",
    )
    await audit_service.log_action(
        created_by,
        created_by,
        "Incident created",
        f"incident:{incident_id}",
        f"Incident '{title}' created with severity '{severity}'",
    )
    return await get_incident(incident_id)


async def get_incident(incident_id: str) -> dict[str, Any]:
    """Fetch an incident with its linked alert IDs and event timeline."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents").select("*").eq("id", incident_id).limit(1).execute()
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to query incident")

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )
    incident = rows[0]

    try:
        links = (
            client.table("incident_alerts")
            .select("alert_id")
            .eq("incident_id", incident_id)
            .execute()
            .data
            or []
        )
        timeline = (
            client.table("incident_events")
            .select("*")
            .eq("incident_id", incident_id)
            .order("created_at", desc=False)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to query incident details")

    return {
        "id": incident["id"],
        "title": incident.get("title"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "assigned_to": incident.get("assigned_to"),
        "linked_alert_ids": [link["alert_id"] for link in links],
        "timeline": timeline,
        "created_at": incident.get("created_at"),
        "updated_at": incident.get("updated_at"),
    }


async def list_incidents(status_filter: Optional[str] = None) -> list[dict[str, Any]]:
    """List incidents, newest activity first, optionally by status."""
    if status_filter and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter; must be one of {sorted(VALID_STATUSES)}",
        )
    query = get_supabase().table("incidents").select("*").order("updated_at", desc=True)
    if status_filter:
        query = query.eq("status", status_filter)
    try:
        response = query.execute()
    except Exception as exc:
        _raise_db_error(exc, "Failed to list incidents")
    return response.data or []


async def update_incident_status(incident_id: str, new_status: str, actor: str) -> dict[str, Any]:
    """Change an incident's status, record the timeline entry, and audit it."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .update({"status": new_status, "updated_at": _now_iso()})
            .eq("id", incident_id)
            .execute()
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to update incident status")

    if not (response.data or []):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    _add_timeline_event(incident_id, f"Status changed to {new_status}", actor)
    await audit_service.log_action(
        actor, actor, f"Incident status changed to {new_status}", f"incident:{incident_id}", ""
    )
    return await get_incident(incident_id)


async def assign_incident(incident_id: str, assigned_to: str, actor: str) -> dict[str, Any]:
    """Assign an incident, record the timeline entry, and audit it."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .update({"assigned_to": assigned_to, "updated_at": _now_iso()})
            .eq("id", incident_id)
            .execute()
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to assign incident")

    if not (response.data or []):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    _add_timeline_event(incident_id, f"Assigned to {assigned_to}", actor)
    await audit_service.log_action(
        actor, actor, "Incident assigned", f"incident:{incident_id}", f"Assigned to {assigned_to}"
    )
    return await get_incident(incident_id)


async def escalate_incident(incident_id: str, reason: str, actor: str) -> dict[str, Any]:
    """Escalate an incident to critical severity, audit the escalation."""
    client = get_supabase()
    try:
        current = (
            client.table("incidents")
            .select("severity")
            .eq("id", incident_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to query incident")

    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    update_payload: dict[str, Any] = {"updated_at": _now_iso()}
    if current[0].get("severity") != "critical":
        update_payload["severity"] = "critical"

    try:
        client.table("incidents").update(update_payload).eq("id", incident_id).execute()
    except Exception as exc:
        _raise_db_error(exc, "Failed to escalate incident")

    _add_timeline_event(incident_id, "Incident Escalated", actor, reason)
    await audit_service.log_action(
        actor, actor, "Incident escalated", f"incident:{incident_id}", reason
    )
    return await get_incident(incident_id)
