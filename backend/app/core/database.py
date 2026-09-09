"""Async SQLAlchemy engine and session management (Phase A domain layer).

The engine talks to the same Postgres database that Supabase hosts, but via
asyncpg so domain logic can use ORM sessions and transactions. The supabase-py
client (app.core.supabase_client) stays responsible for Auth, Storage, and
Realtime and is unaffected by this module.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()


def _to_async_url(url: str) -> str:
    """Force the asyncpg driver onto a driver-less postgres://-style URL.

    Environments often carry DATABASE_URL in the libpq form
    (postgresql://user:pass@host/db); SQLAlchemy would try the synchronous
    psycopg2 dialect for those. Rewrite the scheme to postgresql+asyncpg while
    leaving URLs that already name a driver untouched.
    """
    scheme, sep, rest = url.partition("://")
    if sep and "+" not in scheme:
        return f"{scheme}+asyncpg://{rest}"
    return url


engine = create_async_engine(
    _to_async_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session and always closes it."""
    async with AsyncSessionLocal() as session:
        yield session
