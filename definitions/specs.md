### This is the spec to create the Live Flight System

Goal: Expose an HTTP API that, given a caller-supplied location (latitude / longitude), returns information about the closest live flight — flight identification, airline, aircraft model, origin and destination airports (with name / city / country) and current speed. The API is served together with a minimal web UI; the API does not manage the refresh cadence itself (the client decides when to poll).

### Technologies

- The service must to be written in Python.
- It must to expose an HTTP API built with `FastAPI` and served via `uvicorn`.
- It should consume the OpenSky API. The documentation is defined here: https://openskynetwork.github.io/opensky-api/python.html
- It should use environment variables (loaded from a `.env` file) to define the OpenSky OAuth2 credentials (`OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`). `.env` must be excluded from version control.
- We need to setup a local environment using poetry


### API Endpoints

- `GET /status` — health check. Always returns `200` with a small JSON body (e.g. `{"status": "ok"}`).
- `GET /closest-flight?lat=<lat>&lon=<lon>` — returns the closest live flight to the provided coordinates.
  - `200` — success. When no aircraft is within the search area, return `{"flight": null}` (still 200).
  - `400` — `lat` or `lon` is missing, not numeric, or out of range (`lat ∉ [-90, 90]` or `lon ∉ [-180, 180]`).
  - `500` — upstream error (OpenSky unreachable, unhandled exception in enrichment, …).
- `GET /aircraft-photo?icao24=<hex>` — returns a photo of the aircraft with the given ICAO24 address, sourced from a public aircraft photo registry (e.g. `planespotters.net`). The response must to include a thumbnail URL, the photographer's name and a link back to the photo page so callers can comply with the registry's attribution requirements.
  - `200` — success. When the registry has no photo for this aircraft, return `{"photo": null}` (still 200).
  - `400` — `icao24` is missing or is not a valid 6-character hex string.
  - `500` — upstream error.
- `GET /` — serves the web UI's entry HTML document.
- `GET /static/*` — serves the web UI's static assets (CSS, JS).


### Web UI

- The API must to ship a minimal web UI reachable at `/`, implemented with plain HTML, CSS and JavaScript (no build step, no framework).
- On load, the UI must to detect the visitor's location using the browser's native Geolocation API (`navigator.geolocation.getCurrentPosition`). If the user denies the permission or the browser does not support geolocation, the UI must to fall back silently to an IP-based lookup via a public client-side service (e.g. `ipapi.co`). The backend must not be involved in the location lookup in either case.
- Using those coordinates, the UI must to call the `/closest-flight` endpoint and render the response (callsign, airline, aircraft model, origin, destination, speed, distance).
- For each rendered flight, the UI must to call `/aircraft-photo?icao24=<hex>` and, when a photo is returned, display it alongside the flight details together with the photographer's name linking back to the photo page (per the photo registry's attribution requirement). The UI must to cache photo lookups client-side keyed by `icao24`: when the next refresh returns the same aircraft as the one already displayed, the UI must not re-issue the photo request nor flicker the existing image. Previously seen aircraft (not currently displayed) must to be served from the cache instead of a fresh network call.
- The UI must to include an interactive map built on an open-source stack (e.g. `Leaflet` + `OpenStreetMap` data — no proprietary map provider). A dark basemap variant (e.g. CartoDB's free `dark_all` tiles) must to be used so the map blends with the dark UI theme, with the appropriate attribution. The map must to show a marker at the visitor's location and a distinct airplane-shaped marker at the aircraft's current latitude/longitude. The airplane marker must to be rotated to match the aircraft's `true_track` so it visually points toward its direction of travel; when the heading is unknown, the icon must to render un-rotated (pointing north). The initial viewport must to be scaled so that roughly 100 km around the visitor is visible, and the map must to render a distance scale control (in kilometers). The aircraft marker must to move and re-rotate on every refresh when a flight is present, and be removed when no flight is returned.
- Between API refreshes the UI must to dead-reckon the aircraft's position — on each animation frame, advance the displayed marker along its current `true_track` at its reported speed using a great-circle destination-point calculation, so the aircraft appears to move continuously in real time rather than jumping every 20 seconds. When a new API response arrives the anchor position must to snap back to the reported truth. Dead reckoning must to be skipped when either heading or speed is missing, or when speed is zero.
- The user-location marker on the map must to be draggable. When the user drops it in a new place, the UI must to immediately re-call `/closest-flight` with the new coordinates and refresh the flight card / map. The ongoing 20-second auto-refresh must to continue from the new coordinates (the original IP/browser-detected location is effectively replaced for the rest of the session).
- The page must to use a full-screen two-column layout — the flight details panel on the left and the full-height map on the right — so the two components together cover the whole viewport. On narrow viewports (roughly ≤ 768 px wide) the two panels should stack vertically instead of competing for width.
- The UI must to auto-refresh the flight information every 20 seconds; the IP-based location is only fetched once, at page load.
- Errors from either the geolocation service or the API must to be surfaced to the user.


### Business Rules

- The system must to authenticate to the OpenSky API using the OAuth2 client credentials (client id + client secret) defined in the environment variables
- The `/closest-flight` endpoint must to accept latitude and longitude from the caller; it does not detect the location server-side (the eventual web UI will use the browser geolocation API and forward the coordinates)
- The response must to at least include: flight identification, airline, aircraft model, origin, destination, current speed, current altitude in metres (barometric when available, geometric as a fallback), the aircraft's current latitude and longitude (so the client can plot it on a map) and the aircraft's true track (heading in decimal degrees clockwise from north) so the client can rotate the aircraft icon. When OpenSky does not provide the heading or the altitude, those fields must to be `null`
- The aircraft model and operating airline must to be derived from the aircraft's ICAO24 address using a public aircraft registry (e.g. `hexdb.io`); when the registry does not return a match, show `N/A`
- Origin and destination must to include the airport ICAO code, airport name, city/region and country code; these details must to be resolved from a public airport registry (e.g. `hexdb.io`). When the registry does not return a match, show `N/A` for the missing fields


### Quality & Continuous Integration

- The project must to have unit tests covering the main business logic (OpenSky client wrapper, airport/aircraft enrichment) and the HTTP API (status codes, request validation, serialization), written with `pytest`
- The HTTP endpoints must to be exercised via `fastapi.testclient.TestClient`, with OpenSky calls mocked so tests do not hit the network
- Test coverage must to be tracked with `pytest-cov` and reported automatically when running the test suite
- A GitHub Actions workflow must to run the test suite on every push to the `main` branch, and the build should fail if any test fails
