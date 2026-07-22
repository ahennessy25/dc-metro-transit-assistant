"""Tests for the GTFS zip-parsing logic in data/wmata_static.py.

These mock the network layer (requests.get) and exercise the real
extract-and-load code against an in-memory zip, so they catch things like
a renamed column or a missing file in the feed without ever hitting WMATA.
"""

import io
import zipfile

import pytest

from data import wmata_static

STOPS_CSV = "stop_id,stop_name,stop_lat,stop_lon\nA01,Metro Center,38.898,-77.028\n"
ROUTES_CSV = "route_id,route_long_name,route_color\nRD,Red Line,BE4B48\n"
TRIPS_CSV = "route_id,service_id,trip_id\nRD,1,trip-1\n"
STOP_TIMES_CSV = (
    "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
    "trip-1,08:00:00,08:00:30,A01,1\n"
)


def _build_gtfs_zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


@pytest.fixture
def valid_zip_bytes():
    return _build_gtfs_zip(
        {
            "stops.txt": STOPS_CSV,
            "routes.txt": ROUTES_CSV,
            "trips.txt": TRIPS_CSV,
            "stop_times.txt": STOP_TIMES_CSV,
        }
    )


def test_fetch_gtfs_static_loads_expected_dataframes(monkeypatch, valid_zip_bytes):
    monkeypatch.setattr(wmata_static, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(
        wmata_static.requests,
        "get",
        lambda *a, **k: FakeResponse(200, valid_zip_bytes),
    )

    dataframes = wmata_static.fetch_gtfs_static()

    assert set(dataframes.keys()) == {"stops", "routes", "trips", "stop_times"}
    assert len(dataframes["stops"]) == 1
    assert len(dataframes["routes"]) == 1
    assert len(dataframes["trips"]) == 1
    assert len(dataframes["stop_times"]) == 1
    assert dataframes["stops"].loc[0, "stop_name"] == "Metro Center"


def test_fetch_gtfs_static_keeps_ids_as_strings(monkeypatch, valid_zip_bytes):
    # GTFS IDs like route_id/stop_id are numeric-looking strings; a naive
    # pandas.read_csv without dtype=str would silently coerce these to ints
    # and break downstream string-based joins/lookups.
    monkeypatch.setattr(wmata_static, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(
        wmata_static.requests,
        "get",
        lambda *a, **k: FakeResponse(200, valid_zip_bytes),
    )

    dataframes = wmata_static.fetch_gtfs_static()

    assert isinstance(dataframes["stops"].loc[0, "stop_id"], str)
    assert dataframes["stops"].loc[0, "stop_id"] == "A01"


def test_fetch_gtfs_static_missing_key_raises(monkeypatch):
    monkeypatch.setattr(wmata_static, "WMATA_API_KEY", "")

    with pytest.raises(wmata_static.WmataGtfsDownloadError, match="WMATA_API_KEY"):
        wmata_static.fetch_gtfs_static()


def test_fetch_gtfs_static_invalid_key_raises(monkeypatch):
    monkeypatch.setattr(wmata_static, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(
        wmata_static.requests, "get", lambda *a, **k: FakeResponse(401, b"")
    )

    with pytest.raises(wmata_static.WmataGtfsDownloadError, match="HTTP 401"):
        wmata_static.fetch_gtfs_static()


def test_fetch_gtfs_static_bad_zip_raises(monkeypatch):
    monkeypatch.setattr(wmata_static, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(
        wmata_static.requests,
        "get",
        lambda *a, **k: FakeResponse(200, b"this is not a zip file"),
    )

    with pytest.raises(wmata_static.WmataGtfsDownloadError, match="not a valid GTFS zip"):
        wmata_static.fetch_gtfs_static()


def test_fetch_gtfs_static_missing_file_in_feed_raises(monkeypatch):
    # Simulates WMATA dropping/renaming a file in the feed.
    monkeypatch.setattr(wmata_static, "WMATA_API_KEY", "fake-key")
    incomplete_zip = _build_gtfs_zip(
        {"stops.txt": STOPS_CSV, "routes.txt": ROUTES_CSV, "trips.txt": TRIPS_CSV}
    )
    monkeypatch.setattr(
        wmata_static.requests, "get", lambda *a, **k: FakeResponse(200, incomplete_zip)
    )

    with pytest.raises(wmata_static.WmataGtfsDownloadError, match="stop_times.txt"):
        wmata_static.fetch_gtfs_static()
