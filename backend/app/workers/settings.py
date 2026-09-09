"""Arq worker settings — run with: arq app.workers.settings.WorkerSettings

Requires Redis reachable at settings.REDIS_URL (start it with
`docker compose up -d redis`). While the worker is down jobs simply stay
queued; the API's synchronous fallback only kicks in when Redis itself is
unreachable or BACKGROUND_WORKERS_ENABLED=false.
"""

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.workers.jobs import job_analyze_bulk_logs, job_analyze_media

async def startup(ctx: dict) -> None:
    logger = ctx.get("logger")
    if logger:
        logger.info("CYBERGUARD worker starting (redis=%s)", get_settings().REDIS_URL)


async def shutdown(ctx: dict) -> None:
    logger = ctx.get("logger")
    if logger:
        logger.info("CYBERGUARD worker shutting down")


class WorkerSettings:
    """Arq WorkerSettings consumed by the `arq` CLI."""

    functions = [job_analyze_media, job_analyze_bulk_logs]
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)
    max_jobs = 4
    job_timeout = 300
    on_startup = startup
    on_shutdown = shutdown
