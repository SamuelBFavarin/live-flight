import requests


def get_current_location() -> tuple[float, float]:
    response = requests.get("https://ipapi.co/json/", timeout=10)
    response.raise_for_status()
    data = response.json()
    return float(data["latitude"]), float(data["longitude"])
