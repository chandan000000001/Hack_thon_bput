"""Database introspection endpoints."""

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.core.supabase_client import get_supabase

router = APIRouter(tags=["db"])

MONITORED_TABLES = ("events", "alerts", "incidents", "audit_logs")


@router.get("/db/check")
def check_database(_user: dict = Depends(get_current_user)) -> dict:
    """Return row counts for the core tables using the service role client."""
    client = get_supabase()
    counts: dict[str, int | None] = {}
    errors: dict[str, str] = {}

    for table in MONITORED_TABLES:
        try:
            response = client.table(table).select("id", count="exact").limit(1).execute()
            counts[table] = response.count or 0
        except Exception as exc:
            counts[table] = None
            errors[table] = str(exc)

    payload: dict = {"tables": counts}
    if errors:
        payload["errors"] = errors
    return payload
