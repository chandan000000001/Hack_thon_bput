"""Audit log endpoints (Part 6)."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, get_current_user, require_permission
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/logs", response_model=list[dict])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    analyst: CurrentUser = Depends(require_permission("audit.view")),
) -> list[dict[str, Any]]:
    """Return the caller's organization's audit log entries, newest first."""
    return await audit_service.get_audit_logs(org_id=analyst.org_id, limit=limit, offset=offset)
