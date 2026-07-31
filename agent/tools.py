"""Tool schemas (Anthropic Messages API format) and dispatch map for the
Week 2 tool-calling agent.

The five tools here match the planned agent interface from CLAUDE.md
(get_scheduled_times, get_real_time_arrivals, get_service_alerts, get_weather,
search_station_info). Only search_station_info exists with that exact
signature already (data/rag_index.py); the other four are thin adapters
around functions that exist under different names/shapes:

- get_scheduled_times(route, stop) adapts data/wmata_static.fetch_gtfs_static(),
  which returns raw DataFrames, not a route/stop-filtered lookup.
- get_real_time_arrivals(station) adapts data/wmata_realtime.get_trip_updates(),
  which returns all trips' predictions unfiltered by station.
- get_service_alerts(line=None) adapts data/wmata_realtime.get_service_alerts(),
  which takes no arguments and returns all alerts unfiltered.
- get_weather(when="now") adapts data/weather's two separate functions,
  get_current_conditions() and get_forecast(), into one when-dispatched call.

This file does NOT build the agent loop — just the schemas and TOOL_FUNCTIONS
dispatch map.
"""

import time

import pandas as pd

from data.rag_index import search_station_info
from data.wmata_realtime import get_service_alerts as _get_all_service_alerts
from data.wmata_realtime import get_trip_updates
from data.wmata_static import fetch_gtfs_static
from data.weather import get_current_conditions, get_forecast

# Static GTFS rarely changes and fetch_gtfs_static() is expensive (downloads
# + unzips + parses ~400k rows), so it's loaded once per process and reused,
# rather than re-fetched on every tool call. Restart the process to pick up
# a newer feed.
_static_data = None


def _get_static_data():
    global _static_data
    if _static_data is None:
        _static_data = fetch_gtfs_static()
    return _static_data


def _match_route_ids(route_query, routes_df):
    """Matches a user-supplied route string against route_id, the
    single-letter route_short_name, or route_long_name (e.g. "RED", "R",
    "Red", and "Red Line" all match the RED line).
    """
    query = route_query.strip().lower().replace("line", "").strip()
    matches = routes_df[
        (routes_df["route_id"].str.lower() == query)
        | (routes_df["route_short_name"].str.lower() == query)
        | (routes_df["route_long_name"].str.lower() == query)
    ]
    return set(matches["route_id"])


def _match_station_stop_ids(station_query, stops_df):
    """Matches a user-supplied station name against platform-level stops
    (location_type "0") — the level stop_times.txt and GTFS-RT actually key
    on — by case-insensitive substring, so "metro center" matches
    "Metro Center, Red Line Track 1 Platform" etc.
    """
    query = station_query.strip().lower()
    platform_stops = stops_df[stops_df["location_type"] == "0"]
    matches = platform_stops[platform_stops["stop_name"].str.lower().str.contains(query, regex=False)]
    return set(matches["stop_id"])


def _first_and_last(stop_times_df, n=8):
    """Returns up to `n` earliest and `n` latest rows (by arrival_time).

    A plain .head(n) on a full day's schedule only ever returns the first
    trains of service — a "what time's the last train" question can never
    be answered from that, since the answer is truncated away before it
    gets there. Sampling both ends keeps the result compact while covering
    both first-train and last-train questions from a single call.
    """
    if len(stop_times_df) <= 2 * n:
        return stop_times_df
    return pd.concat([stop_times_df.head(n), stop_times_df.tail(n)])


