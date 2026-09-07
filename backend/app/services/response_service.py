"""Response execution service (Part 6).

Executes catalog response actions with the human-approval gate. Actions
are recorded in response_executions and audited; no destructive side
effects are performed in this prototype.
"""

import logging
from typing import Any

from fastapi import HTTPException, status

from app.core.supabase_client import get_supabase
from app.services import audit_service

logger = logging.getLogger("cyberguard.response")


async def get_response_catalog() -> list[dict[str, Any]]:
    """Fetch the full response action catalog."""
    try:
        response = (
            get_supabase().table("response_catalog").select("*").order("action").execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch response catalog")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch response catalog",
        ) from exc
    return response.data or []


async def execute_response(
    catalog_id: str, target: str, approved: bool, executed_by: str
) -> dict[str, Any]:
    """Execute (or reject) a catalog response action against a target."""
    client = get_supabase()
    try:
        catalog_rows = (
            client.table("response_catalog")
            .select("*")
            .eq("id", catalog_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.exception("Failed to fetch catalog entry %s", catalog_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch catalog entry",
        ) from exc

    if not catalog_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalog entry not found",
        )
    catalog = catalog_rows[0]
    action_name = catalog["action"]

    if catalog.get("requires_approval") and not approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires explicit approval",
        )

    # Actions run without approval are auto-executed; approved actions are
    # executed with the approver recorded. (The 403 above handles
    # approval-required actions that were not approved.)
    execution_status = "executed" if approved or not catalog.get("requires_approval") else "rejected"

    try:
        response = (
            client.table("response_executions")
            .insert(
                {
                    "catalog_id": catalog_id,
                    "action_name": action_name,
                    "target": target,
                    "status": execution_status,
                    "executed_by": executed_by,
                    "approved_by": executed_by if approved else None,
                }
            )
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to record response execution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record response execution",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Response execution returned no data",
        )

    await audit_service.log_action(
        executed_by,
        executed_by,
        f"Response executed: {action_name}",
        target,
        f"Status: {execution_status}; approved: {approved}",
    )
    return rows[0]


async def get_execution_history(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent response executions, newest first."""
    try:
        response = (
            get_supabase()
            .table("response_executions")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch execution history")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch execution history",
        ) from exc
    return response.data or []
