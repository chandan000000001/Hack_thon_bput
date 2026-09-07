"""Authentication dependencies backed by Supabase Auth.

Protected routes use ``get_current_user`` to verify a bearer JWT with
Supabase Auth. Token verification uses a separate anon client because the
service role must never be used to validate end-user credentials.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import Client, create_client

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication token",
    headers={"WWW-Authenticate": "Bearer"},
)


class CurrentUser(BaseModel):
    """Identity of the authenticated caller."""

    id: str
    email: str | None = None
    role: str = "analyst"


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


def require_role(role: str):
    """Return a dependency enforcing a specific role.

    Role-based access control is enforced in later parts of the build;
    for now every authenticated user passes.
    """

    def _checker(user: CurrentUser = Depends(get_current_user)) -> bool:
        # Placeholder policy: all authenticated users are authorized.
        # Role enforcement will compare the caller's profile role with `role`.
        _ = role
        return True

    return _checker
