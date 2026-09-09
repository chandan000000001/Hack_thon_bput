"""Incident management service (Part 6 + Phase B multi-tenancy).

Every query and write is scoped by org_id: the service-role client used here
bypasses Row Level Security, so explicit `.eq("org_id", org_id)` filtering on
every SELECT and org_id on every INSERT is the primary tenant isolation.
"""

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


def _filter_alerts_in_org(client: Any, org_id: str, alert_ids: list[str]) -> list[str]:
    """Return only the requested alert ids that belong to the caller's org."""
    try:
        rows = (
            client.table("alerts")
            .select("id")
            .eq("org_id", org_id)
            .in_("id", alert_ids)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        _raise_db_error(exc, "Failed to validate linked alerts")
    return [row["id"] for row in rows]


async def create_incident(
    org_id: str,
    title: str,
    severity: str,
    linked_alert_ids: list[str],
    created_by: str,
) -> dict[str, Any]:
    """Create an org-scoped incident, link same-org alerts, add a timeline
    entry, and audit it."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .insert({"org_id": org_id, "title": title, "severity": severity, "status": "open"})
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
        # Only link alerts that exist inside the caller's organization.
        allowed_ids = _filter_alerts_in_org(client, org_id, linked_alert_ids)
        if allowed_ids:
            try:
                client.table("incident_alerts").insert(
                    [{"incident_id": incident_id, "alert_id": alert_id} for alert_id in allowed_ids]
                ).execute()
            except Exception as exc:
                _raise_db_error(exc, "Failed to link alerts to incident")

    _add_timeline_event(
        incident_id,
        "Incident Created",
        created_by,
        f"Linked {len(allowed_ids) if linked_alert_ids else 0} alert(s)",
    )
    await audit_service.log_action(
        created_by,
        created_by,
        "Incident created",
        f"incident:{incident_id}",
        f"Incident '{title}' created with severity '{severity}'",
        org_id=org_id,
    )
    return await get_incident(org_id, incident_id)


async def get_incident(org_id: str, incident_id: str) -> dict[str, Any]:
    """Fetch an org-scoped incident with its linked alert IDs and timeline."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .select("*")
            .eq("id", incident_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
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


async def list_incidents(
    org_id: str, status_filter: Optional[str] = None
) -> list[dict[str, Any]]:
    """List the org's incidents, newest activity first, optionally by status."""
    if status_filter and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter; must be one of {sorted(VALID_STATUSES)}",
        )
    query = (
        get_supabase()
        .table("incidents")
        .select("*")
        .eq("org_id", org_id)
        .order("updated_at", desc=True)
    )
    if status_filter:
        query = query.eq("status", status_filter)
    try:
        response = query.execute()
    except Exception as exc:
        _raise_db_error(exc, "Failed to list incidents")
    return response.data or []


async def update_incident_status(
    org_id: str, incident_id: str, new_status: str, actor: str
) -> dict[str, Any]:
    """Change an org-scoped incident's status, record the timeline entry,
    and audit it. A cross-tenant id resolves to 404, not an update."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .update({"status": new_status, "updated_at": _now_iso()})
            .eq("id", incident_id)
            .eq("org_id", org_id)
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
        actor, actor, f"Incident status changed to {new_status}", f"incident:{incident_id}", "",
        org_id=org_id,
    )
    return await get_incident(org_id, incident_id)


async def assign_incident(
    org_id: str, incident_id: str, assigned_to: str, actor: str
) -> dict[str, Any]:
    """Assign an org-scoped incident, record the timeline entry, and audit it."""
    client = get_supabase()
    try:
        response = (
            client.table("incidents")
            .update({"assigned_to": assigned_to, "updated_at": _now_iso()})
            .eq("id", incident_id)
            .eq("org_id", org_id)
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
        actor, actor, "Incident assigned", f"incident:{incident_id}", f"Assigned to {assigned_to}",
        org_id=org_id,
    )
    return await get_incident(org_id, incident_id)


async def escalate_incident(
    org_id: str, incident_id: str, reason: str, actor: str
) -> dict[str, Any]:
    """Escalate an org-scoped incident to critical severity and audit it."""
    client = get_supabase()
    try:
        current = (
            client.table("incidents")
            .select("severity")
            .eq("id", incident_id)
            .eq("org_id", org_id)
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
        client.table("incidents").update(update_payload).eq("id", incident_id).eq(
            "org_id", org_id
        ).execute()
    except Exception as exc:
        _raise_db_error(exc, "Failed to escalate incident")

    _add_timeline_event(incident_id, "Incident Escalated", actor, reason)
    await audit_service.log_action(
        actor, actor, "Incident escalated", f"incident:{incident_id}", reason,
        org_id=org_id,
    )
    return await get_incident(org_id, incident_id)
