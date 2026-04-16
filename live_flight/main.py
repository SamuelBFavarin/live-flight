import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from opensky_api import OpenSkyApi

from live_flight.location import get_current_location
from live_flight.opensky import find_closest_flight

REFRESH_SECONDS = 20


def _build_api() -> OpenSkyApi:
    client_id = os.getenv("OPENSKY_CLIENT_ID")
    client_secret = os.getenv("OPENSKY_CLIENT_SECRET")
    if client_id and client_secret:
        return OpenSkyApi(client_id=client_id, client_secret=client_secret)
    print("[warn] OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET not set — using anonymous access (rate-limited).")
    return OpenSkyApi()


def _print_flight(lat: float, lon: float, api: OpenSkyApi) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        flight = find_closest_flight(api, lat, lon)
    except Exception as exc:
        print(f"[{timestamp}] error fetching flight data: {exc}")
        return

    if flight is None:
        print(f"[{timestamp}] no flights found near ({lat:.4f}, {lon:.4f}).")
        return

    print(
        f"[{timestamp}] closest flight: {flight.callsign} | "
        f"origin: {flight.departure_airport} ({flight.origin_country}) | "
        f"destination: {flight.arrival_airport} | "
        f"speed: {flight.speed_kmh:.1f} km/h | "
        f"distance: {flight.distance_km:.1f} km"
    )


def main() -> int:
    load_dotenv()
    api = _build_api()

    try:
        lat, lon = get_current_location()
    except Exception as exc:
        print(f"failed to detect current location: {exc}", file=sys.stderr)
        return 1

    print(f"current location: ({lat:.4f}, {lon:.4f}). Refreshing every {REFRESH_SECONDS}s. Ctrl+C to quit.")

    try:
        while True:
            _print_flight(lat, lon, api)
            time.sleep(REFRESH_SECONDS)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
