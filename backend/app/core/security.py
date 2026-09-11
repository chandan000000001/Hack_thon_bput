"""Authentication, role-based access control and tenant scoping.

JWT verification uses a separate anon client (the service role must never
validate end-user credentials). Authorization is decided by a database-backed
permission matrix (migration 0005): the caller's role (viewer/analyst/admin)
resolves to a set of granular permission keys via the role_permissions table,
cached in memory for 5 minutes per role. require_permission guards endpoints
by key; require_role remains as a backward-compatible alias.

Phase B (multi-tenancy): get_current_user also resolves the caller's
organization (get_user_org_id, 5-minute cache) and CurrentUser carries
org_id. Every tenant-scoped service reads current_user.org_id and filters
its queries with it — the primary isolation layer, because the service-role
client bypasses RLS.
"""

import hashlib
import logging
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import Client, create_client

from app.core.asyncbridge import to_thread
from app.core.config import get_settings
from app.core.supabase_client import get_supabase, get_user_org_id

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

# ---------------------------------------------------------------------------
# Verified-auth-context cache (Phase D-2, item 1): a verified bearer token is
# expensive (one Supabase Auth round-trip per request), so the resolved
# identity (user id + email) is cached keyed by sha256(token) for 60 s. The
# JWT itself stays the source of truth for expiry — Supabase rejects expired
# tokens and the cache TTL is far shorter than the token lifetime.
# ---------------------------------------------------------------------------
_AUTH_CONTEXT_TTL_SECONDS = 60.0
_auth_context_cache: dict[str, tuple[float, str, str | None]] = {}
# reverse index user_id -> {token_hash} so invalidate_user can clear them all
_auth_context_index: dict[str, set[str]] = {}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _auth_context_get(token: str) -> tuple[str, str | None] | None:
    entry = _auth_context_cache.get(_token_hash(token))
    if entry is None or time.monotonic() >= entry[0]:
        return None
    return entry[1], entry[2]


def _auth_context_put(token: str, user_id: str, email: str | None) -> None:
    token_key = _token_hash(token)
    _auth_context_cache[token_key] = (time.monotonic() + _AUTH_CONTEXT_TTL_SECONDS, user_id, email)
    _auth_context_index.setdefault(user_id, set()).add(token_key)


class CurrentUser(BaseModel):
    """Identity of the authenticated caller, scoped to an organization."""

    id: str
    email: str | None = None
    role: str = DEFAULT_ROLE
    org_id: str


def _get_anon_client() -> Client:
    """Create a Supabase client with the anon key for token verification."""
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Verify the bearer token against Supabase Auth and return the user.

    After the JWT is verified, the caller's organization is resolved via
    get_user_org_id (profiles.org_id, falling back to the Default
    Organization; cached 5 minutes per user). Raises 401 if the
    Authorization header is missing or the token is invalid or expired.
    """
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXCEPTION

    token = credentials.credentials

    # Phase D-2: reuse the verified identity for 60 s per token; the network
    # verification only runs on a cache miss.
    cached = _auth_context_get(token)
    if cached is not None:
        user_id, email = cached
        org_id = await get_user_org_id(user_id)
        role = await _profile_role(user_id)
        return CurrentUser(id=user_id, email=email, role=role, org_id=org_id)

    try:
        # Phase D-1: the Auth network call must not block the event loop.
        response = await to_thread(_get_anon_client().auth.get_user, token)
    except Exception as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = getattr(response, "user", None)
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    user_id = str(user.id)
    email = getattr(user, "email", None)
    _auth_context_put(token, user_id, email)
    org_id = await get_user_org_id(user_id)
    role = await _profile_role(user_id)
    return CurrentUser(id=user_id, email=email, role=role, org_id=org_id)


async def fetch_profile(user_id: str) -> dict:
    """Fetch the caller's profile row (role, full_name, email) — fail safe.

    Returns an empty dict when the profile is missing or the query fails;
    callers treat that as the default role (viewer). If the email column is
    not present yet (migration 0003 not applied), retries with role only so
    existing deployments keep working during the migration window. The
    supabase-py query runs in the threadpool (Phase D-1)."""
    try:
        response = await to_thread(
            lambda: get_supabase()
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
            response = await to_thread(
                lambda: get_supabase()
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


_PROFILE_ROLE_TTL_SECONDS = 60.0  # Phase D-2: short TTL, invalidated on role change
_profile_role_cache: dict[str, tuple[float, str]] = {}


async def _profile_role(user_id: str) -> str:
    """Resolve the caller's role; missing profile or unknown value -> viewer.

    Cached for 60 s per user (Phase D-2) and invalidated by invalidate_user()
    whenever an admin changes the user's role."""
    cached = _profile_role_cache.get(user_id)
    if cached and time.monotonic() < cached[0]:
        return cached[1]
    profile = await fetch_profile(user_id)
    role = str(profile.get("role") or DEFAULT_ROLE)
    role = role if role in ROLE_LEVELS else DEFAULT_ROLE
    _profile_role_cache[user_id] = (time.monotonic() + _PROFILE_ROLE_TTL_SECONDS, role)
    return role


