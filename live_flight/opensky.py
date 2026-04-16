import math
import time
from dataclasses import dataclass

from opensky_api import OpenSkyApi, StateVector

EARTH_RADIUS_KM = 6371.0
SEARCH_RADIUS_DEG = 3.0
FLIGHT_HISTORY_WINDOW_HOURS = 24


@dataclass
class ClosestFlight:
    callsign: str
    origin_country: str
    departure_airport: str
    arrival_airport: str
    speed_kmh: float
    distance_km: float


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


def find_closest_flight(api: OpenSkyApi, lat: float, lon: float) -> ClosestFlight | None:
    bbox = _bounding_box(lat, lon, SEARCH_RADIUS_DEG)
    states_response = api.get_states(bbox=bbox)
    if states_response is None or not states_response.states:
        return None

    nearest = _nearest_state(states_response.states, lat, lon)
    if nearest is None:
        return None

    state, distance = nearest
    departure, arrival = _lookup_route(api, state.icao24)
    speed_kmh = (state.velocity or 0.0) * 3.6

    return ClosestFlight(
        callsign=(state.callsign or "").strip() or "N/A",
        origin_country=state.origin_country or "N/A",
        departure_airport=departure,
        arrival_airport=arrival,
        speed_kmh=speed_kmh,
        distance_km=distance,
    )
