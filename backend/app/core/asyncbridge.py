"""Bridge for blocking work onto the threadpool (Phase D-1).

Blocking IO never runs on the event loop: any supabase-py call, Supabase Auth
network call, file IO or ELA/CNN inference invoked from an async context must
go through `to_thread`, which delegates to Starlette's threadpool (the same
mechanism FastAPI uses for `def` routes).
"""

from typing import Any, Callable

from starlette.concurrency import run_in_threadpool


async def to_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run the synchronous ``fn(*args, **kwargs)`` in the threadpool."""
    return await run_in_threadpool(fn, *args, **kwargs)
