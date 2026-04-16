const REFRESH_MS = 20_000;

const el = (id) => document.getElementById(id);

function detectBrowserLocation() {
  if (!navigator.geolocation) {
    return Promise.reject(new Error("Browser geolocation not supported"));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          city: "",
          country: "",
        }),
      (err) => reject(new Error(err.message || "Geolocation permission denied")),
      { timeout: 10_000, maximumAge: 0 },
    );
  });
}

async function detectIpLocation() {
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

async function detectLocation() {
  try {
    return await detectBrowserLocation();
  } catch (err) {
    console.warn(`Browser geolocation failed: ${err.message}. Falling back to IP lookup.`);
    return await detectIpLocation();
  }
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

function hidePhoto() {
  el("f-photo").classList.add("hidden");
  el("f-photo-credit").classList.add("hidden");
}

function showPhoto(photo) {
  const img = el("f-photo");
  const credit = el("f-photo-credit");

  img.src = photo.thumbnail_url;
  img.classList.remove("hidden");

  credit.replaceChildren();
  credit.append("Photo © ");
  if (photo.link) {
    const anchor = document.createElement("a");
    anchor.href = photo.link;
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.textContent = photo.photographer;
    credit.appendChild(anchor);
  } else {
    credit.append(photo.photographer);
  }
  credit.append(" / planespotters.net");
  credit.classList.remove("hidden");
}

async function loadAircraftPhoto(icao24) {
  hidePhoto();
  if (!icao24) return;
  try {
    const response = await fetch(`/aircraft-photo?icao24=${icao24}`);
    if (!response.ok) return;
    const { photo } = await response.json();
    if (photo) showPhoto(photo);
  } catch (err) {
    console.warn(`photo lookup failed: ${err.message}`);
  }
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
  loadAircraftPhoto(flight.icao24);
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

  const label = coords.city && coords.country ? `${coords.city}, ${coords.country} ` : "";
  el("location-info").textContent = `Your location: ${label}(${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)})`;

  await refresh();
  setInterval(refresh, REFRESH_MS);
}

main();
