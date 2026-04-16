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
- `GET /` — serves the web UI's entry HTML document.
- `GET /static/*` — serves the web UI's static assets (CSS, JS).


### Web UI

- The API must to ship a minimal web UI reachable at `/`, implemented with plain HTML, CSS and JavaScript (no build step, no framework).
- On load, the UI must to detect the visitor's approximate location from their IP using a public client-side geolocation service (e.g. `ipapi.co`). The backend must not be involved in the location lookup.
- Using those coordinates, the UI must to call the `/closest-flight` endpoint and render the response (callsign, airline, aircraft model, origin, destination, speed, distance).
- The UI must to auto-refresh the flight information every 20 seconds; the IP-based location is only fetched once, at page load.
- Errors from either the geolocation service or the API must to be surfaced to the user.


### Business Rules

- The system must to authenticate to the OpenSky API using the OAuth2 client credentials (client id + client secret) defined in the environment variables
- The `/closest-flight` endpoint must to accept latitude and longitude from the caller; it does not detect the location server-side (the eventual web UI will use the browser geolocation API and forward the coordinates)
- The response must to at least include: flight identification, airline, aircraft model, origin, destination and speed
- The aircraft model and operating airline must to be derived from the aircraft's ICAO24 address using a public aircraft registry (e.g. `hexdb.io`); when the registry does not return a match, show `N/A`
- Origin and destination must to include the airport ICAO code, airport name, city/region and country code; these details must to be resolved from a public airport registry (e.g. `hexdb.io`). When the registry does not return a match, show `N/A` for the missing fields


### Quality & Continuous Integration

- The project must to have unit tests covering the main business logic (OpenSky client wrapper, airport/aircraft enrichment) and the HTTP API (status codes, request validation, serialization), written with `pytest`
- The HTTP endpoints must to be exercised via `fastapi.testclient.TestClient`, with OpenSky calls mocked so tests do not hit the network
- Test coverage must to be tracked with `pytest-cov` and reported automatically when running the test suite
- A GitHub Actions workflow must to run the test suite on every push to the `main` branch, and the build should fail if any test fails
