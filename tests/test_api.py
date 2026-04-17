from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from live_flight.api import app, limiter
from live_flight.opensky import Airport, ClosestFlight
from live_flight.photos import AircraftPhoto

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield


def _sample_flight() -> ClosestFlight:
    return ClosestFlight(
        callsign="GOL1234",
        icao24="e48e38",
        origin_country="Brazil",
        latitude=-23.5,
        longitude=-46.6,
        true_track=225.0,
        altitude_m=11582.4,
        departure=Airport(
            icao="SBGR", name="Guarulhos Intl", city="Sao Paulo", country="BR",
            latitude=-23.4322, longitude=-46.4692,
        ),
        arrival=Airport(
            icao="SBSP", name="Congonhas", city="Sao Paulo", country="BR",
            latitude=-23.6261, longitude=-46.6564,
        ),
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
        assert body["flight"]["latitude"] == pytest.approx(-23.5)
        assert body["flight"]["longitude"] == pytest.approx(-46.6)
        assert body["flight"]["true_track"] == pytest.approx(225.0)
        assert body["flight"]["altitude_m"] == pytest.approx(11582.4)
        assert body["flight"]["departure"] == {
            "icao": "SBGR",
            "name": "Guarulhos Intl",
            "city": "Sao Paulo",
            "country": "BR",
            "latitude": pytest.approx(-23.4322),
            "longitude": pytest.approx(-46.4692),
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


class TestClosestFlightRateLimit:
    @patch("live_flight.api.find_closest_flight")
    def test_429_after_10_requests_in_a_minute(self, mock_find):
        mock_find.return_value = None
        for i in range(10):
            response = client.get("/closest-flight", params={"lat": 0, "lon": 0})
            assert response.status_code == 200, f"request {i + 1} returned {response.status_code}"

        response = client.get("/closest-flight", params={"lat": 0, "lon": 0})
        assert response.status_code == 429

    def test_status_endpoint_not_rate_limited(self):
        for _ in range(15):
            response = client.get("/status")
            assert response.status_code == 200

    @patch("live_flight.api.fetch_aircraft_photo")
    def test_aircraft_photo_endpoint_not_rate_limited(self, mock_fetch):
        mock_fetch.return_value = None
        for _ in range(15):
            response = client.get("/aircraft-photo", params={"icao24": "abcdef"})
            assert response.status_code == 200


class TestAircraftPhotoEndpoint:
    @patch("live_flight.api.fetch_aircraft_photo")
    def test_200_returns_serialized_photo(self, mock_fetch):
        mock_fetch.return_value = AircraftPhoto(
            thumbnail_url="https://example.com/large.jpg",
            photographer="Jane Doe",
            link="https://www.planespotters.net/photo/1/x",
        )

        response = client.get("/aircraft-photo", params={"icao24": "4B1805"})

        assert response.status_code == 200
        assert response.json() == {
            "photo": {
                "thumbnail_url": "https://example.com/large.jpg",
                "photographer": "Jane Doe",
                "link": "https://www.planespotters.net/photo/1/x",
            }
        }
        mock_fetch.assert_called_once_with("4b1805")

    @patch("live_flight.api.fetch_aircraft_photo")
    def test_200_with_null_when_photo_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        response = client.get("/aircraft-photo", params={"icao24": "abcdef"})
        assert response.status_code == 200
        assert response.json() == {"photo": None}

    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"icao24": ""},
            {"icao24": "xyz"},
            {"icao24": "12345"},
            {"icao24": "12345g"},
            {"icao24": "1234567"},
        ],
    )
    def test_400_on_invalid_icao24(self, params):
        response = client.get("/aircraft-photo", params=params)
        assert response.status_code == 400

    @patch("live_flight.api.fetch_aircraft_photo")
    def test_500_on_upstream_error(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("planespotters is down")
        response = client.get("/aircraft-photo", params={"icao24": "abcdef"})
        assert response.status_code == 500
        assert "planespotters is down" in response.json()["detail"]
