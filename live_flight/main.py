import os

import uvicorn


def main() -> int:
    host = os.getenv("LIVE_FLIGHT_HOST", "127.0.0.1")
    port = int(os.getenv("LIVE_FLIGHT_PORT", "8000"))
    uvicorn.run("live_flight.api:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
