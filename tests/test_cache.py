"""Tests for the in-memory TTL cache in data/cache.py — the Cache class and
the @cached decorator, tested in isolation with no live API calls and no
dependency on wmata_realtime.py/weather.py.
"""

import time

from data.cache import Cache, cached


def test_get_returns_value_before_ttl_expires():
    cache = Cache()
    cache.set("station", "Metro Center", ttl_seconds=5)

    assert cache.get("station") == "Metro Center"


def test_get_returns_none_after_ttl_expires():
    cache = Cache()
    cache.set("station", "Metro Center", ttl_seconds=0.1)

    time.sleep(0.15)

    assert cache.get("station") is None


def test_expired_entry_is_evicted_from_store():
    cache = Cache()
    cache.set("station", "Metro Center", ttl_seconds=0.1)
    time.sleep(0.15)

    cache.get("station")  # triggers lazy eviction

    assert cache.stats()["size"] == 0


def test_get_missing_key_returns_none():
    cache = Cache()
    assert cache.get("does-not-exist") is None


def test_clear_removes_all_entries():
    cache = Cache()
    cache.set("a", 1, ttl_seconds=5)
    cache.set("b", 2, ttl_seconds=5)

    cache.clear()

    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.stats()["size"] == 0


def test_stats_tracks_hits_misses_and_size():
    cache = Cache()
    cache.set("a", 1, ttl_seconds=5)

    cache.get("a")  # hit
    cache.get("a")  # hit
    cache.get("missing")  # miss

    stats = cache.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["size"] == 1


def test_stats_counts_expiry_as_a_miss():
    cache = Cache()
    cache.set("a", 1, ttl_seconds=0.1)
    time.sleep(0.15)

    cache.get("a")

    stats = cache.stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1


def test_cached_decorator_returns_cached_value_before_ttl_expires():
    calls = []

    @cached(ttl_seconds=5)
    def slow_double(n):
        calls.append(n)
        return n * 2

    assert slow_double(3) == 6
    assert slow_double(3) == 6

    assert calls == [3]  # second call was served from cache, not recomputed


def test_cached_decorator_recomputes_after_ttl_expires():
    calls = []

    @cached(ttl_seconds=0.1)
    def slow_double(n):
        calls.append(n)
        return n * 2

    assert slow_double(3) == 6
    time.sleep(0.15)
    assert slow_double(3) == 6

    assert calls == [3, 3]  # recomputed after expiry


def test_cached_decorator_uses_different_keys_for_different_args():
    calls = []

    @cached(ttl_seconds=5)
    def slow_double(n):
        calls.append(n)
        return n * 2

    assert slow_double(3) == 6
    assert slow_double(4) == 8
    assert slow_double(3) == 6  # still cached from the first call
    assert slow_double(4) == 8  # still cached from the second call

    assert calls == [3, 4]


def test_cached_decorator_uses_different_keys_for_different_kwargs():
    calls = []

    @cached(ttl_seconds=5)
    def get_thing(station=None):
        calls.append(station)
        return f"info for {station}"

    assert get_thing(station="Metro Center") == "info for Metro Center"
    assert get_thing(station="Union Station") == "info for Union Station"
    assert get_thing(station="Metro Center") == "info for Metro Center"

    assert calls == ["Metro Center", "Union Station"]


def test_cached_decorator_exposes_underlying_cache_for_clearing():
    @cached(ttl_seconds=5)
    def slow_double(n):
        return n * 2

    slow_double(3)
    assert slow_double.cache.stats()["size"] == 1

    slow_double.cache.clear()
    assert slow_double.cache.stats()["size"] == 0
