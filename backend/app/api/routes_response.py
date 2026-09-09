"""Response action endpoints (Part 6)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import CurrentUser, get_current_user, has_permission, require_permission
from app.core.supabase_client import get_supabase
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
    payload: ResponseExecuteRequest,
    user: CurrentUser = Depends(require_permission("response.execute")),
) -> dict[str, Any]:
    """Execute (or approve) a catalog response action against a target.

    Requires response.execute; approval-required (destructive) catalog
    entries additionally require response.execute_destructive.
    """
    try:
        catalog_rows = (
            get_supabase()
            .table("response_catalog")
            .select("requires_approval")
            .eq("id", payload.catalog_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch catalog entry",
        ) from exc
    if not catalog_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Catalog entry not found"
        )
    if catalog_rows[0].get("requires_approval") and not await has_permission(
        user, "response.execute_destructive"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing permission: response.execute_destructive",
        )
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
