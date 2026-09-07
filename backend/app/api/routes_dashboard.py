"""Dashboard endpoints (Part 6)."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the aggregated dashboard summary."""
    return await dashboard_service.get_dashboard_summary()
