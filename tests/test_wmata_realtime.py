"""Tests for the protobuf -> dict parsing logic in data/wmata_realtime.py.

Builds real gtfs_realtime_pb2.FeedMessage objects in memory, serializes them,
and feeds the bytes back through the module's requests.get seam. This
exercises the actual protobuf parsing/field-extraction code (enum decoding,
optional-field handling) without ever calling WMATA's live endpoints.
"""

import pytest
from google.transit import gtfs_realtime_pb2 as pb

from data import wmata_realtime


class FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


def _feed_message() -> pb.FeedMessage:
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1700000000
    return feed


def _mock_get_for_url(monkeypatch, url_to_content: dict):
    def fake_get(url, *args, **kwargs):
        return FakeResponse(200, url_to_content[url])

    monkeypatch.setattr(wmata_realtime, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(wmata_realtime.requests, "get", fake_get)


def test_get_vehicle_positions_parses_full_and_minimal_entities(monkeypatch):
    feed = _feed_message()

    full = feed.entity.add()
    full.id = "vehicle-1"
    full.vehicle.vehicle.id = "railcar-100"
    full.vehicle.trip.trip_id = "trip-1"
    full.vehicle.trip.route_id = "RD"
    full.vehicle.position.latitude = 38.9
    full.vehicle.position.longitude = -77.0
    full.vehicle.position.bearing = 90.0
    full.vehicle.position.speed = 12.5
    full.vehicle.current_stop_sequence = 3
    full.vehicle.stop_id = "A01"
    full.vehicle.current_status = pb.VehiclePosition.STOPPED_AT
    full.vehicle.timestamp = 1700000001

    minimal = feed.entity.add()
    minimal.id = "vehicle-2"
    minimal.vehicle.position.latitude = 38.8
    minimal.vehicle.position.longitude = -77.1
    # current_status has an implicit proto2 default (IN_TRANSIT_TO) even
    # when unset, but bearing/speed/stop_sequence/timestamp are left unset.

    _mock_get_for_url(
        monkeypatch, {wmata_realtime.VEHICLE_POSITIONS_URL: feed.SerializeToString()}
    )

    positions = wmata_realtime.get_vehicle_positions()

    assert len(positions) == 2
    full_position = positions[0]
    assert full_position == {
        "entity_id": "vehicle-1",
        "vehicle_id": "railcar-100",
        "trip_id": "trip-1",
        "route_id": "RD",
        "latitude": pytest.approx(38.9),
        "longitude": pytest.approx(-77.0),
        "bearing": pytest.approx(90.0),
        "speed": pytest.approx(12.5),
        "current_stop_sequence": 3,
        "stop_id": "A01",
        "current_status": "STOPPED_AT",
        "timestamp": 1700000001,
    }

    minimal_position = positions[1]
    assert minimal_position["vehicle_id"] is None
    assert minimal_position["trip_id"] is None
    assert minimal_position["bearing"] is None
    assert minimal_position["speed"] is None
    assert minimal_position["current_stop_sequence"] is None
    assert minimal_position["timestamp"] is None
    assert minimal_position["current_status"] == "IN_TRANSIT_TO"


def test_get_trip_updates_parses_stop_time_updates(monkeypatch):
    feed = _feed_message()

    entity = feed.entity.add()
    entity.id = "tu-1"
    entity.trip_update.trip.trip_id = "trip-1"
    entity.trip_update.trip.route_id = "RD"
    entity.trip_update.trip.start_date = "20260722"
    entity.trip_update.vehicle.id = "railcar-100"
    entity.trip_update.timestamp = 1700000002

    arrival_only = entity.trip_update.stop_time_update.add()
    arrival_only.stop_id = "A01"
    arrival_only.stop_sequence = 1
    arrival_only.arrival.delay = 30

    departure_only = entity.trip_update.stop_time_update.add()
    departure_only.stop_id = "A02"
    departure_only.stop_sequence = 2
    departure_only.departure.time = 1700000100

    _mock_get_for_url(
        monkeypatch, {wmata_realtime.TRIP_UPDATES_URL: feed.SerializeToString()}
    )

    updates = wmata_realtime.get_trip_updates()

    assert len(updates) == 1
    update = updates[0]
    assert update["trip_id"] == "trip-1"
    assert update["route_id"] == "RD"
    assert update["start_date"] == "20260722"
    assert update["schedule_relationship"] == "SCHEDULED"
    assert update["vehicle_id"] == "railcar-100"

    stop_time_updates = update["stop_time_updates"]
    assert len(stop_time_updates) == 2
    assert stop_time_updates[0]["arrival_delay"] == 30
    assert stop_time_updates[0]["departure_delay"] is None
    assert stop_time_updates[1]["departure_time"] == 1700000100
    assert stop_time_updates[1]["arrival_delay"] is None


def test_get_service_alerts_parses_text_and_scope(monkeypatch):
    feed = _feed_message()

    with_text = feed.entity.add()
    with_text.id = "alert-1"
    with_text.alert.cause = pb.Alert.MAINTENANCE
    with_text.alert.effect = pb.Alert.SIGNIFICANT_DELAYS
    with_text.alert.header_text.translation.add(text="Track work", language="en")
    with_text.alert.description_text.translation.add(
        text="Single-tracking between stations", language="en"
    )
    informed = with_text.alert.informed_entity.add()
    informed.route_id = "RD"
    informed.stop_id = "A01"
    period = with_text.alert.active_period.add()
    period.start = 1700000000
    period.end = 1700003600

    without_text = feed.entity.add()
    without_text.id = "alert-2"
    without_text.alert.cause = pb.Alert.UNKNOWN_CAUSE
    without_text.alert.effect = pb.Alert.UNKNOWN_EFFECT

    _mock_get_for_url(
        monkeypatch, {wmata_realtime.SERVICE_ALERTS_URL: feed.SerializeToString()}
    )

    alerts = wmata_realtime.get_service_alerts()

    assert len(alerts) == 2
    first = alerts[0]
    assert first["cause"] == "MAINTENANCE"
    assert first["effect"] == "SIGNIFICANT_DELAYS"
    assert first["header_text"] == "Track work"
    assert first["description_text"] == "Single-tracking between stations"
    assert first["informed_entities"] == [
        {"route_id": "RD", "stop_id": "A01", "trip_id": None}
    ]
    assert first["active_periods"] == [{"start": 1700000000, "end": 1700003600}]

    second = alerts[1]
    assert second["header_text"] is None
    assert second["description_text"] is None
    assert second["informed_entities"] == []
    assert second["active_periods"] == []


def test_fetch_feed_missing_key_raises(monkeypatch):
    monkeypatch.setattr(wmata_realtime, "WMATA_API_KEY", "")

    with pytest.raises(wmata_realtime.WmataRealtimeError, match="WMATA_API_KEY"):
        wmata_realtime.get_vehicle_positions()


def test_fetch_feed_invalid_key_raises(monkeypatch):
    monkeypatch.setattr(wmata_realtime, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(
        wmata_realtime.requests, "get", lambda *a, **k: FakeResponse(403, b"")
    )

    with pytest.raises(wmata_realtime.WmataRealtimeError, match="HTTP 403"):
        wmata_realtime.get_trip_updates()


def test_fetch_feed_bad_protobuf_raises(monkeypatch):
    # Simulates WMATA's response changing shape (e.g. an HTML error page
    # returned with a 200 status) so the bytes aren't valid protobuf.
    monkeypatch.setattr(wmata_realtime, "WMATA_API_KEY", "fake-key")
    monkeypatch.setattr(
        wmata_realtime.requests,
        "get",
        lambda *a, **k: FakeResponse(200, b"<html>not protobuf</html>"),
    )

    with pytest.raises(wmata_realtime.WmataRealtimeError, match="Could not parse"):
        wmata_realtime.get_service_alerts()
