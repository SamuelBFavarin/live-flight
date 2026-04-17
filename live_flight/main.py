import os
import socket
import subprocess

import uvicorn


def main() -> int:
    host = os.getenv("LIVE_FLIGHT_HOST", "127.0.0.1")
    port = int(os.getenv("LIVE_FLIGHT_PORT", "8000"))
    uvicorn.run("live_flight.api:app", host=host, port=port)
    return 0


def _mdns_hostname() -> str | None:
    try:
        out = subprocess.check_output(
            ["scutil", "--get", "LocalHostName"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out or None
    except Exception:
        return None


def _lan_ip() -> str | None:
    for iface in ("en0", "en1"):
        try:
            ip = subprocess.check_output(
                ["ipconfig", "getifaddr", iface], text=True, stderr=subprocess.DEVNULL
            ).strip()
            if ip:
                return ip
        except Exception:
            continue
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return None


def lan() -> int:
    port = int(os.getenv("LIVE_FLIGHT_PORT", "8000"))
    ip = _lan_ip()
    hostname = _mdns_hostname()
    print("Live Flight — reachable on your LAN at:")
    if hostname:
        print(f"  http://{hostname}.local:{port}   (Bonjour/mDNS)")
    if ip:
        print(f"  http://{ip}:{port}")
    if not ip and not hostname:
        print("  (could not detect LAN address — check your network)")
    print()
    uvicorn.run("live_flight.api:app", host="0.0.0.0", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
