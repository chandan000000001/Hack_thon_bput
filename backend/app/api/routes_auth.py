"""Authenticated user endpoints."""

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user

router = APIRouter(tags=["auth"])


@router.get("/auth/me")
def read_current_user(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the identity of the caller verified via Supabase Auth."""
    return {
        "id": user.id,
        "email": user.email,
        "role": "analyst",
    }
