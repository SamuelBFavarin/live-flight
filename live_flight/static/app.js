const REFRESH_MS = 20_000;
const MAP_RADIUS_METERS = 50_000; // 50 km radius -> ~100 km viewport

const el = (id) => document.getElementById(id);

const EARTH_RADIUS_M = 6_371_000;

let map = null;
let userMarker = null;
let flightMarker = null;
let airportSegment = null;
let aircraftTrail = null;
let currentFlight = null;
let currentTrack = null;
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
    updateTrailTail(nextLat, nextLon);
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
  scheduleRefreshTimer();
}

function removeTrail() {
  if (airportSegment) {
    airportSegment.remove();
    airportSegment = null;
  }
  if (aircraftTrail) {
    aircraftTrail.remove();
    aircraftTrail = null;
  }
}

function trackPathPoints(track) {
  if (!track || !Array.isArray(track.path)) return [];
  const points = [];
  for (const wp of track.path) {
    if (wp.latitude != null && wp.longitude != null) {
      points.push([wp.latitude, wp.longitude]);
    }
  }
  return points;
}

function updateFlightTrail(flight, track) {
  if (!map) return;
  if (!flight || flight.latitude == null || flight.longitude == null) {
    removeTrail();
    return;
  }

  const departure = flight.departure;
  const hasDeparture =
    departure &&
    departure.latitude != null &&
    departure.longitude != null;

  const trackPoints = trackPathPoints(track);
  const trailPoints = trackPoints.slice();
  trailPoints.push([flight.latitude, flight.longitude]);

  if (trailPoints.length >= 2) {
    if (!aircraftTrail) {
      aircraftTrail = L.polyline(trailPoints, {
        color: "#38bdf8",
        weight: 2.5,
        opacity: 0.85,
      }).addTo(map);
    } else {
      aircraftTrail.setLatLngs(trailPoints);
    }
  } else if (aircraftTrail) {
    aircraftTrail.remove();
    aircraftTrail = null;
  }

  if (hasDeparture) {
    const connector = trackPoints.length
      ? trackPoints[0]
      : [flight.latitude, flight.longitude];
    const segment = [[departure.latitude, departure.longitude], connector];
    if (!airportSegment) {
      airportSegment = L.polyline(segment, {
        color: "#38bdf8",
        weight: 2,
        opacity: 0.55,
        dashArray: "6, 8",
      }).addTo(map);
    } else {
      airportSegment.setLatLngs(segment);
    }
  } else if (airportSegment) {
    airportSegment.remove();
    airportSegment = null;
  }
}

function updateTrailTail(lat, lon) {
  if (!aircraftTrail) return;
  const latlngs = aircraftTrail.getLatLngs();
  if (latlngs.length === 0) return;
  latlngs[latlngs.length - 1] = L.latLng(lat, lon);
  aircraftTrail.setLatLngs(latlngs);
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

const IP_LOOKUP_PROVIDERS = [
  {
    name: "ipapi.co",
    url: "https://ipapi.co/json/",
    extract: (data) => ({
      lat: Number(data.latitude),
      lon: Number(data.longitude),
      city: data.city || "",
      country: data.country_name || "",
    }),
  },
  {
    name: "ipwho.is",
    url: "https://ipwho.is/",
    extract: (data) => ({
      lat: Number(data.latitude),
      lon: Number(data.longitude),
      city: data.city || "",
      country: data.country || "",
    }),
  },
];

async function detectIpLocation() {
  const errors = [];
  for (const provider of IP_LOOKUP_PROVIDERS) {
    try {
      const response = await fetch(provider.url);
      if (!response.ok) {
        errors.push(`${provider.name} ${response.status}`);
        continue;
      }
      const data = await response.json();
      const extracted = provider.extract(data);
      if (Number.isFinite(extracted.lat) && Number.isFinite(extracted.lon)) {
        return extracted;
      }
      errors.push(`${provider.name} no coords`);
    } catch (err) {
      errors.push(`${provider.name} ${err.message}`);
    }
  }
  throw new Error(`all IP lookups failed (${errors.join("; ")})`);
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
  if (!response.ok) {
    let detail = `API returned ${response.status}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch {
      // non-JSON response; stick with the default detail
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
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

const photoCache = new Map();
let currentPhotoIcao = null;

function applyPhoto(photo) {
  if (photo) showPhoto(photo);
  else hidePhoto();
}

async function loadAircraftPhoto(icao24) {
  if (!icao24) {
    hidePhoto();
    currentPhotoIcao = null;
    return;
  }
  if (icao24 === currentPhotoIcao) {
    return;
  }
  if (photoCache.has(icao24)) {
    applyPhoto(photoCache.get(icao24));
    currentPhotoIcao = icao24;
    return;
  }
  hidePhoto();
  try {
    const response = await fetch(`/aircraft-photo?icao24=${icao24}`);
    if (!response.ok) return;
    const { photo } = await response.json();
    photoCache.set(icao24, photo);
    applyPhoto(photo);
    currentPhotoIcao = icao24;
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
    currentFlight = null;
    currentTrack = null;
    updateFlightMarker(null);
    updateFlightTrail(null, null);
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
  if (currentFlight && currentFlight.icao24 !== flight.icao24) {
    currentTrack = null;
  }
  currentFlight = flight;
  updateFlightTrail(flight, currentTrack);
}

async function loadFlightTrack(icao24) {
  if (!icao24) return null;
  try {
    const response = await fetch(`/flight-track?icao24=${icao24}`);
    if (!response.ok) return null;
    const body = await response.json();
    return body.track;
  } catch {
    return null;
  }
}

function setError(message) {
  el("flight-card").classList.add("hidden");
  el("flight-status").textContent = `Error: ${message}`;
}

const RATE_LIMIT_COOLDOWN_MS = 60_000;

let coords = null;
let refreshTimer = null;
let cooldownTimer = null;

function clearRefreshTimer() {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function scheduleRefreshTimer() {
  clearRefreshTimer();
  refreshTimer = setInterval(refresh, REFRESH_MS);
}

function startRateLimitCooldown() {
  clearRefreshTimer();
  if (cooldownTimer !== null) {
    clearInterval(cooldownTimer);
  }

  const modal = el("rate-limit-modal");
  const countdown = el("rate-limit-countdown");
  const startedAt = Date.now();

  modal.classList.remove("hidden");
  countdown.textContent = "60";

  cooldownTimer = setInterval(() => {
    const remaining = Math.max(
      0,
      Math.ceil((RATE_LIMIT_COOLDOWN_MS - (Date.now() - startedAt)) / 1000),
    );
    countdown.textContent = String(remaining);
    if (remaining <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
      modal.classList.add("hidden");
      refresh();
      scheduleRefreshTimer();
    }
  }, 250);
}

async function refresh() {
  if (cooldownTimer !== null) return;
  try {
    const flight = await fetchClosestFlight(coords.lat, coords.lon);
    renderFlight(flight);
    el("last-updated").textContent = `Last updated ${new Date().toLocaleTimeString()}`;
    if (flight && flight.icao24) {
      const icao24 = flight.icao24;
      loadFlightTrack(icao24).then((track) => {
        if (currentFlight && currentFlight.icao24 === icao24) {
          currentTrack = track;
          updateFlightTrail(currentFlight, currentTrack);
        }
      });
    }
  } catch (err) {
    if (err.status === 429) {
      startRateLimitCooldown();
      return;
    }
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
  scheduleRefreshTimer();
}

main();
