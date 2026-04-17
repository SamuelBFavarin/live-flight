const REFRESH_MS = 20_000;
const MAP_RADIUS_METERS = 50_000; // 50 km radius -> ~100 km viewport

const el = (id) => document.getElementById(id);

const EARTH_RADIUS_M = 6_371_000;

let map = null;
let userMarker = null;
let flightMarker = null;
let deadReckonState = null;

function destinationPoint(lat, lon, distanceM, bearingDeg) {
  const angular = distanceM / EARTH_RADIUS_M;
  const bearing = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) +
      Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    );
  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

function animationFrame(timestamp) {
  if (deadReckonState && flightMarker) {
    const dt = (timestamp - deadReckonState.lastFrameTime) / 1000;
    deadReckonState.lastFrameTime = timestamp;
    const [nextLat, nextLon] = destinationPoint(
      deadReckonState.lat,
      deadReckonState.lon,
      deadReckonState.speedMps * dt,
      deadReckonState.heading,
    );
    deadReckonState.lat = nextLat;
    deadReckonState.lon = nextLon;
    flightMarker.setLatLng([nextLat, nextLon]);
  }
  requestAnimationFrame(animationFrame);
}

requestAnimationFrame(animationFrame);

const PLANE_SVG = `<svg viewBox="0 0 24 24" width="28" height="28" xmlns="http://www.w3.org/2000/svg"><path d="M21,16v-2l-8-5V3.5C13,2.67 12.33,2 11.5,2C10.67,2 10,2.67 10,3.5V9l-8,5v2l8-2.5V19l-2,1.5V22l3.5-1l3.5,1v-1.5L13,19v-5.5L21,16z" fill="#f8fafc" stroke="#0f172a" stroke-width="0.5" stroke-linejoin="round"/></svg>`;

function planeIcon(heading) {
  const rotation = Number.isFinite(heading) ? heading : 0;
  return L.divIcon({
    html: `<div class="plane-marker" style="transform: rotate(${rotation}deg)">${PLANE_SVG}</div>`,
    className: "plane-icon",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function initMap(initialCoords) {
  const center = L.latLng(initialCoords.lat, initialCoords.lon);
  map = L.map("map").fitBounds(center.toBounds(MAP_RADIUS_METERS * 2));
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    subdomains: "abcd",
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(map);
  L.control.scale({ imperial: false, metric: true, maxWidth: 150 }).addTo(map);
  userMarker = L.marker(center, { draggable: true })
    .addTo(map)
    .bindTooltip("Drag me to explore another location", { direction: "top", offset: [0, -10] });
  userMarker.on("dragend", onUserMarkerDragEnd);
}

async function onUserMarkerDragEnd(event) {
  const latlng = event.target.getLatLng();
  coords = { lat: latlng.lat, lon: latlng.lng, city: "", country: "" };
  el("location-info").textContent =
    `Custom location: (${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)})`;
  el("flight-status").textContent = "Fetching closest flight for the new location…";
  await refresh();
}

function updateFlightMarker(flight) {
  if (!map) return;
  if (!flight || flight.latitude == null || flight.longitude == null) {
    if (flightMarker) {
      flightMarker.remove();
      flightMarker = null;
    }
    deadReckonState = null;
    return;
  }
  const position = [flight.latitude, flight.longitude];
  const icon = planeIcon(flight.true_track);
  if (!flightMarker) {
    flightMarker = L.marker(position, { icon }).addTo(map);
  } else {
    flightMarker.setLatLng(position);
    flightMarker.setIcon(icon);
  }
  flightMarker.bindPopup(`${flight.callsign} — ${flight.airline}`);

  if (
    Number.isFinite(flight.true_track) &&
    Number.isFinite(flight.speed_kmh) &&
    flight.speed_kmh > 0
  ) {
    deadReckonState = {
      lat: flight.latitude,
      lon: flight.longitude,
      heading: flight.true_track,
      speedMps: flight.speed_kmh / 3.6,
      lastFrameTime: performance.now(),
    };
  } else {
    deadReckonState = null;
  }
}

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
    updateFlightMarker(null);
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
  el("f-altitude").textContent =
    flight.altitude_m == null ? "N/A" : `${Math.round(flight.altitude_m).toLocaleString()} m`;
  el("f-distance").textContent = `${flight.distance_km.toFixed(1)} km`;
  loadAircraftPhoto(flight.icao24);
  updateFlightMarker(flight);
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

  initMap(coords);

  await refresh();
  setInterval(refresh, REFRESH_MS);
}

main();
