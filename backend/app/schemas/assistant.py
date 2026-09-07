"""Pydantic schemas for the SOC assistant chat endpoint (Part 6)."""

from pydantic import BaseModel, Field


class AssistantMessage(BaseModel):
    """Body for a SOC assistant chat message."""

    message: str = Field(min_length=1)


class AssistantResponse(BaseModel):
    """Assistant reply plus the alert IDs used as context."""

    reply: str
    context_used: list[str] = []
