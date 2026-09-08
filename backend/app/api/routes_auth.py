"""Authenticated user endpoints (role-aware since the RBAC completion)."""

from fastapi import APIRouter, Depends

from app.core.security import ROLE_LEVELS, CurrentUser, fetch_profile, get_current_user

router = APIRouter(tags=["auth"])


@router.get("/auth/me")
def read_current_user(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the caller's identity with role and full_name from profiles.

    Missing profile or unknown role values fall back to 'viewer'."""
    profile = fetch_profile(user.id)
    role = str(profile.get("role") or "viewer")
    if role not in ROLE_LEVELS:
        role = "viewer"
    return {
        "id": user.id,
        "email": user.email,
        "role": role,
        "full_name": profile.get("full_name"),
    }
