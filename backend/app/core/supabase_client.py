"""Supabase client factory.

The backend uses a single privileged client created with the service role
key. The service role bypasses Row Level Security, so this key must never
leave the backend environment.

Phase B (multi-tenancy): also resolves which Organization a user belongs to.
The service role client reads profiles.org_id directly; a user without an
assigned organization falls back to the "Default Organization" so a brand-new
signup can never crash tenant scoping. Results are cached in memory for 5
minutes per user_id to avoid a profiles round-trip on every request.
"""

import logging
import time
from functools import lru_cache
from typing import Optional

from supabase import Client, create_client

from app.core.config import get_settings

logger = logging.getLogger("cyberguard.supabase")

DEFAULT_ORG_NAME = "Default Organization"
_ORG_CACHE_TTL_SECONDS = 300.0  # 5 minutes

# user_id -> (expires_at, org_id); module-level so it is shared across requests.
_org_cache: dict[str, tuple[float, str]] = {}
_default_org_cache: Optional[tuple[float, str]] = None


@lru_cache
def get_supabase() -> Client:
    """Return the cached singleton service-role Supabase client."""
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def check_connection() -> bool:
    """Run a lightweight count query against the events table.

    Returns True if Supabase is reachable and the table exists, else False.
    """
    try:
        get_supabase().table("events").select("id", count="exact").limit(1).execute()
        return True
    except Exception:
        return False


def _cached_value(entry: Optional[tuple[float, str]]) -> Optional[str]:
    """Return the cached value if the entry exists and has not expired."""
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        return None
    return value


def _get_default_org_id() -> str:
    """Resolve and cache the Default Organization's id (5-minute TTL)."""
    global _default_org_cache
    cached = _cached_value(_default_org_cache)
    if cached is not None:
        return cached
    response = (
        get_supabase()
        .table("organizations")
        .select("id")
        .eq("name", DEFAULT_ORG_NAME)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise RuntimeError(
            "Default Organization is missing; run db/migrations/0004_multi_tenancy.sql"
        )
    org_id = str(rows[0]["id"])
    _default_org_cache = (time.monotonic() + _ORG_CACHE_TTL_SECONDS, org_id)
    return org_id


async def get_user_org_id(user_id: str) -> str:
    """Return the organization id the user belongs to (5-minute cache).

    Queries profiles.org_id with the service-role client. When the profile is
    missing or has no org_id yet (user created before migration 0004), the
    Default Organization is returned instead, so unassigned users keep a
    valid tenant and the application never crashes on a missing org.
    """
    cache_key = str(user_id)
    cached = _cached_value(_org_cache.get(cache_key))
    if cached is not None:
        return cached

    org_id: Optional[str] = None
    try:
        response = (
            get_supabase()
            .table("profiles")
            .select("org_id")
            .eq("id", cache_key)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows and rows[0].get("org_id"):
            org_id = str(rows[0]["org_id"])
    except Exception as exc:
        logger.warning("org lookup failed for user %s: %s", cache_key, exc)

    if org_id is None:
        org_id = _get_default_org_id()

    _org_cache[cache_key] = (time.monotonic() + _ORG_CACHE_TTL_SECONDS, org_id)
    return org_id
