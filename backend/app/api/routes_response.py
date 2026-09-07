"""Response action endpoints (Part 6)."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, get_current_user
from app.schemas.responses import ResponseExecuteRequest, ResponseExecutionResponse
from app.services import response_service

router = APIRouter(prefix="/responses", tags=["Response Actions"])


@router.get("/catalog", response_model=list[dict])
async def get_response_catalog(
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return the full response action catalog."""
    return await response_service.get_response_catalog()


@router.post("/execute", response_model=ResponseExecutionResponse)
async def execute_response(
    payload: ResponseExecuteRequest, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Execute (or approve) a catalog response action against a target."""
    return await response_service.execute_response(
        catalog_id=payload.catalog_id,
        target=payload.target,
        approved=payload.approved,
        executed_by=user.email or user.id,
    )


@router.get("/history", response_model=list[ResponseExecutionResponse])
async def get_execution_history(
    limit: int = Query(default=50, ge=1, le=200),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return recent response executions, newest first."""
    return await response_service.get_execution_history(limit)
