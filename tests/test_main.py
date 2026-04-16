from unittest.mock import MagicMock, patch

import pytest

from live_flight import main as main_module
from live_flight.opensky import ClosestFlight


@patch.dict("os.environ", {"OPENSKY_CLIENT_ID": "id", "OPENSKY_CLIENT_SECRET": "secret"}, clear=True)
@patch("live_flight.main.OpenSkyApi")
def test_build_api_uses_credentials_when_present(mock_api_cls):
    main_module._build_api()
    mock_api_cls.assert_called_once_with(client_id="id", client_secret="secret")


@patch.dict("os.environ", {}, clear=True)
@patch("live_flight.main.OpenSkyApi")
def test_build_api_falls_back_to_anonymous_when_env_missing(mock_api_cls, capsys):
    main_module._build_api()
    mock_api_cls.assert_called_once_with()
    assert "anonymous access" in capsys.readouterr().out


@patch.dict("os.environ", {"OPENSKY_CLIENT_ID": "id"}, clear=True)
@patch("live_flight.main.OpenSkyApi")
def test_build_api_anonymous_when_only_one_var_set(mock_api_cls):
    main_module._build_api()
    mock_api_cls.assert_called_once_with()


@patch("live_flight.main.find_closest_flight")
def test_print_flight_renders_closest_flight(mock_find, capsys):
    mock_find.return_value = ClosestFlight(
        callsign="GOL1234",
        origin_country="Brazil",
        departure_airport="SBGR",
        arrival_airport="SBSP",
        speed_kmh=900.0,
        distance_km=12.5,
    )

    main_module._print_flight(0.0, 0.0, MagicMock())

    out = capsys.readouterr().out
    assert "GOL1234" in out
    assert "SBGR" in out
    assert "SBSP" in out
    assert "Brazil" in out
    assert "900.0 km/h" in out
    assert "12.5 km" in out


@patch("live_flight.main.find_closest_flight")
def test_print_flight_reports_when_no_flights_found(mock_find, capsys):
    mock_find.return_value = None
    main_module._print_flight(1.0, 2.0, MagicMock())
    assert "no flights found" in capsys.readouterr().out


@patch("live_flight.main.find_closest_flight")
def test_print_flight_reports_errors_without_raising(mock_find, capsys):
    mock_find.side_effect = RuntimeError("boom")
    main_module._print_flight(0.0, 0.0, MagicMock())
    assert "error fetching flight data: boom" in capsys.readouterr().out
