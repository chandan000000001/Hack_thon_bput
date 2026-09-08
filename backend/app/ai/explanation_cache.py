"""Thread-safe in-memory LRU cache for LLM explanations.

Keys are sha256 hex strings (see llm_gateway.make_cache_key). Entries expire
after their TTL and expired entries are evicted lazily on access. At most
_MAX_ENTRIES entries are retained; the least-recently-used entry is evicted
first. This bounds worst-case memory regardless of traffic.
"""

import threading
import time
from collections import OrderedDict

_MAX_ENTRIES = 256
DEFAULT_TTL_SECONDS = 3600

_lock = threading.Lock()
_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()


def get(key: str) -> dict | None:
    """Return the cached value for key, or None if missing/expired."""
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if now >= expires_at:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return value


def set(key: str, value: dict, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    """Insert/refresh a cache entry with the given TTL and enforce the LRU cap."""
    with _lock:
        _cache[key] = (time.monotonic() + ttl, value)
        _cache.move_to_end(key)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