def get_scheduled_times(route, stop):
    """Static (published) scheduled times for a route+stop, from GTFS."""
    data = _get_static_data()

    route_ids = _match_route_ids(route, data["routes"])
    if not route_ids:
        return [{"message": f"No Metrorail line matching '{route}'."}]

    stop_ids = _match_station_stop_ids(stop, data["stops"])
    if not stop_ids:
        return [{"message": f"No station matching '{stop}'."}]

    trip_ids = set(data["trips"][data["trips"]["route_id"].isin(route_ids)]["trip_id"])

    matching_stop_times = (
        data["stop_times"][
            data["stop_times"]["trip_id"].isin(trip_ids) & data["stop_times"]["stop_id"].isin(stop_ids)
        ]
        # Multiple service_id calendars (weekday/Saturday/Sunday variants,
        # etc.) often share the same clock time — collapse those down to
        # one row per distinct time rather than showing near-identical
        # duplicates.
        .drop_duplicates(subset=["arrival_time", "departure_time"])
        .sort_values("arrival_time")
    )

    if matching_stop_times.empty:
        return [{"message": f"No scheduled times found for '{route}' at '{stop}'."}]

    route_id_by_trip = dict(zip(data["trips"]["trip_id"], data["trips"]["route_id"]))
    return [
        {
            "route": route_id_by_trip.get(row["trip_id"]),
            "stop": stop,
            "arrival_time": row["arrival_time"],
            "departure_time": row["departure_time"],
        }
        for _, row in _first_and_last(matching_stop_times).iterrows()
    ]


def get_real_time_arrivals(station):
    """Live predicted arrivals at a station, from GTFS-Realtime trip updates."""
    data = _get_static_data()
    stop_ids = _match_station_stop_ids(station, data["stops"])
    if not stop_ids:
        return [{"message": f"No station matching '{station}'."}]

    now = time.time()
    arrivals = []
    for trip_update in get_trip_updates():
        for stop_time_update in trip_update["stop_time_updates"]:
            if stop_time_update["stop_id"] not in stop_ids:
                continue

            predicted_time = stop_time_update["arrival_time"] or stop_time_update["departure_time"]
            if predicted_time is None:
                continue
            minutes_until_arrival = round((predicted_time - now) / 60, 1)
            if minutes_until_arrival < 0:
                # Trip already served this stop — the feed doesn't always
                # prune past stops from a trip's remaining schedule, but
                # it's not a genuine upcoming arrival.
                continue

            arrivals.append(
                {
                    "route": trip_update["route_id"],
                    "station": station,
                    "trip_id": trip_update["trip_id"],
                    "minutes_until_arrival": minutes_until_arrival,
                }
            )

    if not arrivals:
        return [{"message": f"No live arrival predictions found for '{station}' right now."}]

    arrivals.sort(key=lambda a: a["minutes_until_arrival"])
    return arrivals[:10]


def get_service_alerts(line=None):
    """Active service alerts, optionally filtered to one Metrorail line."""
    all_alerts = _get_all_service_alerts()

    if line is None:
        return all_alerts

    data = _get_static_data()
    route_ids = _match_route_ids(line, data["routes"])
    if not route_ids:
        return [{"message": f"No Metrorail line matching '{line}'."}]

    return [
        alert
        for alert in all_alerts
        if not alert["informed_entities"]  # systemwide alerts apply to every line
        or any(entity["route_id"] in route_ids for entity in alert["informed_entities"])
    ]


def get_weather(when="now"):
    """Current conditions if when="now", otherwise a short forecast."""
    if when.strip().lower() in ("now", "current", "currently"):
        return get_current_conditions()
    return get_forecast(periods=3)


