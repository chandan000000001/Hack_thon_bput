"""SQLAlchemy ORM models mapping to the existing Supabase tables (Phase A).

These models describe the tables already created by db/schema.sql. They do not
create or migrate anything by themselves; Alembic/DDL stays in db/schema.sql.
Columns the domain layer does not need (e.g. media hashes) are intentionally
left unmapped — SQLAlchemy only loads what is declared here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all CYBERGUARD domain models."""


class IncidentModel(Base):
    """An incident under investigation (table ``incidents``)."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Tenant scope (migration 0004); the service layer filters on it because
    # the service-role client bypasses RLS.
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    title: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    assigned_to: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    events: Mapped[list["IncidentEventModel"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEventModel.created_at",
    )
    alert_links: Mapped[list["IncidentAlertLinkModel"]] = relationship(
        cascade="all, delete-orphan"
    )


class IncidentEventModel(Base):
    """One timeline entry on an incident (table ``incident_events``)."""

    __tablename__ = "incident_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    incident: Mapped[IncidentModel] = relationship(back_populates="events")


class AlertModel(Base):
    """A detection alert raised by the analysis pipeline (table ``alerts``)."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id"))
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    module: Mapped[str] = mapped_column(String(32))
    threat_type: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    risk_score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    indicators: Mapped[Optional[dict]] = mapped_column(JSONB)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    mitre: Mapped[Optional[dict]] = mapped_column(JSONB)
    target_user: Mapped[Optional[str]] = mapped_column(Text)
    target_service: Mapped[Optional[str]] = mapped_column(Text)
    source_ip: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IncidentAlertLinkModel(Base):
    """Junction row linking an incident to an alert (table ``incident_alerts``)."""

    __tablename__ = "incident_alerts"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
