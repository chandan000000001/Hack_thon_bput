"""Audit logging service (Part 6).

Writes to the audit_logs table via the service role client. Logging
failures are logged but never crash the calling operation.
"""

import logging
from typing import Any, Optional

from app.core.supabase_client import get_supabase

logger = logging.getLogger("cyberguard.audit")


def _clean_user_id(user_id: Optional[str]) -> Optional[str]:
    """Return None for empty user ids so the uuid column stays NULL."""
    return user_id if user_id else None


async def log_action(
    user_id: str, user_name: str, action: str, resource: str, details: str
) -> None:
    """Insert an audit log row for a state-changing operation."""
    try:
        get_supabase().table("audit_logs").insert(
            {
                "user_id": _clean_user_id(user_id),
                "user_name": user_name,
                "action": action,
                "resource": resource,
                "details": details,
            }
        ).execute()
    except Exception:
        logger.exception("Failed to write audit log for action %r", action)


async def get_audit_logs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Fetch audit log rows, newest first."""
    response = (
        get_supabase()
        .table("audit_logs")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + max(limit, 0) - 1)
        .execute()
    )
    return response.data or []
