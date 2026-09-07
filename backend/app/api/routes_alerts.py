"""Alert management endpoints (Part 6)."""

from collections import defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import CurrentUser, get_current_user
from app.core.supabase_client import get_supabase
from app.schemas.alerts import AlertListParams, AlertResponse, AlertStatusUpdate
from app.services import audit_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])

SEARCH_FIELDS = ("title", "summary", "explanation")


def _attach_recommended_actions(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join recommended_actions onto each alert row."""
    if not alerts:
        return alerts
    alert_ids = [alert["id"] for alert in alerts]
    try:
        actions = (
            get_supabase()
            .table("recommended_actions")
            .select("*")
            .in_("alert_id", alert_ids)
            .execute()
            .data
            or []
        )
    except Exception as e:
        # Fail-safe: return the alerts without actions instead of a 500.
        print(f"❌ Supabase recommended_actions query error: {e}")
        actions = []

    by_alert: dict[str, list[dict]] = defaultdict(list)
    for action in actions:
        by_alert[action["alert_id"]].append(action)
    for alert in alerts:
        alert["recommended_actions"] = by_alert.get(alert["id"], [])
    return alerts


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    params: Annotated[AlertListParams, Depends()],
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List alerts with optional severity/module/status filters and search."""
    query = get_supabase().table("alerts").select("*")
    if params.severity:
        query = query.eq("severity", params.severity)
    if params.module:
        query = query.eq("module", params.module)
    if params.status:
        query = query.eq("status", params.status)
    if params.search:
        # PostgREST `or` filter; strip characters that would break the syntax.
        sanitized = (
            params.search.replace(",", " ").replace("(", " ").replace(")", " ").strip()
        )
        if sanitized:
            conditions = ",".join(
                f"{field}.ilike.*{sanitized}*" for field in SEARCH_FIELDS
            )
            query = query.or_(conditions)

    try:
        response = (
            query.order("created_at", desc=True)
            .range(params.offset, params.offset + params.limit - 1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query alerts",
        ) from exc

    return _attach_recommended_actions(response.data or [])


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: str, _user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Fetch a single alert with its recommended actions."""
    try:
        response = (
            get_supabase()
            .table("alerts")
            .select("*")
            .eq("id", alert_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query alert",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )
    return _attach_recommended_actions(rows)[0]


@router.patch("/{alert_id}/status", response_model=AlertResponse)
async def update_alert_status(
    alert_id: str,
    payload: AlertStatusUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Update an alert's status and record the change in the audit log."""
    try:
        response = (
            get_supabase()
            .table("alerts")
            .update({"status": payload.status})
            .eq("id", alert_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update alert status",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )
    alert = rows[0]

    await audit_service.log_action(
        user.id,
        user.email or user.id,
        f"Alert status changed to {payload.status}",
        f"alert:{alert_id}",
        f"Alert '{alert.get('title')}'",
    )
    return _attach_recommended_actions([alert])[0]
