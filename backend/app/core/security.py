"""Authentication and role-based access control (Supabase Auth + profiles).

JWT verification uses a separate anon client (the service role must never
validate end-user credentials). Authorization reads the caller's role from
the profiles table with the service role client — queried per request
(no caching), which is acceptable for the prototype.
"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import Client, create_client

from app.core.config import get_settings
from app.core.supabase_client import get_supabase

logger = logging.getLogger("cyberguard.security")

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication token",
    headers={"WWW-Authenticate": "Bearer"},
)

# Role hierarchy: a caller is allowed everything at or below their level.
ROLE_LEVELS = {"viewer": 1, "analyst": 2, "admin": 3}
DEFAULT_ROLE = "viewer"


class CurrentUser(BaseModel):
    """Identity of the authenticated caller."""

    id: str
    email: str | None = None
    role: str = DEFAULT_ROLE


def _get_anon_client() -> Client:
    """Create a Supabase client with the anon key for token verification."""
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Verify the bearer token against Supabase Auth and return the user.

    Raises 401 if the Authorization header is missing or the token is
    invalid or expired.
    """
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXCEPTION

    token = credentials.credentials
    try:
        response = _get_anon_client().auth.get_user(token)
    except Exception as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = getattr(response, "user", None)
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    return CurrentUser(
        id=str(user.id),
        email=getattr(user, "email", None),
    )


def fetch_profile(user_id: str) -> dict:
    """Fetch the caller's profile row (role, full_name, email) — fail safe.

    Returns an empty dict when the profile is missing or the query fails;
    callers treat that as the default role (viewer). If the email column is
    not present yet (migration 0003 not applied), retries with role only so
    existing deployments keep working during the migration window."""
    try:
        response = (
            get_supabase()
            .table("profiles")
            .select("role, full_name, email")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else {}
    except Exception:
        try:
            response = (
                get_supabase()
                .table("profiles")
                .select("role")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            return rows[0] if rows else {}
        except Exception as exc:
            logger.warning("profile lookup failed for %s: %s", user_id, exc)
            return {}


def _profile_role(user_id: str) -> str:
    """Resolve the caller's role; missing profile or unknown value -> viewer."""
    profile = fetch_profile(user_id)
    role = str(profile.get("role") or DEFAULT_ROLE)
    return role if role in ROLE_LEVELS else DEFAULT_ROLE


def require_role(minimum_role: str):
    """Dependency factory enforcing the role hierarchy (viewer < analyst < admin).

    The caller's role comes from the profiles table (queried per request via
    the service role client; a missing profile counts as viewer). Callers
    below the required level receive 403 "Requires role: <role>". The
    resolved CurrentUser (with the profile role) is injected into the route.
    """
    required_level = ROLE_LEVELS.get(minimum_role)
    if required_level is None:
        raise ValueError(f"Unknown role: {minimum_role!r}")

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        role = _profile_role(user.id)
        user.role = role
        if ROLE_LEVELS.get(role, ROLE_LEVELS[DEFAULT_ROLE]) < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {minimum_role}",
            )
        return user

    return checker
