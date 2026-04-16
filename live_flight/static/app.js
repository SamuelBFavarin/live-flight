const REFRESH_MS = 20_000;

const el = (id) => document.getElementById(id);

async function detectLocation() {
  const response = await fetch("https://ipapi.co/json/");
  if (!response.ok) throw new Error(`IP geolocation failed (${response.status})`);
  const data = await response.json();
  if (data.latitude == null || data.longitude == null) {
    throw new Error("IP geolocation did not return coordinates");
  }
  return {
    lat: Number(data.latitude),
    lon: Number(data.longitude),
    city: data.city || "",
    country: data.country_name || "",
  };
}

async function fetchClosestFlight(lat, lon) {
  const response = await fetch(`/closest-flight?lat=${lat}&lon=${lon}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  const body = await response.json();
  return body.flight;
}

function formatAirport(airport) {
  return `${airport.icao} — ${airport.name} (${airport.city}, ${airport.country})`;
}

function renderFlight(flight) {
  const card = el("flight-card");
  const status = el("flight-status");

  if (!flight) {
    card.classList.add("hidden");
    status.textContent = "No aircraft currently within range.";
    return;
  }

  status.textContent = "Closest flight";
  card.classList.remove("hidden");
  el("f-callsign").textContent = flight.callsign;
  el("f-airline").textContent = flight.airline;
  el("f-aircraft").textContent = flight.aircraft_type;
  el("f-origin").textContent = formatAirport(flight.departure);
  el("f-destination").textContent = formatAirport(flight.arrival);
  el("f-speed").textContent = `${flight.speed_kmh.toFixed(1)} km/h`;
  el("f-distance").textContent = `${flight.distance_km.toFixed(1)} km`;
}

function setError(message) {
  el("flight-card").classList.add("hidden");
  el("flight-status").textContent = `Error: ${message}`;
}

let coords = null;

async function refresh() {
  try {
    const flight = await fetchClosestFlight(coords.lat, coords.lon);
    renderFlight(flight);
    el("last-updated").textContent = `Last updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    setError(err.message);
  }
}

async function main() {
  try {
    coords = await detectLocation();
  } catch (err) {
    el("location-info").textContent = `Couldn't detect location: ${err.message}`;
    return;
  }

  const label = coords.city && coords.country ? `${coords.city}, ${coords.country}` : "unknown place";
  el("location-info").textContent = `Your location: ${label} (${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)})`;

  await refresh();
  setInterval(refresh, REFRESH_MS);
}

main();
