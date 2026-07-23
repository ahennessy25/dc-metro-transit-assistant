"""Shared pytest fixtures."""

import pytest

from data import weather, wmata_realtime


@pytest.fixture(autouse=True)
def _clear_cached_function_caches():
    """Clears @cached()'s per-function caches before every test.

    Without this, a test that successfully caches a result (e.g. a
    successful get_vehicle_positions() call) would leak that cached value
    into a later test expecting a different mocked response or an error —
    the TTLs (30s-15min) far outlast a single test run.
    """
    wmata_realtime.get_vehicle_positions.cache.clear()
    wmata_realtime.get_trip_updates.cache.clear()
    wmata_realtime.get_service_alerts.cache.clear()
    weather.get_current_conditions.cache.clear()
    weather.get_forecast.cache.clear()
