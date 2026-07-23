"""Thin in-memory TTL cache for live API responses (WMATA, NWS), so the team
isn't hammering those during development/demo. No background thread —
expired entries are just evicted lazily, on the next get() that finds them.
"""

import functools
import time


class Cache:
    """A dict-backed cache where each entry has its own TTL."""

    def __init__(self):
        self._store = {}
        self._hits = 0
        self._misses = 0

    def get(self, key):
        """Returns the cached value for `key`, or None if missing/expired."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key, value, ttl_seconds):
        self._store[key] = (value, time.monotonic() + ttl_seconds)

    def clear(self):
        self._store.clear()

    def stats(self) -> dict:
        """Returns cumulative hit/miss counts plus the current entry count.

        Hit/miss counts aren't reset by clear() — they're meant to show
        cache effectiveness over the process's lifetime (e.g. for a demo),
        not just the current contents.
        """
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
        }


def _make_key(func, args, kwargs):
    return f"{func.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"


def cached(ttl_seconds):
    """Decorator that caches a function's return value for `ttl_seconds`.

    The cache key is the function's name plus its arguments, so calls with
    different arguments are cached separately. Note: like Cache.get(), a
    function that legitimately returns None is treated as a cache miss on
    every call — not a correctness issue here (WMATA/NWS calls return dicts
    or lists, never None), just a limitation worth knowing before reusing
    this on something that returns None.
    """

    def decorator(func):
        cache = Cache()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(func, args, kwargs)
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value

            result = func(*args, **kwargs)
            cache.set(key, result, ttl_seconds)
            return result

        wrapper.cache = cache  # exposed so callers/tests can inspect or clear it
        return wrapper

    return decorator


if __name__ == "__main__":
    print("--- Cache class demo ---")
    cache = Cache()
    cache.set("station", "Metro Center", ttl_seconds=1)
    print("immediately after set:", cache.get("station"))
    time.sleep(1.2)
    print("after ttl expires:", cache.get("station"))
    cache.set("station", "Union Station", ttl_seconds=10)
    cache.clear()
    print("after clear():", cache.get("station"))

    print("\n--- @cached decorator demo ---")

    @cached(ttl_seconds=2)
    def slow_square(n):
        time.sleep(1)
        return n * n

    start = time.perf_counter()
    print("first call (uncached):", slow_square(4), f"({time.perf_counter() - start:.2f}s)")

    start = time.perf_counter()
    print("second call (cached):", slow_square(4), f"({time.perf_counter() - start:.2f}s)")

    start = time.perf_counter()
    print("different args (uncached):", slow_square(5), f"({time.perf_counter() - start:.2f}s)")

    print("waiting for ttl to expire...")
    time.sleep(2.1)

    start = time.perf_counter()
    print("after ttl expires (uncached again):", slow_square(4), f"({time.perf_counter() - start:.2f}s)")

    print("\nstats:", slow_square.cache.stats())
