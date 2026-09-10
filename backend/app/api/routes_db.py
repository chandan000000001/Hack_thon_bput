"""Database introspection endpoints (Phase D-2: org-scoped, no error leaks)."""

import logging

from fastapi import APIRouter, Depends
from fastapi import HTTPException, status as http_status

from app.core.asyncbridge import to_thread
from app.core.security import CurrentUser, get_current_user
from app.core.supabase_client import get_supabase

logger = logging.getLogger("cyberguard.db")

router = APIRouter(tags=["db"])

MONITORED_TABLES = ("events", "alerts", "incidents", "audit_logs")


@router.get("/db/check")
async def check_database(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return org-scoped row counts for the core tables.

    Every count is filtered by the caller's org_id (multi-tenancy), and raw
    Supabase error strings never reach the client — failures log server-side
    and answer 500 "database check unavailable".
    """
    client = get_supabase()
    counts: dict[str, int | None] = {}

    def _count(table: str) -> int:
        response = (
            client.table(table)
            .select("id", count="exact")
            .eq("org_id", user.org_id)
            .limit(1)
            .execute()
        )
        return response.count or 0

    for table in MONITORED_TABLES:
        try:
            counts[table] = await to_thread(_count, table)
        except Exception:
            # Raw error stays in the server log only (Phase D-2, item 3).
            logger.exception("db/check count failed for table %s", table)
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="database check unavailable",
            ) from None

    return {"tables": counts, "org_id": user.org_id}
