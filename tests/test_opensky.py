from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from live_flight.opensky import (
    ClosestFlight,
    _bounding_box,
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


class TestFindClosestFlight:
    def test_no_response_returns_none(self):
        api = MagicMock()
        api.get_states.return_value = None
        assert find_closest_flight(api, 0.0, 0.0) is None

    def test_empty_states_returns_none(self):
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[])
        assert find_closest_flight(api, 0.0, 0.0) is None

    def test_builds_closest_flight_with_route(self):
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
        assert result.departure_airport == "SBGR"
        assert result.arrival_airport == "SBSP"
        assert result.speed_kmh == pytest.approx(250.0 * 3.6)
        assert result.distance_km == pytest.approx(haversine_km(0.0, 0.0, 0.1, 0.1))

    def test_handles_missing_callsign_and_velocity(self):
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[
            _state(callsign=None, velocity=None, latitude=0.1, longitude=0.1),
        ])
        api.get_flights_by_aircraft.return_value = []

        result = find_closest_flight(api, 0.0, 0.0)

        assert result is not None
        assert result.callsign == "N/A"
        assert result.speed_kmh == 0.0
        assert result.departure_airport == "N/A"
        assert result.arrival_airport == "N/A"

    def test_uses_bounding_box_around_location(self):
        api = MagicMock()
        api.get_states.return_value = None
        find_closest_flight(api, 10.0, 20.0)
        api.get_states.assert_called_once()
        _, kwargs = api.get_states.call_args
        assert kwargs["bbox"] == _bounding_box(10.0, 20.0, 3.0)
