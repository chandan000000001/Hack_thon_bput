"""Health check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.supabase_client import check_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def read_health() -> dict:
    """Public liveness probe including Supabase connectivity status."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supabase_connected": check_connection(),
    }
