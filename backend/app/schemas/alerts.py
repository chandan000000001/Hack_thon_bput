"""Pydantic schemas for alert management endpoints (Part 6)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

AlertStatusValue = Literal["new", "acknowledged", "resolved", "dismissed"]


class AlertListParams(BaseModel):
    """Query parameters for listing alerts."""

    severity: Optional[str] = None
    module: Optional[str] = None
    status: Optional[str] = None
    search: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AlertStatusUpdate(BaseModel):
    """Body for updating an alert's status."""

    status: AlertStatusValue


class AlertResponse(BaseModel):
    """Alert record with its recommended actions joined."""

    id: str
    title: str
    module: str
    threat_type: Optional[str] = None
    severity: str
    risk_score: int
    confidence: Optional[float] = None
    status: str
    summary: Optional[str] = None
    indicators: list = []
    explanation: Optional[str] = None
    mitre: list = []
    recommended_actions: list = []
    target_user: Optional[str] = None
    target_service: Optional[str] = None
    source_ip: Optional[str] = None
    created_at: Optional[str] = None
