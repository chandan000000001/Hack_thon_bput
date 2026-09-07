"""Pydantic schemas for response execution endpoints (Part 6)."""

from typing import Optional

from pydantic import BaseModel, Field


class ResponseExecuteRequest(BaseModel):
    """Body for executing (or approving) a catalog response action."""

    catalog_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    approved: bool = False


class ResponseExecutionResponse(BaseModel):
    """A recorded response execution."""

    id: str
    catalog_id: Optional[str] = None
    action_name: str
    target: Optional[str] = None
    status: str
    executed_by: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: Optional[str] = None
