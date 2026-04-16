# Live Flight

Console app that shows the closest live flight to your current location using the [OpenSky Network API](https://openskynetwork.github.io/opensky-api/python.html). Data refreshes every 20 seconds.

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

## Run

```bash
poetry run live-flight
```

Or, from inside the virtual environment:

```bash
poetry shell
python -m live_flight.main
```

## What it does

1. Detects your location via IP geolocation (`ipapi.co`).
2. Authenticates against OpenSky using the credentials loaded from `.env`.
3. Every 20 seconds, queries aircraft within a bounding box around your location and prints the closest one — callsign, aircraft model, origin, destination, speed, and distance.

### Notes

- Origin/destination airports are resolved from OpenSky's recent flight history for the aircraft (ICAO codes). When no history is available, the field shows `N/A` and `origin_country` from the state vector is shown alongside.
- Aircraft model is resolved by looking up the ICAO24 address against the public [hexdb.io](https://hexdb.io/) aircraft registry; if the registry returns no match, the field shows `N/A`.
- Without credentials the app falls back to anonymous requests, which OpenSky rate-limits heavily.
