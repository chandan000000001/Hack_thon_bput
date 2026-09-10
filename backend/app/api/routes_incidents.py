"""Incident management endpoints (Part 6 + Phase A domain layer)."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import CurrentUser, get_current_user, has_permission, require_permission
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
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List the caller's org incidents, newest activity first, optionally filtered."""
    return await incident_service.list_incidents(user.org_id, status_filter)


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Fetch an org-scoped incident with its timeline and linked alerts."""
    return await incident_service.get_incident(user.org_id, incident_id)


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    user: CurrentUser = Depends(require_permission("incident.create")),
) -> dict[str, Any]:
    """Create an org-scoped incident, optionally linking same-org alerts."""
    return await incident_service.create_incident(
        org_id=user.org_id,
        title=payload.title,
        severity=payload.severity,
        linked_alert_ids=payload.linked_alert_ids,
        created_by=user.email or user.id,
    )


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
async def update_incident_status(
    incident_id: str,
    payload: IncidentStatusPatch,
    user: CurrentUser = Depends(require_permission("incident.update")),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Change an incident's status through the NIST/SANS lifecycle state machine.

    Fetches the incident via SQLAlchemy (scoped to the caller's organization),
    validates the transition, then commits the status change and the timeline
    event together. Illegal transitions are rejected with 400 and cross-tenant
    ids resolve to 404 before anything is written.
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
        select(IncidentModel)
        .where(IncidentModel.id == incident_uuid)
        .where(IncidentModel.org_id == uuid.UUID(user.org_id))
        # Phase D-1: row lock serializes concurrent status transitions so two
        # simultaneous PATCHes cannot both pass validate_transition.
        .with_for_update()
        .limit(1)
    )
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        )

    current_status = normalize_status(incident.status)
    # Closing an incident is a distinct, higher-bar permission than updating.
    if new_status == "CLOSED" and not await has_permission(user, "incident.close"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing permission: incident.close",
        )
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
        actor, actor, f"Incident status changed to {new_status}", f"incident:{incident_id}", "",
        org_id=user.org_id,
    )
    return await incident_service.get_incident(user.org_id, incident_id)


@router.patch("/{incident_id}/assign", response_model=IncidentResponse)
async def assign_incident(
    incident_id: str,
    payload: IncidentAssign,
    user: CurrentUser = Depends(require_permission("incident.update")),
) -> dict[str, Any]:
    """Assign an org-scoped incident to an analyst."""
    return await incident_service.assign_incident(
        user.org_id, incident_id, payload.assigned_to, actor=user.email or user.id
    )


@router.post("/{incident_id}/escalate", response_model=IncidentResponse)
async def escalate_incident(
    incident_id: str,
    payload: IncidentEscalate,
    user: CurrentUser = Depends(require_permission("incident.escalate")),
) -> dict[str, Any]:
    """Escalate an org-scoped incident to critical severity with a reason."""
    return await incident_service.escalate_incident(
        user.org_id, incident_id, payload.reason, actor=user.email or user.id
    )
