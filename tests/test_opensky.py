from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from live_flight.opensky import (
    AircraftTrack,
    Airport,
    ClosestFlight,
    TrackWaypoint,
    _bounding_box,
    _lookup_aircraft_info,
    _lookup_airport,
    _lookup_route,
    _lookup_route_by_callsign,
    _nearest_state,
    fetch_aircraft_track,
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
        true_track=90.0,
        baro_altitude=10000.0,
        geo_altitude=10050.0,
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


class TestLookupRouteByCallsign:
    @patch("live_flight.opensky.requests.get")
    def test_parses_simple_route(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"flight": "UAL234", "route": "KIAD-EDDB"}
        mock_get.return_value = mock_response
        assert _lookup_route_by_callsign("UAL234") == ("KIAD", "EDDB")

    @patch("live_flight.opensky.requests.get")
    def test_multi_leg_route_uses_first_and_last(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"route": "SBGR-SBRJ-SBSP"}
        mock_get.return_value = mock_response
        assert _lookup_route_by_callsign("GOL100") == ("SBGR", "SBSP")

    @patch("live_flight.opensky.requests.get")
    def test_na_callsign_does_not_call_api(self, mock_get):
        assert _lookup_route_by_callsign("N/A") == ("N/A", "N/A")
        mock_get.assert_not_called()

    @patch("live_flight.opensky.requests.get")
    def test_empty_callsign_does_not_call_api(self, mock_get):
        assert _lookup_route_by_callsign("") == ("N/A", "N/A")
        mock_get.assert_not_called()

    @patch("live_flight.opensky.requests.get")
    def test_http_error_returns_na(self, mock_get):
        mock_get.side_effect = RuntimeError("network down")
        assert _lookup_route_by_callsign("UAL234") == ("N/A", "N/A")

    @patch("live_flight.opensky.requests.get")
    def test_missing_route_field_returns_na(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"flight": "X"}
        mock_get.return_value = mock_response
        assert _lookup_route_by_callsign("UAL234") == ("N/A", "N/A")

    @patch("live_flight.opensky.requests.get")
    def test_route_without_dash_returns_na(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"route": "UNKNOWN"}
        mock_get.return_value = mock_response
        assert _lookup_route_by_callsign("UAL234") == ("N/A", "N/A")


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

        mock_response.json.return_value = {
            "airport": "Guarulhos International Airport",
            "region_name": "Sao Paulo",
            "country_code": "BR",
            "icao": "SBGR",
            "latitude": -23.4322,
            "longitude": -46.4692,
        }

        result = _lookup_airport("SBGR")

        assert result == Airport(
            icao="SBGR",
            name="Guarulhos International Airport",
            city="Sao Paulo",
            country="BR",
            latitude=-23.4322,
            longitude=-46.4692,
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
        assert result == Airport(
            icao="XXXX", name="N/A", city="N/A", country="N/A", latitude=None, longitude=None
        )


class TestFindClosestFlight:
    def test_no_response_returns_none(self):
        api = MagicMock()
        api.get_states.return_value = None
        assert find_closest_flight(api, 0.0, 0.0) is None

    def test_empty_states_returns_none(self):
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[])
        assert find_closest_flight(api, 0.0, 0.0) is None

    @patch("live_flight.opensky._lookup_route_by_callsign")
    @patch("live_flight.opensky._lookup_airport")
    @patch("live_flight.opensky._lookup_aircraft_info")
    def test_builds_closest_flight_with_route(self, mock_aircraft, mock_airport, mock_callsign_route):
        mock_aircraft.return_value = ("Boeing 737-8", "Gol")
        mock_airport.side_effect = lambda icao: Airport(
            icao=icao,
            name=f"{icao} Name",
            city="Sao Paulo",
            country="BR",
            latitude=-23.4,
            longitude=-46.5,
        )
        mock_callsign_route.return_value = ("SBGR", "SBSP")
        api = MagicMock()
        near = _state(
            icao24="near01",
            callsign="  GOL1234  ",
            origin_country="Brazil",
            latitude=0.1,
            longitude=0.1,
            velocity=250.0,
            true_track=135.0,
            baro_altitude=11582.4,
            geo_altitude=11600.0,
        )
        far = _state(icao24="far01", latitude=5.0, longitude=5.0)
        api.get_states.return_value = SimpleNamespace(states=[far, near])

        result = find_closest_flight(api, 0.0, 0.0)

        assert isinstance(result, ClosestFlight)
        assert result.callsign == "GOL1234"
        assert result.origin_country == "Brazil"
        assert result.latitude == pytest.approx(0.1)
        assert result.longitude == pytest.approx(0.1)
        assert result.true_track == pytest.approx(135.0)
        assert result.altitude_m == pytest.approx(11582.4)
        assert result.departure == Airport(
            icao="SBGR", name="SBGR Name", city="Sao Paulo", country="BR",
            latitude=-23.4, longitude=-46.5,
        )
        assert result.arrival == Airport(
            icao="SBSP", name="SBSP Name", city="Sao Paulo", country="BR",
            latitude=-23.4, longitude=-46.5,
        )
        assert result.aircraft_type == "Boeing 737-8"
        assert result.airline == "Gol"
        assert result.speed_kmh == pytest.approx(250.0 * 3.6)
        assert result.distance_km == pytest.approx(haversine_km(0.0, 0.0, 0.1, 0.1))
        mock_aircraft.assert_called_once_with("near01")
        mock_callsign_route.assert_called_once_with("GOL1234")
        api.get_flights_by_aircraft.assert_not_called()
        assert [c.args[0] for c in mock_airport.call_args_list] == ["SBGR", "SBSP"]

    @patch("live_flight.opensky._lookup_route_by_callsign")
    @patch("live_flight.opensky._lookup_airport")
    @patch("live_flight.opensky._lookup_aircraft_info")
    def test_handles_missing_callsign_and_velocity(
        self, mock_aircraft, mock_airport, mock_callsign_route
    ):
        mock_aircraft.return_value = ("N/A", "N/A")
        mock_airport.return_value = Airport.unknown()
        mock_callsign_route.return_value = ("N/A", "N/A")
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[
            _state(
                callsign=None,
                velocity=None,
                latitude=0.1,
                longitude=0.1,
                true_track=None,
                baro_altitude=None,
                geo_altitude=None,
            ),
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
        assert result.true_track is None
        assert result.altitude_m is None

    @patch("live_flight.opensky._lookup_route_by_callsign")
    @patch("live_flight.opensky._lookup_airport")
    @patch("live_flight.opensky._lookup_aircraft_info")
    def test_falls_back_to_geo_altitude_when_baro_missing(
        self, mock_aircraft, mock_airport, mock_callsign_route
    ):
        mock_aircraft.return_value = ("N/A", "N/A")
        mock_airport.return_value = Airport.unknown()
        mock_callsign_route.return_value = ("N/A", "N/A")
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[
            _state(latitude=0.1, longitude=0.1, baro_altitude=None, geo_altitude=9750.0),
        ])
        api.get_flights_by_aircraft.return_value = []

        result = find_closest_flight(api, 0.0, 0.0)

        assert result is not None
        assert result.altitude_m == pytest.approx(9750.0)

    @patch("live_flight.opensky._lookup_route_by_callsign")
    @patch("live_flight.opensky._lookup_airport")
    @patch("live_flight.opensky._lookup_aircraft_info")
    def test_falls_back_to_opensky_history_when_callsign_route_missing(
        self, mock_aircraft, mock_airport, mock_callsign_route
    ):
        mock_aircraft.return_value = ("N/A", "N/A")
        mock_airport.side_effect = lambda icao: Airport(
            icao=icao, name=f"{icao} Name", city="City", country="US",
            latitude=40.0, longitude=-100.0,
        )
        mock_callsign_route.return_value = ("N/A", "N/A")
        api = MagicMock()
        api.get_states.return_value = SimpleNamespace(states=[
            _state(icao24="hist01", latitude=0.1, longitude=0.1, callsign="UAL999"),
        ])
        api.get_flights_by_aircraft.return_value = [
            SimpleNamespace(estDepartureAirport="KLAX", estArrivalAirport="KJFK"),
        ]

        result = find_closest_flight(api, 0.0, 0.0)

        assert result is not None
        assert result.departure.icao == "KLAX"
        assert result.arrival.icao == "KJFK"
        api.get_flights_by_aircraft.assert_called_once()

    def test_uses_bounding_box_around_location(self):
        api = MagicMock()
        api.get_states.return_value = None
        find_closest_flight(api, 10.0, 20.0)
        api.get_states.assert_called_once()
        _, kwargs = api.get_states.call_args
        assert kwargs["bbox"] == _bounding_box(10.0, 20.0, 3.0)


class TestFetchAircraftTrack:
    def _waypoint(self, **kwargs) -> SimpleNamespace:
        defaults = dict(
            time=1_700_000_000,
            latitude=10.0,
            longitude=20.0,
            baro_altitude=9000.0,
            true_track=90.0,
            on_ground=False,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_api_returns_none(self):
        api = MagicMock()
        api.get_track_by_aircraft.return_value = None
        assert fetch_aircraft_track(api, "abc123") is None

    def test_api_raises_returns_none(self):
        api = MagicMock()
        api.get_track_by_aircraft.side_effect = RuntimeError("404 no track")
        assert fetch_aircraft_track(api, "abc123") is None

    def test_builds_track_from_waypoints(self):
        api = MagicMock()
        api.get_track_by_aircraft.return_value = SimpleNamespace(
            path=[
                self._waypoint(latitude=10.0, longitude=20.0),
                self._waypoint(latitude=10.5, longitude=20.5, on_ground=True),
            ],
            callsign=" TAM3456  ",
            startTime=1_700_000_000,
            endTime=1_700_003_600,
        )

        result = fetch_aircraft_track(api, "abc123")

        assert isinstance(result, AircraftTrack)
        assert result.icao24 == "abc123"
        assert result.callsign == "TAM3456"
        assert result.start_time == 1_700_000_000
        assert result.end_time == 1_700_003_600
        assert len(result.path) == 2
        assert result.path[0] == TrackWaypoint(
            time=1_700_000_000,
            latitude=10.0,
            longitude=20.0,
            baro_altitude=9000.0,
            true_track=90.0,
            on_ground=False,
        )
        assert result.path[1].on_ground is True

    def test_empty_path_returns_track_with_no_waypoints(self):
        api = MagicMock()
        api.get_track_by_aircraft.return_value = SimpleNamespace(
            path=[], callsign=None, startTime=None, endTime=None
        )
        result = fetch_aircraft_track(api, "abc123")
        assert result is not None
        assert result.path == []
        assert result.callsign is None
