import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

PLANESPOTTERS_URL = "https://api.planespotters.net/pub/photos/hex"
PLANESPOTTERS_TIMEOUT = 5.0


@dataclass
class AircraftPhoto:
    thumbnail_url: str
    photographer: str
    link: str


def fetch_aircraft_photo(icao24: str) -> AircraftPhoto | None:
    try:
        response = requests.get(f"{PLANESPOTTERS_URL}/{icao24}", timeout=PLANESPOTTERS_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.exception("planespotters lookup failed for %s", icao24)
        return None

    photos = data.get("photos") or []
    if not photos:
        return None

    first = photos[0]
    thumbnail = first.get("thumbnail_large") or first.get("thumbnail") or {}
    url = (thumbnail.get("src") or "").strip()
    if not url:
        return None

    return AircraftPhoto(
        thumbnail_url=url,
        photographer=(first.get("photographer") or "").strip() or "Unknown",
        link=(first.get("link") or "").strip(),
    )
