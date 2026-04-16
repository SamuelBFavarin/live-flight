from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from live_flight.api import app
from live_flight.opensky import Airport, ClosestFlight

client = TestClient(app)


def _sample_flight() -> ClosestFlight:
    return ClosestFlight(
        callsign="GOL1234",
        origin_country="Brazil",
        departure=Airport(icao="SBGR", name="Guarulhos Intl", city="Sao Paulo", country="BR"),
        arrival=Airport(icao="SBSP", name="Congonhas", city="Sao Paulo", country="BR"),
        aircraft_type="Boeing 737-8",
        airline="Gol Linhas Aereas",
        speed_kmh=900.0,
        distance_km=12.5,
    )


class TestStatusEndpoint:
    def test_returns_ok(self):
        response = client.get("/status")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestFrontend:
    def test_root_serves_html_page(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>Live Flight</title>" in response.text

    def test_static_js_is_served(self):
        response = client.get("/static/app.js")
        assert response.status_code == 200
        assert "/closest-flight" in response.text

    def test_static_css_is_served(self):
        response = client.get("/static/styles.css")
        assert response.status_code == 200


class TestClosestFlightEndpoint:
    @patch("live_flight.api.find_closest_flight")
    def test_200_returns_serialized_flight(self, mock_find):
        mock_find.return_value = _sample_flight()

        response = client.get("/closest-flight", params={"lat": -23.5, "lon": -46.6})

        assert response.status_code == 200
        body = response.json()
        assert body["flight"]["callsign"] == "GOL1234"
        assert body["flight"]["airline"] == "Gol Linhas Aereas"
        assert body["flight"]["aircraft_type"] == "Boeing 737-8"
        assert body["flight"]["departure"] == {
            "icao": "SBGR",
            "name": "Guarulhos Intl",
            "city": "Sao Paulo",
            "country": "BR",
        }
        assert body["flight"]["arrival"]["icao"] == "SBSP"

    @patch("live_flight.api.find_closest_flight")
    def test_200_with_null_when_no_flight_found(self, mock_find):
        mock_find.return_value = None

        response = client.get("/closest-flight", params={"lat": 0, "lon": 0})

        assert response.status_code == 200
        assert response.json() == {"flight": None}

    @patch("live_flight.api.find_closest_flight")
    def test_passes_coordinates_to_finder(self, mock_find):
        mock_find.return_value = None

        client.get("/closest-flight", params={"lat": 40.7128, "lon": -74.0060})

        _, args, _ = mock_find.mock_calls[0]
        assert args[1] == pytest.approx(40.7128)
        assert args[2] == pytest.approx(-74.0060)

    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"lat": "0"},
            {"lon": "0"},
            {"lat": "abc", "lon": "0"},
            {"lat": "0", "lon": "xyz"},
            {"lat": "91", "lon": "0"},
            {"lat": "-91", "lon": "0"},
            {"lat": "0", "lon": "181"},
            {"lat": "0", "lon": "-181"},
        ],
    )
    def test_400_on_invalid_query_params(self, params):
        response = client.get("/closest-flight", params=params)
        assert response.status_code == 400

    @patch("live_flight.api.find_closest_flight")
    def test_500_on_upstream_error(self, mock_find):
        mock_find.side_effect = RuntimeError("opensky is down")

        response = client.get("/closest-flight", params={"lat": 0, "lon": 0})

        assert response.status_code == 500
        assert "opensky is down" in response.json()["detail"]
