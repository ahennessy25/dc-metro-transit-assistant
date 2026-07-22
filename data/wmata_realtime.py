"""Fetches and parses WMATA's GTFS-Realtime feeds for Metrorail.

The feeds are protobuf (google.transit.gtfs_realtime_pb2.FeedMessage), not
JSON. Each public function here parses the protobuf and returns plain
Python dicts, so the rest of the app never has to import gtfs_realtime_pb2
or know protobuf field names.
"""

import requests
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from config import WMATA_API_KEY

VEHICLE_POSITIONS_URL = "https://api.wmata.com/gtfs/rail-gtfsrt-vehiclepositions.pb"
TRIP_UPDATES_URL = "https://api.wmata.com/gtfs/rail-gtfsrt-tripupdates.pb"
SERVICE_ALERTS_URL = "https://api.wmata.com/gtfs/rail-gtfsrt-alerts.pb"


class WmataRealtimeError(RuntimeError):
    """Raised when a WMATA GTFS-Realtime feed can't be fetched or parsed."""


def _fetch_feed(url: str) -> gtfs_realtime_pb2.FeedMessage:
    if not WMATA_API_KEY:
        raise WmataRealtimeError(
            "WMATA_API_KEY is not set. Add it to .env (see .env.example)."
        )

    try:
        response = requests.get(
            url,
            headers={"api_key": WMATA_API_KEY},
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        raise WmataRealtimeError(f"Failed to reach WMATA API: {e}") from e

    if response.status_code in (401, 403):
        raise WmataRealtimeError(
            f"WMATA API rejected the request (HTTP {response.status_code}) — "
            "check that WMATA_API_KEY is valid and not expired."
        )
    if response.status_code != 200:
        raise WmataRealtimeError(
            f"WMATA API request failed with HTTP {response.status_code}."
        )

    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(response.content)
    except DecodeError as e:
        raise WmataRealtimeError(
            "Could not parse GTFS-Realtime response as protobuf — the WMATA "
            "API key may be invalid or the response was an error page."
        ) from e

    return feed


def _enum_name(enum_wrapper, value) -> str:
    try:
        return enum_wrapper.Name(value)
    except ValueError:
        return str(value)


def get_vehicle_positions() -> list[dict]:
    """Returns current Metrorail train positions as a list of dicts."""
    feed = _fetch_feed(VEHICLE_POSITIONS_URL)

    positions = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle

        positions.append(
            {
                "entity_id": entity.id,
                "vehicle_id": vehicle.vehicle.id or None,
                "trip_id": vehicle.trip.trip_id or None,
                "route_id": vehicle.trip.route_id or None,
                "latitude": vehicle.position.latitude,
                "longitude": vehicle.position.longitude,
                "bearing": vehicle.position.bearing if vehicle.position.HasField("bearing") else None,
                "speed": vehicle.position.speed if vehicle.position.HasField("speed") else None,
                "current_stop_sequence": vehicle.current_stop_sequence if vehicle.HasField("current_stop_sequence") else None,
                "stop_id": vehicle.stop_id or None,
                "current_status": _enum_name(gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus, vehicle.current_status),
                "timestamp": vehicle.timestamp if vehicle.HasField("timestamp") else None,
            }
        )

    return positions


def get_trip_updates() -> list[dict]:
    """Returns Metrorail trip updates (predicted stop arrivals/departures) as a list of dicts."""
    feed = _fetch_feed(TRIP_UPDATES_URL)

    updates = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update

        stop_time_updates = []
        for stu in trip_update.stop_time_update:
            stop_time_updates.append(
                {
                    "stop_id": stu.stop_id or None,
                    "stop_sequence": stu.stop_sequence if stu.HasField("stop_sequence") else None,
                    "arrival_delay": stu.arrival.delay if stu.HasField("arrival") and stu.arrival.HasField("delay") else None,
                    "arrival_time": stu.arrival.time if stu.HasField("arrival") and stu.arrival.HasField("time") else None,
                    "departure_delay": stu.departure.delay if stu.HasField("departure") and stu.departure.HasField("delay") else None,
                    "departure_time": stu.departure.time if stu.HasField("departure") and stu.departure.HasField("time") else None,
                    "schedule_relationship": _enum_name(
                        gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship, stu.schedule_relationship
                    ),
                }
            )

        updates.append(
            {
                "entity_id": entity.id,
                "trip_id": trip_update.trip.trip_id or None,
                "route_id": trip_update.trip.route_id or None,
                "start_date": trip_update.trip.start_date or None,
                "schedule_relationship": _enum_name(
                    gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship, trip_update.trip.schedule_relationship
                ),
                "vehicle_id": trip_update.vehicle.id or None,
                "timestamp": trip_update.timestamp if trip_update.HasField("timestamp") else None,
                "stop_time_updates": stop_time_updates,
            }
        )

    return updates


def get_service_alerts() -> list[dict]:
    """Returns active Metrorail service alerts as a list of dicts."""
    feed = _fetch_feed(SERVICE_ALERTS_URL)

    alerts = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert

        informed_entities = []
        for informed in alert.informed_entity:
            informed_entities.append(
                {
                    "route_id": informed.route_id or None,
                    "stop_id": informed.stop_id or None,
                    "trip_id": informed.trip.trip_id or None,
                }
            )

        active_periods = []
        for period in alert.active_period:
            active_periods.append(
                {
                    "start": period.start if period.HasField("start") else None,
                    "end": period.end if period.HasField("end") else None,
                }
            )

        alerts.append(
            {
                "entity_id": entity.id,
                "cause": _enum_name(gtfs_realtime_pb2.Alert.Cause, alert.cause),
                "effect": _enum_name(gtfs_realtime_pb2.Alert.Effect, alert.effect),
                "header_text": _first_translation(alert.header_text),
                "description_text": _first_translation(alert.description_text),
                "informed_entities": informed_entities,
                "active_periods": active_periods,
            }
        )

    return alerts


def _first_translation(translated_string) -> str | None:
    if not translated_string.translation:
        return None
    return translated_string.translation[0].text


if __name__ == "__main__":
    vehicle_positions = get_vehicle_positions()
    trip_updates = get_trip_updates()
    service_alerts = get_service_alerts()

    print("WMATA GTFS-Realtime feeds loaded:")
    print(f"  Active vehicles: {len(vehicle_positions)}")
    print(f"  Trip updates: {len(trip_updates)}")
    print(f"  Active alerts: {len(service_alerts)}")
