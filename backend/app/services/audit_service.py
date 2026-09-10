"""Audit logging service (Part 6 + Phases B/D-1).

Writes org-scoped rows to the audit_logs table via the service role client.
Phase B: when the caller does not pass an org_id it is resolved from the
acting user's profile (5-minute cache, Default Organization fallback).
Phase D-1: a failed write is retried once; if the retry also fails, the row
is appended to evidence/logs/audit_fallback.jsonl (durable local record) and
an error is logged — audit failures are never swallowed silently. All
supabase-py calls run in the threadpool.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.asyncbridge import to_thread
from app.core.supabase_client import _get_default_org_id, get_supabase, get_user_org_id

logger = logging.getLogger("cyberguard.audit")

# Repo root is three levels up: app/services/audit_service.py -> backend/app -> backend -> repo.
_FALLBACK_LOG_PATH = (
    Path(__file__).resolve().parents[3] / "evidence" / "logs" / "audit_fallback.jsonl"
)
_AUDIT_WRITE_ATTEMPTS = 2


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
    return await _get_default_org_id()


def _write_fallback_record(record: dict[str, Any]) -> None:
    """Append one JSON line to the local audit fallback log. Sync (threadpool)."""
    _FALLBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FALLBACK_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


async def log_action(
    user_id: str,
    user_name: str,
    action: str,
    resource: str,
    details: str,
    org_id: Optional[str] = None,
) -> None:
    """Insert an org-scoped audit log row for a state-changing operation.

    Durability contract (Phase D-1): one retry on failure, then a JSON line
    in evidence/logs/audit_fallback.jsonl plus an error log — never silent.
    """
    clean_user_id = _clean_user_id(user_id)
    record = {
        "user_id": clean_user_id,
        "user_name": user_name,
        "action": action,
        "resource": resource,
        "details": details,
    }

    try:
        record["org_id"] = await _resolve_org_id(clean_user_id, org_id)
    except Exception as exc:
        # Resolution itself failed; the DB is likely down. Fall through to the
        # retry/fallback path with the org left unset in the fallback record.
        logger.warning("audit org resolution failed for action %r: %s", action, exc)

    last_error: Optional[Exception] = None
    for attempt in range(1, _AUDIT_WRITE_ATTEMPTS + 1):
        try:
            await to_thread(
                lambda: get_supabase().table("audit_logs").insert(dict(record)).execute()
            )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "audit log write failed (attempt %d/%d) for action %r: %s",
                attempt,
                _AUDIT_WRITE_ATTEMPTS,
                action,
                exc,
            )

    # Both attempts failed: durable local fallback, then a loud error.
    fallback_record = {
        **record,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": str(last_error),
    }
    try:
        await to_thread(_write_fallback_record, fallback_record)
        logger.error(
            "audit fallback written for action %r after %d failed Supabase attempts",
            action,
            _AUDIT_WRITE_ATTEMPTS,
        )
    except Exception:
        logger.exception(
            "audit fallback write ALSO failed for action %r — audit row lost", action
        )


async def get_audit_logs(
    org_id: str, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Fetch the organization's audit log rows, newest first.

    The org_id filter is the tenant isolation: the service-role client
    bypasses RLS, so it must be applied here explicitly.
    """
    response = await to_thread(
        lambda: get_supabase()
        .table("audit_logs")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .range(offset, offset + max(limit, 0) - 1)
        .execute()
    )
    return response.data or []
