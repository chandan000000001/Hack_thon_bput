"""Supabase client factory.

The backend uses a single privileged client created with the service role
key. The service role bypasses Row Level Security, so this key must never
leave the backend environment.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


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