def require_role(minimum_role: str):
    """Backward-compatible alias: enforce the role hierarchy (viewer < analyst < admin).

    New endpoints should use require_permission instead; this factory is kept
    so existing callers and third-party integrations keep working.
    """
    required_level = ROLE_LEVELS.get(minimum_role)
    if required_level is None:
        raise ValueError(f"Unknown role: {minimum_role!r}")

    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        role = await _profile_role(user.id)
        user.role = role
        if ROLE_LEVELS.get(role, ROLE_LEVELS[DEFAULT_ROLE]) < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {minimum_role}",
            )
        return user

    return checker


# ---------------------------------------------------------------------------
# Permission matrix (Phase C-2) — roles resolve to granular permission keys
# ---------------------------------------------------------------------------

# Same matrix as db/migrations/0005_permissions.sql. Used as a fail-safe
# fallback ONLY when the role_permissions table is unreadable or the role has
# no seeded rows (migration 0005 not applied yet) — once the migration is
# applied, the database is the single source of truth.
DEFAULT_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(
        {"dashboard.view", "alerts.view", "incidents.view", "reports.view"}
    ),
    "analyst": frozenset(
        {
            "dashboard.view",
            "alerts.view",
            "incidents.view",
            "reports.view",
            "analysis.run",
            "media.upload",
            "incident.create",
            "incident.update",
            "incident.escalate",
            "incident.close",
            "alert.acknowledge",
            "alert.resolve",
            "response.execute",
            "audit.view",
        }
    ),
    "admin": frozenset(
        {
            "dashboard.view",
            "alerts.view",
            "incidents.view",
            "reports.view",
            "analysis.run",
            "media.upload",
            "incident.create",
            "incident.update",
            "incident.escalate",
            "incident.close",
            "alert.acknowledge",
            "alert.resolve",
            "response.execute",
            "response.execute_destructive",
            "audit.view",
            "users.manage",
        }
    ),
}

_ROLE_PERMISSIONS_TTL_SECONDS = 60.0  # Phase D-2: 60 s per role
_role_permissions_cache: dict[str, tuple[float, frozenset[str]]] = {}


async def get_role_permissions(role: str) -> list[str]:
    """Return the permission keys granted to a role (5-minute cache).

    Queries the role_permissions table with the service-role client. If the
    query fails or the role has no seeded rows (migration 0005 not applied),
    the hardcoded DEFAULT_ROLE_PERMISSIONS matrix is used so the demo keeps
    working before/without the migration.
    """
    cached = _role_permissions_cache.get(role)
    if cached and time.monotonic() < cached[0]:
        return list(cached[1])

    permissions: frozenset[str]
    try:
        response = await to_thread(
            lambda: get_supabase()
            .table("role_permissions")
            .select("permission_key")
            .eq("role", role)
            .execute()
        )
        rows = response.data or []
        if rows:
            permissions = frozenset(row["permission_key"] for row in rows)
        else:
            logger.info(
                "No permission rows for role %r (migration 0005 not applied?); "
                "using the built-in default matrix",
                role,
            )
            permissions = DEFAULT_ROLE_PERMISSIONS.get(role, frozenset())
    except Exception as exc:
        logger.warning(
            "role_permissions lookup failed for role %r; using the built-in "
            "default matrix: %s",
            role,
            exc,
        )
        permissions = DEFAULT_ROLE_PERMISSIONS.get(role, frozenset())

    _role_permissions_cache[role] = (
        time.monotonic() + _ROLE_PERMISSIONS_TTL_SECONDS,
        permissions,
    )
    return list(permissions)


async def has_permission(user: CurrentUser, key: str) -> bool:
    """Check one permission for an already-authenticated user.

    Resolves the caller's actual profile role (CurrentUser.role may still be
    the default when only get_current_user ran) and tests the key against the
    cached role matrix. Used inside handlers for conditional checks such as
    the incident.close gate on the CLOSED transition.
    """
    role = await _profile_role(user.id)
    permissions = await get_role_permissions(role)
    return key in permissions


def require_permission(key: str):
    """FastAPI dependency factory enforcing one granular permission.

    Resolves the current user (JWT + org_id), loads the caller's role
    permissions, and raises 403 "Missing permission: <key>" when the key is
    not granted. The authenticated user (with role and org_id filled in) is
    injected into the route.
    """
    return require_permissions(key)


def require_permissions(*keys: str):
    """FastAPI dependency factory enforcing several granular permissions at once.

    The user, profile role and permission set are resolved exactly once per
    request (Phase D-2), so stacking requirements — e.g. analysis.run plus
    media.upload on the media endpoints — costs a single dependency instead of
    one per key. Raises 403 "Missing permission: <key>" for the first key the
    caller lacks.
    """
    if not keys:
        raise ValueError("require_permissions() needs at least one permission key")

    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user.role = await _profile_role(user.id)
        permissions = await get_role_permissions(user.role)
        for key in keys:
            if key not in permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing permission: {key}",
                )
        return user

    return dependency


def invalidate_user(user_id: str) -> None:
    """Drop every cached authorization artifact for one user (Phase D-2, item 2).

    Called after an admin changes a user's role so privilege changes take
    effect immediately instead of at cache expiry. Clears the profile-role
    cache, the verified-auth-context cache entries for that user's tokens,
    and the organization cache entry (via supabase_client).
    """
    _profile_role_cache.pop(user_id, None)
    for token_key in _auth_context_index.pop(user_id, set()):
        _auth_context_cache.pop(token_key, None)
    from app.core.supabase_client import invalidate_user_org_cache

    invalidate_user_org_cache(user_id)
    logger.info("Authorization caches invalidated for user %s", user_id)
