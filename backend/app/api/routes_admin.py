"""Admin user-management endpoints (RBAC completion).

All endpoints require the admin role. Emails live on the profiles table
(migration 0003 adds the column and the trigger populates it), because the
service role REST API cannot query auth.users directly.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.asyncbridge import to_thread
from app.core.security import CurrentUser, invalidate_user, require_permission
from app.core.supabase_client import get_supabase
from app.services import audit_service

router = APIRouter(prefix="/admin", tags=["Admin"])


class RoleUpdate(BaseModel):
    role: Literal["viewer", "analyst", "admin"]


@router.get("/users")
async def list_users(_admin: CurrentUser = Depends(require_permission("users.manage"))) -> list[dict[str, Any]]:
    """List all user profiles, oldest first."""
    try:
        response = await to_thread(
            lambda: get_supabase()
            .table("profiles")
            .select("id, email, full_name, role, created_at")
            .order("created_at", desc=False)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users",
        ) from exc
    return response.data or []


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: RoleUpdate,
    admin: CurrentUser = Depends(require_permission("users.manage")),
) -> dict[str, Any]:
    """Change a user's role; audit-logged.

    Self-demote protection: an admin cannot lower their own role, which
    would lock them out of /admin endpoints."""
    if user_id == admin.id and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot change their own role (lockout prevention)",
        )

    client = get_supabase()
    try:
        response = await to_thread(
            lambda: client.table("profiles").update({"role": payload.role}).eq("id", user_id).execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Phase D-2: privilege change takes effect immediately — drop the target
    # user's cached role, permissions-bearing auth context and org resolution.
    invalidate_user(user_id)

    await audit_service.log_action(
        admin.id,
        admin.email or admin.id,
        "role_changed",
        f"profile:{user_id}",
        f"Role set to {payload.role}",
    )
    return rows[0]
