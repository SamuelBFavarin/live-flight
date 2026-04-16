from unittest.mock import MagicMock, patch

import pytest

from live_flight.location import get_current_location


@patch("live_flight.location.requests.get")
def test_returns_parsed_lat_lon(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"latitude": "-23.5505", "longitude": "-46.6333"}
    mock_get.return_value = mock_response

    lat, lon = get_current_location()

    assert lat == pytest.approx(-23.5505)
    assert lon == pytest.approx(-46.6333)
    mock_response.raise_for_status.assert_called_once()


@patch("live_flight.location.requests.get")
def test_propagates_http_errors(mock_get):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = RuntimeError("timeout")
    mock_get.return_value = mock_response

    with pytest.raises(RuntimeError, match="timeout"):
        get_current_location()


@patch("live_flight.location.requests.get")
def test_calls_ipapi_endpoint(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"latitude": 0.0, "longitude": 0.0}
    mock_get.return_value = mock_response

    get_current_location()

    (url,), _ = mock_get.call_args
    assert "ipapi.co" in url