TOOL_SCHEMAS = [
    {
        "name": "get_scheduled_times",
        "description": (
            "Look up WMATA Metrorail's static (pre-published) scheduled arrival and departure "
            "times for a specific route and stop, from the official GTFS schedule — not live/"
            "real-time data. Use this for questions about the planned schedule (e.g. 'what time "
            "does the Red Line usually run at Metro Center', 'what's the first train in the "
            "morning', 'when's the last train'), NOT for 'when is the next train arriving right "
            "now' — use get_real_time_arrivals for that instead. Returns only a sample of the "
            "day's scheduled times (the first several and last several), not the full schedule "
            "— it will have first-train and last-train times, but may not have a specific "
            "midday time the user asks about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "description": (
                        "The Metrorail line to look up, as either its route ID (e.g. 'RED', "
                        "'BLUE', 'ORANGE', 'SILVER', 'GREEN', 'YELLOW') or full name (e.g. "
                        "'Red Line', 'Red'). Matching is case-insensitive."
                    ),
                },
                "stop": {
                    "type": "string",
                    "description": (
                        "The station name to look up scheduled times for (e.g. 'Metro Center', "
                        "'Union Station'). Matches by partial, case-insensitive station name — "
                        "the full official platform name isn't required."
                    ),
                },
            },
            "required": ["route", "stop"],
        },
    },
    {
        "name": "get_real_time_arrivals",
        "description": (
            "Get live, real-time predicted train arrival times for a specific Metrorail "
            "station, from WMATA's GTFS-Realtime feed — reflects current train positions and "
            "delays, not the static schedule. Use this for 'when is the next train' or 'how "
            "many minutes until the next train at X' questions. For the official published "
            "schedule instead of live predictions, use get_scheduled_times instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "station": {
                    "type": "string",
                    "description": (
                        "The station name to get live arrival predictions for (e.g. 'Metro "
                        "Center', 'Dupont Circle'). Matches by partial, case-insensitive "
                        "station name."
                    ),
                },
            },
            "required": ["station"],
        },
    },
    {
        "name": "get_service_alerts",
        "description": (
            "Get currently active WMATA Metrorail service alerts — delays, single-tracking, "
            "station closures, and other disruptions — from the live GTFS-Realtime alerts "
            "feed. Optionally filter to a single line; omit to get all active alerts "
            "systemwide. Use this for questions like 'is the Red Line running normally', 'are "
            "there any delays', or 'is anything closed right now'. This is NOT for station "
            "accessibility info like elevator outages history — use search_station_info for "
            "that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "line": {
                    "type": "string",
                    "description": (
                        "Restrict results to alerts affecting this Metrorail line only, as its "
                        "route ID (e.g. 'RED', 'BLUE') or full name (e.g. 'Red Line'). Omit "
                        "this parameter entirely to return all active alerts, including "
                        "systemwide ones."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get current DC-area weather conditions or a short forecast from the National "
            "Weather Service, for commute-relevant weather questions (e.g. 'is it raining "
            "right now', 'what's the weather looking like for tomorrow morning's commute'). "
            "Pass when='now' for current observed conditions; pass anything else (e.g. "
            "'today', 'tomorrow', 'this weekend') to get a short multi-period forecast "
            "instead. This is DC weather only, not transit status — use get_service_alerts "
            "for train delays."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "when": {
                    "type": "string",
                    "description": (
                        "'now' for current observed conditions at the nearest DC-area station "
                        "(the default); any other value (e.g. 'today', 'tomorrow', 'later') "
                        "returns a short forecast covering the next few periods instead."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_station_info",
        "description": (
            "Semantic search over descriptive, non-live Metrorail text: station accessibility "
            "notes (elevators, entrances, wheelchair access), historical service alert "
            "descriptions, and trip-planning FAQ content (fares, bike policy, bus transfers). "
            "This is NOT for live/current data — do NOT use this for current alerts, "
            "arrivals, or weather; use get_service_alerts, get_real_time_arrivals, or "
            "get_weather for those instead. Use this for questions like 'is there an elevator "
            "at Dupont Circle' or 'how do Metrorail-to-bus transfers work'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A natural-language question or phrase to search for, e.g. "
                        "'wheelchair access at Dupont Circle' or 'bike policy on Metrorail'."
                    ),
                },
            },
            "required": ["query"],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_scheduled_times": get_scheduled_times,
    "get_real_time_arrivals": get_real_time_arrivals,
    "get_service_alerts": get_service_alerts,
    "get_weather": get_weather,
    "search_station_info": search_station_info,
}
