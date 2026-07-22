"""National Weather Service (api.weather.gov) lookups. No API key required.

NWS requires a two-step lookup: /points/{lat},{lon} resolves a location to
its forecast office/grid, which returns the URLs to actually call for
forecasts and nearby observation stations.
"""

import requests

from config import NWS_USER_AGENT

DC_LATITUDE = 38.9072
DC_LONGITUDE = -77.0369

NWS_API_BASE = "https://api.weather.gov"
REQUEST_HEADERS = {
    "User-Agent": NWS_USER_AGENT,
    "Accept": "application/geo+json",
}


class NwsApiError(RuntimeError):
    """Raised when the NWS API request fails."""


def _get(url: str) -> dict:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    except requests.exceptions.RequestException as e:
        raise NwsApiError(f"Failed to reach api.weather.gov: {e}") from e

    if response.status_code != 200:
        raise NwsApiError(
            f"api.weather.gov request to {url} failed with HTTP {response.status_code}."
        )

    return response.json()


def _get_point_metadata(latitude: float, longitude: float) -> dict:
    """Resolves a lat/lon to its NWS forecast and observation-station URLs."""
    point = _get(f"{NWS_API_BASE}/points/{latitude},{longitude}")
    properties = point["properties"]
    return {
        "forecast_url": properties["forecast"],
        "observation_stations_url": properties["observationStations"],
        "grid_id": properties["gridId"],
        "grid_x": properties["gridX"],
        "grid_y": properties["gridY"],
    }


def get_current_conditions(latitude: float = DC_LATITUDE, longitude: float = DC_LONGITUDE) -> dict:
    """Returns the latest observed conditions from the nearest NWS station."""
    point_metadata = _get_point_metadata(latitude, longitude)

    stations = _get(point_metadata["observation_stations_url"])
    station_features = stations.get("features") or []
    if not station_features:
        raise NwsApiError("No observation stations found near this location.")

    nearest_station = station_features[0]
    station_id = nearest_station["properties"]["stationIdentifier"]
    station_name = nearest_station["properties"]["name"]

    observation = _get(f"{NWS_API_BASE}/stations/{station_id}/observations/latest")
    props = observation["properties"]

    temperature_c = props.get("temperature", {}).get("value")
    wind_speed_kmh = props.get("windSpeed", {}).get("value")

    return {
        "station_id": station_id,
        "station_name": station_name,
        "timestamp": props.get("timestamp"),
        "description": props.get("textDescription"),
        "temperature_f": _celsius_to_fahrenheit(temperature_c),
        "wind_speed_mph": _kmh_to_mph(wind_speed_kmh),
        "wind_direction_degrees": props.get("windDirection", {}).get("value"),
        "humidity_percent": props.get("relativeHumidity", {}).get("value"),
    }


def get_forecast(periods: int = 3, latitude: float = DC_LATITUDE, longitude: float = DC_LONGITUDE) -> list[dict]:
    """Returns the next `periods` forecast periods (e.g. Today, Tonight, Tomorrow)."""
    point_metadata = _get_point_metadata(latitude, longitude)
    forecast = _get(point_metadata["forecast_url"])
    all_periods = forecast["properties"]["periods"]

    return [
        {
            "name": period["name"],
            "start_time": period["startTime"],
            "end_time": period["endTime"],
            "is_daytime": period["isDaytime"],
            "temperature": period["temperature"],
            "temperature_unit": period["temperatureUnit"],
            "wind_speed": period["windSpeed"],
            "wind_direction": period["windDirection"],
            "short_forecast": period["shortForecast"],
            "detailed_forecast": period["detailedForecast"],
            "precipitation_probability_percent": (period.get("probabilityOfPrecipitation") or {}).get("value"),
        }
        for period in all_periods[:periods]
    ]


def _celsius_to_fahrenheit(celsius):
    if celsius is None:
        return None
    return round(celsius * 9 / 5 + 32, 1)


def _kmh_to_mph(kmh):
    if kmh is None:
        return None
    return round(kmh * 0.621371, 1)


if __name__ == "__main__":
    current = get_current_conditions()
    forecast = get_forecast(periods=3)

    print("NWS weather for DC (38.9072, -77.0369):")
    print(
        f"  Current: {current['temperature_f']}°F, {current['description']} "
        f"(station {current['station_id']}, as of {current['timestamp']})"
    )
    print(f"  Forecast ({len(forecast)} periods):")
    for period in forecast:
        print(f"    {period['name']}: {period['temperature']}°{period['temperature_unit']}, {period['short_forecast']}")
