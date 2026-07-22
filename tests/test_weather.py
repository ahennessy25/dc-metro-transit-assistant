"""Tests for the unit-conversion and response-shaping logic in data/weather.py.

Mocks requests.get (keyed by URL) to return canned NWS JSON payloads, so the
real two-step lookup and dict-building code runs, but no live network call
happens. Also covers the C->F / km/h->mph conversions directly, since NWS
returns metric units that are easy to get subtly wrong.
"""

import pytest

from data import weather

POINTS_RESPONSE = {
    "properties": {
        "forecast": "https://api.weather.gov/gridpoints/LWX/97,71/forecast",
        "observationStations": "https://api.weather.gov/gridpoints/LWX/97,71/stations",
        "gridId": "LWX",
        "gridX": 97,
        "gridY": 71,
    }
}

STATIONS_RESPONSE = {
    "features": [
        {
            "properties": {
                "stationIdentifier": "KDCA",
                "name": "Washington Reagan National Airport",
            }
        }
    ]
}

OBSERVATION_RESPONSE = {
    "properties": {
        "timestamp": "2026-07-22T12:00:00+00:00",
        "textDescription": "Mostly Cloudy",
        "temperature": {"value": 25.0},
        "windSpeed": {"value": 10.0},
        "windDirection": {"value": 180},
        "relativeHumidity": {"value": 60.5},
    }
}

FORECAST_RESPONSE = {
    "properties": {
        "periods": [
            {
                "name": "Today",
                "startTime": "2026-07-22T06:00:00-04:00",
                "endTime": "2026-07-22T18:00:00-04:00",
                "isDaytime": True,
                "temperature": 88,
                "temperatureUnit": "F",
                "windSpeed": "5 mph",
                "windDirection": "SW",
                "shortForecast": "Sunny",
                "detailedForecast": "Sunny, with a high near 88.",
                "probabilityOfPrecipitation": {"value": 10},
            },
            {
                "name": "Tonight",
                "startTime": "2026-07-22T18:00:00-04:00",
                "endTime": "2026-07-23T06:00:00-04:00",
                "isDaytime": False,
                "temperature": 70,
                "temperatureUnit": "F",
                "windSpeed": "5 mph",
                "windDirection": "SW",
                "shortForecast": "Clear",
                "detailedForecast": "Clear, with a low around 70.",
                "probabilityOfPrecipitation": None,
            },
            {
                "name": "Wednesday",
                "startTime": "2026-07-23T06:00:00-04:00",
                "endTime": "2026-07-23T18:00:00-04:00",
                "isDaytime": True,
                "temperature": 90,
                "temperatureUnit": "F",
                "windSpeed": "5 mph",
                "windDirection": "SW",
                "shortForecast": "Sunny",
                "detailedForecast": "Sunny, with a high near 90.",
                "probabilityOfPrecipitation": {"value": 0},
            },
            {
                "name": "Wednesday Night",
                "startTime": "2026-07-23T18:00:00-04:00",
                "endTime": "2026-07-24T06:00:00-04:00",
                "isDaytime": False,
                "temperature": 72,
                "temperatureUnit": "F",
                "windSpeed": "5 mph",
                "windDirection": "SW",
                "shortForecast": "Clear",
                "detailedForecast": "Clear.",
                "probabilityOfPrecipitation": None,
            },
        ]
    }
}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def _mock_get_by_url(monkeypatch, responses: dict):
    def fake_get(url, *args, **kwargs):
        for prefix, payload in responses.items():
            if url.startswith(prefix):
                return FakeResponse(200, payload)
        raise AssertionError(f"Unexpected URL requested: {url}")

    monkeypatch.setattr(weather.requests, "get", fake_get)


def test_get_current_conditions_converts_units_and_shapes_dict(monkeypatch):
    _mock_get_by_url(
        monkeypatch,
        {
            "https://api.weather.gov/points/": POINTS_RESPONSE,
            "https://api.weather.gov/gridpoints/LWX/97,71/stations": STATIONS_RESPONSE,
            "https://api.weather.gov/stations/KDCA/observations/latest": OBSERVATION_RESPONSE,
        },
    )

    conditions = weather.get_current_conditions()

    assert conditions == {
        "station_id": "KDCA",
        "station_name": "Washington Reagan National Airport",
        "timestamp": "2026-07-22T12:00:00+00:00",
        "description": "Mostly Cloudy",
        "temperature_f": 77.0,  # 25.0C
        "wind_speed_mph": 6.2,  # 10.0 km/h
        "wind_direction_degrees": 180,
        "humidity_percent": 60.5,
    }


def test_get_current_conditions_no_stations_raises(monkeypatch):
    _mock_get_by_url(
        monkeypatch,
        {
            "https://api.weather.gov/points/": POINTS_RESPONSE,
            "https://api.weather.gov/gridpoints/LWX/97,71/stations": {"features": []},
        },
    )

    with pytest.raises(weather.NwsApiError, match="No observation stations"):
        weather.get_current_conditions()


def test_get_current_conditions_missing_values_return_none(monkeypatch):
    # Simulates a station that's temporarily offline for some sensors.
    sparse_observation = {"properties": {"timestamp": "2026-07-22T12:00:00+00:00"}}
    _mock_get_by_url(
        monkeypatch,
        {
            "https://api.weather.gov/points/": POINTS_RESPONSE,
            "https://api.weather.gov/gridpoints/LWX/97,71/stations": STATIONS_RESPONSE,
            "https://api.weather.gov/stations/KDCA/observations/latest": sparse_observation,
        },
    )

    conditions = weather.get_current_conditions()

    assert conditions["temperature_f"] is None
    assert conditions["wind_speed_mph"] is None
    assert conditions["description"] is None


def test_get_forecast_returns_requested_number_of_periods(monkeypatch):
    _mock_get_by_url(
        monkeypatch,
        {
            "https://api.weather.gov/points/": POINTS_RESPONSE,
            "https://api.weather.gov/gridpoints/LWX/97,71/forecast": FORECAST_RESPONSE,
        },
    )

    periods = weather.get_forecast(periods=2)

    assert len(periods) == 2
    assert periods[0]["name"] == "Today"
    assert periods[0]["precipitation_probability_percent"] == 10
    assert periods[1]["name"] == "Tonight"
    assert periods[1]["precipitation_probability_percent"] is None


def test_get_forecast_default_returns_three_periods(monkeypatch):
    _mock_get_by_url(
        monkeypatch,
        {
            "https://api.weather.gov/points/": POINTS_RESPONSE,
            "https://api.weather.gov/gridpoints/LWX/97,71/forecast": FORECAST_RESPONSE,
        },
    )

    periods = weather.get_forecast()

    assert len(periods) == 3


def test_get_by_non_200_raises(monkeypatch):
    def fake_get(url, *args, **kwargs):
        return FakeResponse(500, None)

    monkeypatch.setattr(weather.requests, "get", fake_get)

    with pytest.raises(weather.NwsApiError, match="HTTP 500"):
        weather.get_current_conditions()


@pytest.mark.parametrize(
    "celsius,expected_fahrenheit",
    [(0, 32.0), (100, 212.0), (25, 77.0), (None, None)],
)
def test_celsius_to_fahrenheit(celsius, expected_fahrenheit):
    assert weather._celsius_to_fahrenheit(celsius) == expected_fahrenheit


@pytest.mark.parametrize(
    "kmh,expected_mph",
    [(0, 0.0), (100, 62.1), (10, 6.2), (None, None)],
)
def test_kmh_to_mph(kmh, expected_mph):
    assert weather._kmh_to_mph(kmh) == expected_mph
