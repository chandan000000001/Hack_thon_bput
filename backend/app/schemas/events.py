"""Pydantic schemas for multi-source event ingestion (Part 2)."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class EmailEvent(BaseModel):
    """Email submitted for phishing analysis."""

    event_type: str = "phishing_email"
    source: str = Field(min_length=1)
    sender: str = Field(min_length=1)
    subject: str
    body: str
    target_user: Optional[str] = None


class UrlEvent(BaseModel):
    """URL submitted for malicious URL analysis."""

    event_type: str = "malicious_url"
    source: str = Field(min_length=1)
    url: str = Field(min_length=1)
    target_user: Optional[str] = None


class MessageEvent(BaseModel):
    """Message submitted for impersonation analysis."""

    event_type: str = "impersonation_message"
    source: str = Field(min_length=1)
    sender: str = Field(min_length=1)
    claimed_identity: str = Field(min_length=1)
    message: str


class AuthLogEvent(BaseModel):
    """Authentication log records submitted for account takeover analysis."""

    event_type: str = "account_takeover"
    source: str = Field(min_length=1)
    events: list[dict[str, Any]]


class NetworkFlowEvent(BaseModel):
    """Network flow records submitted for network threat analysis."""

    event_type: str = "network_flow"
    source: str = Field(min_length=1)
    flows: list[dict[str, Any]]


class ApiLogEvent(BaseModel):
    """API log records submitted for API abuse analysis."""

    event_type: str = "api_abuse"
    source: str = Field(min_length=1)
    logs: list[dict[str, Any]]
