"""Health check endpoints (Phase D-2, item 9).

GET /health is a shallow liveness probe: it never performs a Supabase
round-trip per call. Connectivity is served from a cache that is lazily
refreshed at most once every 30 seconds.

GET /health/deep is the diagnostics endpoint: authenticated, it performs the
live Supabase round-trip and reports the fresh result.
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user
from app.core.supabase_client import check_connection

router = APIRouter(tags=["health"])

_CONNECTIVITY_REFRESH_SECONDS = 30.0
_connectivity_cache: tuple[float, bool] = (0.0, False)  # (next_refresh_at, value)


def _cached_connectivity() -> bool:
    """Return the cached Supabase connectivity flag, refreshed lazily.

    At most one live round-trip happens every 30 seconds across all /health
    callers; every other call is served from memory.
    """
    global _connectivity_cache
    now = time.monotonic()
    if now >= _connectivity_cache[0]:
        _connectivity_cache = (now + _CONNECTIVITY_REFRESH_SECONDS, check_connection())
    return _connectivity_cache[1]


@router.get("/health")
def read_health() -> dict:
    """Shallow liveness probe — no Supabase round-trip per call."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supabase_connected": _cached_connectivity(),
    }


@router.get("/health/deep")
async def read_deep_health(_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Authenticated diagnostics probe with a live Supabase round-trip."""
    from app.services.ml_inference import deepfake_deployment_status

    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supabase_connected": check_connection(),
        "checked_by": _user.id,
        "models": deepfake_deployment_status(light=False),
    }
