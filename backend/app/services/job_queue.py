"""Arq/Redis job-queue access for Phase C-1 background workers.

Heavy analysis (deepfake media, bulk log ingestion) is offloaded to an Arq
worker so the request thread returns immediately. Every helper in this module
fails soft: when Redis is unreachable the API falls back to running the same
work synchronously, so the product keeps working without a broker.
"""

import logging
import time
from typing import Any, Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

logger = logging.getLogger("cyberguard.job_queue")

_pool: Optional[ArqRedis] = None
_pool_warned = False
_pool_retry_at = 0.0  # monotonic timestamp before which we do not re-dial Redis
_CONNECT_RETRY_COOLDOWN_SECONDS = 30.0


async def get_arq_pool() -> Optional[ArqRedis]:
    """Return the cached Arq redis pool, or None when Redis is unreachable.

    The pool is created once from settings.redis_url and reused across
    requests. Connection failures log exactly one warning (no log spam on
    every request while Redis is down) and start a 30 s cooldown during which
    callers get None immediately instead of paying arq's connection-retry
    delay — the synchronous fallback must stay fast. After the cooldown the
    next call retries the connection.
    """
    global _pool, _pool_warned, _pool_retry_at
    if _pool is not None:
        return _pool
    if time.monotonic() < _pool_retry_at:
        return None
    try:
        _pool = await create_pool(
            RedisSettings.from_dsn(get_settings().REDIS_URL)
        )
        _pool_warned = False
        return _pool
    except Exception as exc:
        if not _pool_warned:
            logger.warning(
                "Redis unavailable at %s, background jobs disabled until it "
                "recovers: %s",
                get_settings().REDIS_URL,
                exc,
            )
            _pool_warned = True
        _pool_retry_at = time.monotonic() + _CONNECT_RETRY_COOLDOWN_SECONDS
        return None


async def enqueue_job(job_name: str, **kwargs: Any) -> bool:
    """Enqueue an Arq job; return True on success, False on ANY failure.

    A False return is the caller's signal to run the work synchronously on
    the request thread — never raise, so the API path cannot break because
    the queue is down.
    """
    try:
        pool = await get_arq_pool()
        if pool is None:
            raise RuntimeError("Redis pool unavailable")
        job = await pool.enqueue_job(job_name, **kwargs)
        if job is None:
            # arq returns None when an identical job is already queued —
            # treat as accepted (the work will run once).
            logger.info("Job %s already queued (deduplicated by arq)", job_name)
        return True
    except Exception as exc:
        logger.warning("Worker queue unavailable, caller must run synchronously: %s", exc)
        return False
