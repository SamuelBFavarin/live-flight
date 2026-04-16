from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from live_flight.opensky import (
    Airport,
    ClosestFlight,
    _bounding_box,
    _lookup_aircraft_info,
    _lookup_airport,
    _lookup_route,
    _nearest_state,
    find_closest_flight,
    haversine_km,
)


def _state(**kwargs) -> SimpleNamespace:
    defaults = dict(
        icao24="abc123",
        callsign="TEST123",
        origin_country="Brazil",
        latitude=0.0,
        longitude=0.0,
        velocity=100.0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestHaversineKm:
    def test_same_point_is_zero(self):
        assert haversine_km(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0)

    def test_one_degree_latitude_is_about_111km(self):
        assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.19, rel=1e-3)

    def test_known_city_pair_nyc_to_la(self):
        distance = haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
        assert distance == pytest.approx(3936, rel=1e-2)

    def test_is_symmetric(self):
        a = haversine_km(-15.0, 45.0, 30.0, -60.0)
        b = haversine_km(30.0, -60.0, -15.0, 45.0)
        assert a == pytest.approx(b)


class TestBoundingBox:
    def test_returns_expected_corners(self):
        assert _bounding_box(10.0, 20.0, 3.0) == (7.0, 13.0, 17.0, 23.0)

    def test_handles_negative_coordinates(self):
        assert _bounding_box(-10.0, -20.0, 1.5) == (-11.5, -8.5, -21.5, -18.5)


class TestNearestState:
    def test_empty_list_returns_none(self):
        assert _nearest_state([], 0.0, 0.0) is None

    def test_all_states_missing_coords_returns_none(self):
        states = [_state(latitude=None, longitude=None)]
        assert _nearest_state(states, 0.0, 0.0) is None

    def test_picks_closest_of_many(self):
        near = _state(icao24="near", latitude=0.1, longitude=0.1)
        far = _state(icao24="far", latitude=5.0, longitude=5.0)
        result = _nearest_state([far, near], 0.0, 0.0)
        assert result is not None
        state, distance = result
        assert state.icao24 == "near"
        assert distance == pytest.approx(haversine_km(0.0, 0.0, 0.1, 0.1))

    def test_skips_states_with_missing_coords(self):
        valid = _state(icao24="valid", latitude=1.0, longitude=1.0)
        missing = _state(icao24="missing", latitude=None, longitude=None)
        result = _nearest_state([missing, valid], 0.0, 0.0)
        assert result is not None
        assert result[0].icao24 == "valid"


class TestLookupRoute:
    def test_no_flights_returns_na(self):
        api = MagicMock()
        api.get_flights_by_aircraft.return_value = []
        assert _lookup_route(api, "abc123") == ("N/A", "N/A")

    def test_none_returns_na(self):
        api = MagicMock()
        api.get_flights_by_aircraft.return_value = None
        assert _lookup_route(api, "abc123") == ("N/A", "N/A")

    def test_api_exception_returns_na(self):
        api = MagicMock()
        api.get_flights_by_aircraft.side_effect = RuntimeError("api down")
        assert _lookup_route(api, "abc123") == ("N/A", "N/A")

    def test_returns_last_flight_airports(self):
        api = MagicMock()
        api.get_flights_by_aircraft.return_value = [
            SimpleNamespace(estDepartureAirport="KSFO", estArrivalAirport="KJFK"),
            SimpleNamespace(estDepartureAirport="KJFK", estArrivalAirport="EGLL"),
        ]
        assert _lookup_route(api, "abc123") == ("KJFK", "EGLL")

    def test_missing_airport_fields_fall_back_to_na(self):
        api = MagicMock()
        api.get_flights_by_aircraft.return_value = [
            SimpleNamespace(estDepartureAirport=None, estArrivalAirport=None),
        ]
        assert _lookup_route(api, "abc123") == ("N/A", "N/A")

    def test_queries_last_24_hours(self):
        api = MagicMock()
        api.get_flights_by_aircraft.return_value = []
        _lookup_route(api, "abc123")
        (_icao, begin, end), _ = api.get_flights_by_aircraft.call_args
        assert end - begin == 24 * 3600


class TestLookupAircraftInfo:
    @patch("live_flight.opensky.requests.get")
    def test_returns_model_and_airline(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Manufacturer": "Boeing",
            "Type": "737-86Q",
            "RegisteredOwners": "Swiss",
        }
        mock_get.return_value = mock_response
        assert _lookup_aircraft_info("abc123") == ("Boeing 737-86Q", "Swiss")

    @patch("live_flight.opensky.requests.get")
    def test_missing_fields_fall_back_to_na(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Manufacturer": None,
            "Type": None,
            "RegisteredOwners": None,
        }
        mock_get.return_value = mock_response
        assert _lookup_aircraft_info("abc123") == ("N/A", "N/A")

    @patch("live_flight.opensky.requests.get")
    def test_only_type_and_airline_present(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Manufacturer": "",
            "Type": "A320",
            "RegisteredOwners": "Air France",
        }
        mock_get.return_value = mock_response
        assert _lookup_aircraft_info("abc123") == ("A320", "Air France")

    @patch("live_flight.opensky.requests.get")
    def test_http_error_returns_na(self, mock_get):
        mock_get.side_effect = RuntimeError("network down")
        assert _lookup_aircraft_info("abc123") == ("N/A", "N/A")

    @patch("live_flight.opensky.requests.get")
    def test_queries_hexdb_endpoint(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Manufacturer": "Airbus",
            "Type": "A320",
            "RegisteredOwners": "Iberia",
        }
        mock_get.return_value = mock_response
        _lookup_aircraft_info("abc123")
        (url,), _ = mock_get.call_args
        assert url.endswith("/abc123")
        assert "hexdb.io" in url


