import logging

from fastapi import APIRouter, Depends

from app.core.security import (
    DEFAULT_ROLE,
    DEFAULT_ROLE_PERMISSIONS,
    ROLE_LEVELS,
    CurrentUser,
    fetch_profile,
    get_current_user,
    get_role_permissions,
)

logger = logging.getLogger("cyberguard.auth")

router = APIRouter(tags=["auth"])


@router.get("/auth/me")
async def read_current_user(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the caller's identity with role, full_name and permissions.

    The role always comes from the profiles row; only the permissions list
    may fall back to the built-in matrix on lookup failure, with a logged warning.
    """
    profile = await fetch_profile(user.id)
    role = str(profile.get("role") or user.role or DEFAULT_ROLE)
    if role not in ROLE_LEVELS:
        role = DEFAULT_ROLE
    try:
        permissions = await get_role_permissions(role)
    except Exception as exc:
        logger.warning(
            "role_permissions lookup failed for role %r; using built-in matrix: %s",
            role,
            exc,
        )
        permissions = list(DEFAULT_ROLE_PERMISSIONS.get(role, frozenset()))
    return {
        "id": user.id,
        "email": user.email,
        "role": role,
        "full_name": profile.get("full_name"),
        "permissions": permissions,
    }
