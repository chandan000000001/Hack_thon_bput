"""Audit logging service (Part 6 + Phase B multi-tenancy).

Writes org-scoped rows to the audit_logs table via the service role client.
Logging failures are logged but never crash the calling operation. When the
caller does not pass an org_id, it is resolved from the acting user's
profile (5-minute cache, Default Organization fallback).
"""

import logging
from typing import Any, Optional

from app.core.supabase_client import _get_default_org_id, get_supabase, get_user_org_id

logger = logging.getLogger("cyberguard.audit")


def _clean_user_id(user_id: Optional[str]) -> Optional[str]:
    """Return None for empty user ids so the uuid column stays NULL."""
    return user_id if user_id else None


async def _resolve_org_id(user_id: Optional[str], org_id: Optional[str]) -> str:
    """Return the explicit org_id, or resolve it from the acting user."""
    if org_id:
        return org_id
    if user_id:
        try:
            return await get_user_org_id(user_id)
        except Exception:
            logger.warning("org resolution failed for audit log user %s", user_id)
    return _get_default_org_id()


async def log_action(
    user_id: str,
    user_name: str,
    action: str,
    resource: str,
    details: str,
    org_id: Optional[str] = None,
) -> None:
    """Insert an org-scoped audit log row for a state-changing operation."""
    try:
        resolved_org_id = await _resolve_org_id(_clean_user_id(user_id), org_id)
        get_supabase().table("audit_logs").insert(
            {
                "user_id": _clean_user_id(user_id),
                "user_name": user_name,
                "action": action,
                "resource": resource,
                "details": details,
                "org_id": resolved_org_id,
            }
        ).execute()
    except Exception:
        logger.exception("Failed to write audit log for action %r", action)


async def get_audit_logs(
    org_id: str, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Fetch the organization's audit log rows, newest first.

    The org_id filter is the tenant isolation: the service-role client
    bypasses RLS, so it must be applied here explicitly.
    """
    response = (
        get_supabase()
        .table("audit_logs")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .range(offset, offset + max(limit, 0) - 1)
        .execute()
    )
    return response.data or []