class TestLookupAirport:
    @patch("live_flight.opensky.requests.get")
    def test_builds_airport_from_hexdb_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "airport": "Guarulhos International Airport",
            "region_name": "Sao Paulo",
            "country_code": "BR",
            "icao": "SBGR",
        }
        mock_get.return_value = mock_response

        result = _lookup_airport("SBGR")

        assert result == Airport(
            icao="SBGR",
            name="Guarulhos International Airport",
            city="Sao Paulo",
            country="BR",
        )

    @patch("live_flight.opensky.requests.get")
    def test_na_icao_does_not_call_api(self, mock_get):
        result = _lookup_airport("N/A")
        assert result == Airport.unknown()
        mock_get.assert_not_called()

    @patch("live_flight.opensky.requests.get")
    def test_empty_icao_does_not_call_api(self, mock_get):
        result = _lookup_airport("")
        assert result == Airport.unknown()
        mock_get.assert_not_called()

    @patch("live_flight.opensky.requests.get")
    def test_http_error_preserves_icao(self, mock_get):
        mock_get.side_effect = RuntimeError("network down")
        result = _lookup_airport("SBGR")
        assert result == Airport.unknown(icao="SBGR")

    @patch("live_flight.opensky.requests.get")
    def test_missing_fields_fall_back_to_na(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"airport": None, "region_name": None, "country_code": None}
        mock_get.return_value = mock_response
        result = _lookup_airport("XXXX")
        assert result == Airport(icao="XXXX", name="N/A", city="N/A", country="N/A")


class TestFindClosestFlight:
    def test_no_response_returns_none(self):
        api = MagicMock()
        api.get_states.return_value = None
        assert find_closest_flight(api, 0.0, 0.0) is None

    def test_empty_states_returns_none(self):
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[])
        assert find_closest_flight(api, 0.0, 0.0) is None

    @patch("live_flight.opensky._lookup_airport")
    @patch("live_flight.opensky._lookup_aircraft_info")
    def test_builds_closest_flight_with_route(self, mock_aircraft, mock_airport):
        mock_aircraft.return_value = ("Boeing 737-8", "Gol")
        mock_airport.side_effect = lambda icao: Airport(
            icao=icao, name=f"{icao} Name", city="Sao Paulo", country="BR"
        )
        api = MagicMock()
        near = _state(
            icao24="near01",
            callsign="  GOL1234  ",
            origin_country="Brazil",
            latitude=0.1,
            longitude=0.1,
            velocity=250.0,
        )
        far = _state(icao24="far01", latitude=5.0, longitude=5.0)
        api.get_states.return_value = SimpleNamespace(states=[far, near])
        api.get_flights_by_aircraft.return_value = [
            SimpleNamespace(estDepartureAirport="SBGR", estArrivalAirport="SBSP"),
        ]

        result = find_closest_flight(api, 0.0, 0.0)

        assert isinstance(result, ClosestFlight)
        assert result.callsign == "GOL1234"
        assert result.origin_country == "Brazil"
        assert result.departure == Airport(icao="SBGR", name="SBGR Name", city="Sao Paulo", country="BR")
        assert result.arrival == Airport(icao="SBSP", name="SBSP Name", city="Sao Paulo", country="BR")
        assert result.aircraft_type == "Boeing 737-8"
        assert result.airline == "Gol"
        assert result.speed_kmh == pytest.approx(250.0 * 3.6)
        assert result.distance_km == pytest.approx(haversine_km(0.0, 0.0, 0.1, 0.1))
        mock_aircraft.assert_called_once_with("near01")
        assert [c.args[0] for c in mock_airport.call_args_list] == ["SBGR", "SBSP"]

    @patch("live_flight.opensky._lookup_airport")
    @patch("live_flight.opensky._lookup_aircraft_info")
    def test_handles_missing_callsign_and_velocity(self, mock_aircraft, mock_airport):
        mock_aircraft.return_value = ("N/A", "N/A")
        mock_airport.return_value = Airport.unknown()
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[
            _state(callsign=None, velocity=None, latitude=0.1, longitude=0.1),
        ])
        api.get_flights_by_aircraft.return_value = []

        result = find_closest_flight(api, 0.0, 0.0)

        assert result is not None
        assert result.callsign == "N/A"
        assert result.speed_kmh == 0.0
        assert result.departure == Airport.unknown()
        assert result.arrival == Airport.unknown()
        assert result.aircraft_type == "N/A"
        assert result.airline == "N/A"

    def test_uses_bounding_box_around_location(self):
        api = MagicMock()
        api.get_states.return_value = None
        find_closest_flight(api, 10.0, 20.0)
        api.get_states.assert_called_once()
        _, kwargs = api.get_states.call_args
        assert kwargs["bbox"] == _bounding_box(10.0, 20.0, 3.0)
