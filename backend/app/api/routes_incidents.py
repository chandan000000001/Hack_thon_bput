"""Incident management endpoints (Part 6)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import CurrentUser, get_current_user
from app.schemas.incidents import (
    IncidentAssign,
    IncidentCreate,
    IncidentEscalate,
    IncidentResponse,
    IncidentStatusUpdate,
)
from app.services import incident_service

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    status_filter: Optional[str] = None,
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List incidents, newest activity first, optionally filtered by status."""
    return await incident_service.list_incidents(status_filter)


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str, _user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Fetch a single incident with its timeline and linked alerts."""
    return await incident_service.get_incident(incident_id)


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Create an incident, optionally linking existing alerts."""
    return await incident_service.create_incident(
        title=payload.title,
        severity=payload.severity,
        linked_alert_ids=payload.linked_alert_ids,
        created_by=user.email or user.id,
    )


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
async def update_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Change an incident's status."""
    return await incident_service.update_incident_status(
        incident_id, payload.status, actor=user.email or user.id
    )


@router.patch("/{incident_id}/assign", response_model=IncidentResponse)
async def assign_incident(
    incident_id: str,
    payload: IncidentAssign,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Assign an incident to an analyst."""
    return await incident_service.assign_incident(
        incident_id, payload.assigned_to, actor=user.email or user.id
    )


@router.post("/{incident_id}/escalate", response_model=IncidentResponse)
async def escalate_incident(
    incident_id: str,
    payload: IncidentEscalate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Escalate an incident to critical severity with a reason."""
    return await incident_service.escalate_incident(
        incident_id, payload.reason, actor=user.email or user.id
    )
