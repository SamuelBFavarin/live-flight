from unittest.mock import MagicMock, patch

from live_flight.photos import AircraftPhoto, fetch_aircraft_photo


@patch("live_flight.photos.requests.get")
def test_returns_first_photo_with_large_thumbnail(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "photos": [
            {
                "id": "1",
                "thumbnail": {"src": "https://example.com/small.jpg"},
                "thumbnail_large": {"src": "https://example.com/large.jpg"},
                "link": "https://www.planespotters.net/photo/1/...",
                "photographer": "Jane Doe",
            }
        ]
    }
    mock_get.return_value = mock_response

    result = fetch_aircraft_photo("4b1805")

    assert result == AircraftPhoto(
        thumbnail_url="https://example.com/large.jpg",
        photographer="Jane Doe",
        link="https://www.planespotters.net/photo/1/...",
    )


@patch("live_flight.photos.requests.get")
def test_falls_back_to_small_thumbnail_when_large_missing(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "photos": [
            {
                "thumbnail": {"src": "https://example.com/small.jpg"},
                "photographer": "John",
                "link": "",
            }
        ]
    }
    mock_get.return_value = mock_response

    result = fetch_aircraft_photo("abcdef")

    assert result is not None
    assert result.thumbnail_url == "https://example.com/small.jpg"
    assert result.photographer == "John"
    assert result.link == ""


@patch("live_flight.photos.requests.get")
def test_no_photos_returns_none(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"photos": []}
    mock_get.return_value = mock_response
    assert fetch_aircraft_photo("abcdef") is None


@patch("live_flight.photos.requests.get")
def test_missing_thumbnail_src_returns_none(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "photos": [{"photographer": "x", "link": "y"}],
    }
    mock_get.return_value = mock_response
    assert fetch_aircraft_photo("abcdef") is None


@patch("live_flight.photos.requests.get")
def test_http_error_returns_none(mock_get):
    mock_get.side_effect = RuntimeError("network down")
    assert fetch_aircraft_photo("abcdef") is None


@patch("live_flight.photos.requests.get")
def test_missing_photographer_defaults_to_unknown(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "photos": [
            {
                "thumbnail_large": {"src": "https://example.com/x.jpg"},
                "photographer": None,
            }
        ]
    }
    mock_get.return_value = mock_response

    result = fetch_aircraft_photo("abcdef")

    assert result is not None
    assert result.photographer == "Unknown"


@patch("live_flight.photos.requests.get")
def test_queries_planespotters_endpoint(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"photos": []}
    mock_get.return_value = mock_response
    fetch_aircraft_photo("abcdef")
    (url,), _ = mock_get.call_args
    assert url.endswith("/abcdef")
    assert "planespotters.net" in url
