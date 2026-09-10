"""Authenticated user endpoints (RBAC v2: role + granular permissions)."""

from fastapi import APIRouter, Depends

from app.core.security import (
    ROLE_LEVELS,
    CurrentUser,
    fetch_profile,
    get_current_user,
    get_role_permissions,
)

router = APIRouter(tags=["auth"])


@router.get("/auth/me")
async def read_current_user(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the caller's identity with role, full_name and permissions.

    Missing profile or unknown role values fall back to 'viewer'. The
    permissions list comes from the role_permissions matrix (migration 0005),
    cached 5 minutes per role on the backend.
    """
    profile = await fetch_profile(user.id)
    role = str(profile.get("role") or "viewer")
    if role not in ROLE_LEVELS:
        role = "viewer"
    permissions = await get_role_permissions(role)
    return {
        "id": user.id,
        "email": user.email,
        "role": role,
        "full_name": profile.get("full_name"),
        "permissions": permissions,
    }
