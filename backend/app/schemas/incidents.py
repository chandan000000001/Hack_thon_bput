"""Pydantic schemas for incident management endpoints (Part 6)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

SeverityValue = Literal["safe", "low", "medium", "high", "critical"]
IncidentStatusValue = Literal["open", "investigating", "contained", "closed"]


class IncidentCreate(BaseModel):
    """Body for creating an incident, optionally linking existing alerts."""

    title: str = Field(min_length=1)
    severity: SeverityValue
    linked_alert_ids: list[str] = []


class IncidentStatusUpdate(BaseModel):
    """Body for updating an incident's status."""

    status: IncidentStatusValue


class IncidentAssign(BaseModel):
    """Body for assigning an incident to an analyst."""

    assigned_to: str = Field(min_length=1)


class IncidentEscalate(BaseModel):
    """Body for escalating an incident."""

    reason: str = Field(min_length=1)


class IncidentResponse(BaseModel):
    """Incident record with linked alerts and its event timeline."""

    id: str
    title: str
    severity: str
    status: str
    assigned_to: Optional[str] = None
    linked_alert_ids: list = []
    timeline: list = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
