# Live Flight API

HTTP API that returns the closest live flight to a given location, using the [OpenSky Network API](https://openskynetwork.github.io/opensky-api/python.html) as the live-data source, [hexdb.io](https://hexdb.io/) for aircraft / airport enrichment, and [planespotters.net](https://www.planespotters.net/) for aircraft photos. Built with FastAPI.

## Requirements

- Python 3.10+
- [Poetry](https://python-poetry.org/docs/#installation)
- An OpenSky Network account (free): https://opensky-network.org/
- OAuth2 API credentials (client ID + secret). Create them from your OpenSky account page.

## Setup

```bash
cd live-flight
poetry install
cp .env.example .env
# edit .env and set OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET
```

## Run the API

```bash
poetry run live-flight
```

That starts uvicorn on `http://0.0.0.0:8000`:

- **Web UI:** `http://localhost:8000/` — simple page that detects your location via IP geolocation, polls `/closest-flight` every 20s and renders the result.
- **Interactive API docs:** `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc`.

## Endpoints

### `GET /status`

Health check.

```bash
curl http://localhost:8000/status
# {"status":"ok"}
```

Always returns `200`.

### `GET /closest-flight?lat=<lat>&lon=<lon>`

Returns the closest live flight to the given coordinates.

```bash
curl "http://localhost:8000/closest-flight?lat=-23.55&lon=-46.63"
```

Example response:

```json
{
  "flight": {
    "callsign": "GOL1234",
    "icao24": "e48e38",
    "origin_country": "Brazil",
    "latitude": -23.512,
    "longitude": -46.623,
    "true_track": 225.4,
    "altitude_m": 11582.4,
    "departure": {
      "icao": "SBGR",
      "name": "Guarulhos International Airport",
      "city": "Sao Paulo",
      "country": "BR"
    },
    "arrival": {
      "icao": "SBSP",
      "name": "Congonhas Airport",
      "city": "Sao Paulo",
      "country": "BR"
    },
    "aircraft_type": "Boeing 737-8",
    "airline": "Gol Linhas Aereas",
    "speed_kmh": 845.3,
    "distance_km": 12.4
  }
}
```

Status codes:

| Code | When |
|------|------|
| `200` | Success. If no aircraft is currently within the search area, the body is `{"flight": null}`. |
| `400` | `lat` or `lon` is missing, not numeric, or out of range (`lat ∉ [-90, 90]` or `lon ∉ [-180, 180]`). |
| `500` | Upstream error (OpenSky unreachable, unhandled exception, …). |

### `GET /aircraft-photo?icao24=<hex>`

Returns a photo of the given aircraft from [planespotters.net](https://www.planespotters.net/).

```bash
curl "http://localhost:8000/aircraft-photo?icao24=4b1805"
```

Example response:

```json
{
  "photo": {
    "thumbnail_url": "https://t.plnspttrs.net/.../1854855_e4f616f312_280.jpg",
    "photographer": "Cornelius Grossmann",
    "link": "https://www.planespotters.net/photo/1854855/..."
  }
}
```

Status codes:

| Code | When |
|------|------|
| `200` | Success. If the registry has no photo for this aircraft, the body is `{"photo": null}`. |
| `400` | `icao24` is missing or not a valid 6-character hex string. |
| `500` | Unexpected upstream error. |

Per planespotters.net's terms, callers that display a photo **must** show the photographer's name and link back to the photo page (the UI bundled with this project does that automatically).

## Frontend

A minimal vanilla HTML/CSS/JS page is shipped with the app (under [live_flight/static/](live_flight/static/)):

1. On load it asks the browser for the visitor's location via the standard [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API) (`navigator.geolocation.getCurrentPosition`). The browser prompts the user the first time.
2. If the user declines or the browser doesn't support geolocation, it silently falls back to an IP-based lookup via [ipapi.co](https://ipapi.co/).
3. It then polls the API's `/closest-flight` endpoint every 20 seconds with those coordinates and renders the response.
4. For each flight, it also calls `/aircraft-photo?icao24=<hex>` to fetch a photo from planespotters.net and renders it at the top of the card with the required photographer credit.
5. An interactive [Leaflet](https://leafletjs.com/) map rendered with CartoDB's free [dark basemap](https://carto.com/attributions) (tiles over [OpenStreetMap](https://www.openstreetmap.org/) data) shows your location and the aircraft's current position with a plane icon. The icon is rotated to match the aircraft's current heading (`true_track`, degrees clockwise from north) so it visually points in the direction of travel. Between API refreshes the marker is animated via **dead reckoning** — each animation frame it advances forward along its heading at its reported speed using the great-circle destination-point formula — so the aircraft appears to move smoothly in real time rather than jumping every 20 seconds. When a new API response arrives, the anchor position is snapped back to the reported truth. The initial viewport is scaled to ~100 km, and a scale bar is rendered in the corner.

The page uses a full-screen two-column layout — flight details on the left, full-height map on the right. On narrow viewports (≤ 768 px) the two panels stack vertically.

No build step, bundler, or framework is required — FastAPI mounts the files at `/static/*` and serves `index.html` at `/`.

> Note: `navigator.geolocation` is only available on secure origins (HTTPS) in production. On `localhost` it works over HTTP for dev.

## Running the tests

```bash
poetry run pytest
```

Coverage is printed automatically (configured via `pyproject.toml`). CI runs the full suite on every push to `main` (see `.github/workflows/tests.yml`).

## Notes

- Origin/destination ICAO codes come from OpenSky's recent flight history for the aircraft. When no history is available, the airport shows as `N/A`.
- Each ICAO airport code is enriched with its name, city/region and country code via hexdb.io's airport registry (`airport`, `region_name`, `country_code`). `region_name` is often the city for major commercial airports but can be a region/state for smaller ones.
- Aircraft model and operating airline are resolved by looking up the ICAO24 address against the same registry (`Manufacturer` + `Type` and `RegisteredOwners`). If the registry returns no match, the fields show `N/A`.
- Without OpenSky credentials, the app falls back to anonymous requests, which OpenSky rate-limits heavily.
