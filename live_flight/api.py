import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from opensky_api import OpenSkyApi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from live_flight.opensky import find_closest_flight
from live_flight.photos import fetch_aircraft_photo

CLOSEST_FLIGHT_RATE_LIMIT = "10/minute"

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


def _build_opensky_client() -> OpenSkyApi:
    client_id = os.getenv("OPENSKY_CLIENT_ID")
    client_secret = os.getenv("OPENSKY_CLIENT_SECRET")
    if client_id and client_secret:
        return OpenSkyApi(client_id=client_id, client_secret=client_secret)
    logger.warning(
        "OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET not set — anonymous OpenSky access (rate-limited)"
    )
    return OpenSkyApi()


load_dotenv()

limiter = Limiter(key_func=get_remote_address, strategy="moving-window")

app = FastAPI(
    title="Live Flight API",
    version="0.1.0",
    description="HTTP API that returns the closest live flight to a given location.",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

opensky_client = _build_opensky_client()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


@app.get("/status", summary="Health check")
def get_status() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/closest-flight", summary="Closest live flight to a location")
@limiter.limit(CLOSEST_FLIGHT_RATE_LIMIT)
def get_closest_flight(
    request: Request,
    lat: float = Query(..., ge=-90, le=90, description="Latitude in decimal degrees."),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in decimal degrees."),
) -> dict[str, Any]:
    try:
        flight = find_closest_flight(opensky_client, lat, lon)
    except Exception as exc:
        logger.exception("failed to fetch closest flight")
        raise HTTPException(status_code=500, detail=f"Upstream error: {exc}")
    return {"flight": asdict(flight) if flight is not None else None}


@app.get("/aircraft-photo", summary="Photo of an aircraft by ICAO24 address")
def get_aircraft_photo(
    icao24: str = Query(
        ...,
        pattern=r"^[a-fA-F0-9]{6}$",
        description="6-character hex ICAO24 transponder address.",
    ),
) -> dict[str, Any]:
    try:
        photo = fetch_aircraft_photo(icao24.lower())
    except Exception as exc:
        logger.exception("failed to fetch aircraft photo")
        raise HTTPException(status_code=500, detail=f"Photo lookup failed: {exc}")
    return {"photo": asdict(photo) if photo is not None else None}
