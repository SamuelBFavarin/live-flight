import math
import time
from dataclasses import dataclass

import requests
from opensky_api import OpenSkyApi, StateVector

EARTH_RADIUS_KM = 6371.0
SEARCH_RADIUS_DEG = 3.0
FLIGHT_HISTORY_WINDOW_HOURS = 24
AIRCRAFT_DB_URL = "https://hexdb.io/api/v1/aircraft"
AIRPORT_DB_URL = "https://hexdb.io/api/v1/airport/icao"
ROUTE_DB_URL = "https://hexdb.io/api/v1/route/icao"
HEXDB_TIMEOUT = 5.0


@dataclass
class Airport:
    icao: str
    name: str
    city: str
    country: str
    latitude: float | None
    longitude: float | None

    @classmethod
    def unknown(cls, icao: str = "N/A") -> "Airport":
        return cls(
            icao=icao,
            name="N/A",
            city="N/A",
            country="N/A",
            latitude=None,
            longitude=None,
        )


@dataclass
class ClosestFlight:
    callsign: str
    icao24: str
    origin_country: str
    latitude: float
    longitude: float
    true_track: float | None
    altitude_m: float | None
    departure: Airport
    arrival: Airport
    aircraft_type: str
    airline: str
    speed_kmh: float
    distance_km: float


@dataclass
class TrackWaypoint:
    time: int | None
    latitude: float | None
    longitude: float | None
    baro_altitude: float | None
    true_track: float | None
    on_ground: bool


@dataclass
class AircraftTrack:
    icao24: str
    callsign: str | None
    start_time: int | None
    end_time: int | None
    path: list[TrackWaypoint]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _bounding_box(lat: float, lon: float, radius_deg: float) -> tuple[float, float, float, float]:
    return (lat - radius_deg, lat + radius_deg, lon - radius_deg, lon + radius_deg)


def _nearest_state(states: list[StateVector], lat: float, lon: float) -> tuple[StateVector, float] | None:
    candidates = [
        (s, haversine_km(lat, lon, s.latitude, s.longitude))
        for s in states
        if s.latitude is not None and s.longitude is not None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1])


def _lookup_aircraft_info(icao24: str) -> tuple[str, str]:
    try:
        response = requests.get(f"{AIRCRAFT_DB_URL}/{icao24}", timeout=HEXDB_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return ("N/A", "N/A")
    manufacturer = (data.get("Manufacturer") or "").strip()
    model = (data.get("Type") or "").strip()
    airline = (data.get("RegisteredOwners") or "").strip()
    aircraft_type = f"{manufacturer} {model}".strip() or "N/A"
    return (aircraft_type, airline or "N/A")


def _lookup_airport(icao: str) -> Airport:
    if not icao or icao == "N/A":
        return Airport.unknown()
    try:
        response = requests.get(f"{AIRPORT_DB_URL}/{icao}", timeout=HEXDB_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return Airport.unknown(icao=icao)
    lat = data.get("latitude")
    lon = data.get("longitude")
    return Airport(
        icao=icao,
        name=(data.get("airport") or "").strip() or "N/A",
        city=(data.get("region_name") or "").strip() or "N/A",
        country=(data.get("country_code") or "").strip() or "N/A",
        latitude=float(lat) if isinstance(lat, (int, float)) else None,
        longitude=float(lon) if isinstance(lon, (int, float)) else None,
    )


def _lookup_route_by_callsign(callsign: str) -> tuple[str, str]:
    if not callsign or callsign == "N/A":
        return ("N/A", "N/A")
    try:
        response = requests.get(f"{ROUTE_DB_URL}/{callsign}", timeout=HEXDB_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return ("N/A", "N/A")
    route = (data.get("route") or "").strip()
    if "-" not in route:
        return ("N/A", "N/A")
    parts = [part.strip() for part in route.split("-")]
    return (parts[0] or "N/A", parts[-1] or "N/A")


def _resolve_route(api: OpenSkyApi, icao24: str, callsign: str) -> tuple[str, str]:
    dep, arr = _lookup_route_by_callsign(callsign)
    if dep != "N/A" and arr != "N/A":
        return dep, arr
    hist_dep, hist_arr = _lookup_route(api, icao24)
    return (
        dep if dep != "N/A" else hist_dep,
        arr if arr != "N/A" else hist_arr,
    )


def _lookup_route(api: OpenSkyApi, icao24: str) -> tuple[str, str]:
    now = int(time.time())
    begin = now - FLIGHT_HISTORY_WINDOW_HOURS * 3600
    try:
        flights = api.get_flights_by_aircraft(icao24, begin, now)
    except Exception:
        return ("N/A", "N/A")
    if not flights:
        return ("N/A", "N/A")
    last = flights[-1]
    return (last.estDepartureAirport or "N/A", last.estArrivalAirport or "N/A")


def fetch_aircraft_track(api: OpenSkyApi, icao24: str) -> AircraftTrack | None:
    try:
        track = api.get_track_by_aircraft(icao24)
    except Exception:
        return None
    if track is None:
        return None
    raw_path = getattr(track, "path", None) or []
    path = [
        TrackWaypoint(
            time=getattr(wp, "time", None),
            latitude=getattr(wp, "latitude", None),
            longitude=getattr(wp, "longitude", None),
            baro_altitude=getattr(wp, "baro_altitude", None),
            true_track=getattr(wp, "true_track", None),
            on_ground=bool(getattr(wp, "on_ground", False)),
        )
        for wp in raw_path
    ]
    return AircraftTrack(
        icao24=icao24,
        callsign=(getattr(track, "callsign", None) or "").strip() or None,
        start_time=getattr(track, "startTime", None),
        end_time=getattr(track, "endTime", None),
        path=path,
    )


def find_closest_flight(api: OpenSkyApi, lat: float, lon: float) -> ClosestFlight | None:
    bbox = _bounding_box(lat, lon, SEARCH_RADIUS_DEG)
    states_response = api.get_states(bbox=bbox)
    if states_response is None or not states_response.states:
        return None

    nearest = _nearest_state(states_response.states, lat, lon)
    if nearest is None:
        return None

    state, distance = nearest
    callsign = (state.callsign or "").strip() or "N/A"
    departure_icao, arrival_icao = _resolve_route(api, state.icao24, callsign)
    aircraft_type, airline = _lookup_aircraft_info(state.icao24)
    speed_kmh = (state.velocity or 0.0) * 3.6
    altitude_m = state.baro_altitude if state.baro_altitude is not None else state.geo_altitude

    return ClosestFlight(
        callsign=callsign,
        icao24=state.icao24,
        origin_country=state.origin_country or "N/A",
        latitude=state.latitude,
        longitude=state.longitude,
        true_track=state.true_track,
        altitude_m=altitude_m,
        departure=_lookup_airport(departure_icao),
        arrival=_lookup_airport(arrival_icao),
        aircraft_type=aircraft_type,
        airline=airline,
        speed_kmh=speed_kmh,
        distance_km=distance,
    )
