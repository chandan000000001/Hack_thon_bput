"""Incident management endpoints (Part 6 + Phase A domain layer)."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import CurrentUser, get_current_user, require_role
from app.domain.incident_lifecycle import (
    InvalidStateTransitionError,
    normalize_status,
    validate_transition,
)
from app.domain.models import IncidentEventModel, IncidentModel
from app.schemas.incidents import (
    IncidentAssign,
    IncidentCreate,
    IncidentEscalate,
    IncidentResponse,
)
from app.services import audit_service, incident_service

router = APIRouter(prefix="/incidents", tags=["Incidents"])


class IncidentStatusPatch(BaseModel):
    """Body for PATCH /incidents/{id}/status.

    Accepts both NIST/SANS lifecycle statuses (TRIAGE, CONTAINMENT, ERADICATION,
    RECOVERY, CLOSED) and the legacy values (open, investigating, contained,
    closed); the lifecycle module normalizes legacy input.
    """

    status: str = Field(min_length=1)


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
    payload: IncidentCreate, user: CurrentUser = Depends(require_role("analyst"))
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
    payload: IncidentStatusPatch,
    user: CurrentUser = Depends(require_role("analyst")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Change an incident's status through the NIST/SANS lifecycle state machine.

    Fetches the incident via SQLAlchemy, validates the transition, then commits
    the status change and the timeline event together. Illegal transitions are
    rejected with 400 before anything is written.
    """
    actor = user.email or user.id
    try:
        new_status = normalize_status(payload.status)
    except InvalidStateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message
        ) from exc

    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        ) from None

    result = await db.execute(
        select(IncidentModel).where(IncidentModel.id == incident_uuid).limit(1)
    )
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    current_status = normalize_status(incident.status)
    try:
        validate_transition(current_status, new_status)
    except InvalidStateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message
        ) from exc

    incident.status = new_status
    incident.updated_at = datetime.now(timezone.utc)
    db.add(
        IncidentEventModel(
            incident_id=incident.id,
            action=f"Status changed to {new_status}",
            actor=actor,
            details=f"Validated transition {current_status} -> {new_status}",
        )
    )
    await db.commit()

    await audit_service.log_action(
        actor, actor, f"Incident status changed to {new_status}", f"incident:{incident_id}", ""
    )
    return await incident_service.get_incident(incident_id)


@router.patch("/{incident_id}/assign", response_model=IncidentResponse)
async def assign_incident(
    incident_id: str,
    payload: IncidentAssign,
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict[str, Any]:
    """Assign an incident to an analyst."""
    return await incident_service.assign_incident(
        incident_id, payload.assigned_to, actor=user.email or user.id
    )


@router.post("/{incident_id}/escalate", response_model=IncidentResponse)
async def escalate_incident(
    incident_id: str,
    payload: IncidentEscalate,
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict[str, Any]:
    """Escalate an incident to critical severity with a reason."""
    return await incident_service.escalate_incident(
        incident_id, payload.reason, actor=user.email or user.id
    )
