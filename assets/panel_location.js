// Location panel: stands in for the phone's GPS. Click the map to jump there,
// pick a place, type coordinates, or draw a route and drive it at the car's
// speed (Car panel). Every position goes to the companion as a "location"
// message, as the phone will send it over BLE. The map uses Leaflet with
// OpenStreetMap tiles, both loaded from the internet; without them the
// buttons and coordinates still work.

import { button } from './dom.js';

const START = [46.6, 11.62]; // where the map opens before there is a position
const SEND_EVERY_MS = 500;   // how often a driving route reports its position
const STEP_MS = 100;         // route player tick

export class LocationPanel {
  constructor(root, send) {
    this.send = send;
    this.places = [];
    this.margin = 0.2;
    this.speed = 0;         // km/h, from the Car panel
    this.route = [];        // [lat, lon] points
    this.drawing = false;
    this.driving = null;    // timer while driving
    this.at = null;         // {leg, metres along it} while driving
    this.lastSent = 0;
    this.placeButtons = root.querySelector('#place-buttons');
    this.info = root.querySelector('#location-info');
    this.routeInfo = root.querySelector('#route-info');
    this.lat = root.querySelector('#lat');
    this.lon = root.querySelector('#lon');
    root.querySelector('#go').addEventListener('click', () => this.jump(Number(this.lat.value), Number(this.lon.value)));
    this.drawButton = root.querySelector('#route-draw');
    this.driveButton = root.querySelector('#route-drive');
    this.timeScale = root.querySelector('#time-scale');
    this.drawButton.addEventListener('click', () => this.#toggleDrawing());
    this.driveButton.addEventListener('click', () => (this.driving ? this.#stop() : this.#drive()));
    root.querySelector('#route-clear').addEventListener('click', () => this.#clearRoute());
    this.map = window.L ? this.#makeMap(root.querySelector('#map')) : null;
    if (!this.map) root.querySelector('#map').textContent = 'The map could not load (no internet?). Places and coordinates still work.';
    this.#showRoute();
  }

  setConfig(config) {
    this.places = config.places.places;
    this.margin = config.settings.place_exit_margin;
    this.placeButtons.replaceChildren(...this.places.map((p) => button(p.name, () => this.jump(p.lat, p.lon))));
    if (!this.map) return;
    this.placeLayer.clearLayers();
    for (const p of this.places) {
      L.circle([p.lat, p.lon], { radius: p.radius_m * (1 + this.margin), color: '#00e5ff', weight: 2, opacity: 0.9, dashArray: '6 6', fill: false, interactive: false })
        .addTo(this.placeLayer);
      L.circle([p.lat, p.lon], { radius: p.radius_m, color: '#00e5ff', weight: 2, fillOpacity: 0.12 })
        .bindTooltip(p.name).addTo(this.placeLayer);
    }
  }

  setCar(car) {
    this.speed = car.speed_kmh;
    this.#showRoute();
  }

  // Where the companion thinks we are (status.location), e.g. sent by another tab.
  setStatus(status) {
    const pos = status.location;
    const place = this.places.find((p) => p.id === status.place);
    this.info.textContent = pos
      ? `${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)} · ${place ? `in ${place.name}` : 'not in a place'}`
      : 'No position yet: click the map or pick a place.';
    if (pos && this.map) this.#moveMarker(pos.lat, pos.lon);
  }

  jump(lat, lon) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    this.#stop();
    this.#report(lat, lon);
    this.map?.panTo([lat, lon]);
  }

  #report(lat, lon) {
    this.send({ type: 'location', lat: round(lat), lon: round(lon) });
    this.lat.value = round(lat);
    this.lon.value = round(lon);
    if (this.map) this.#moveMarker(lat, lon);
  }

  #makeMap(div) {
    const map = L.map(div).setView(START, 11);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    this.placeLayer = L.layerGroup().addTo(map);
    this.routeLine = L.polyline([], { color: '#ffc94d', weight: 3 }).addTo(map);
    this.marker = L.circleMarker(START, { radius: 7, color: '#fff', weight: 2, fillColor: '#ff4d3a', fillOpacity: 1 });
    map.on('click', (e) => {
      if (this.drawing) {
        this.route.push([e.latlng.lat, e.latlng.lng]);
        this.#showRoute();
      } else {
        this.jump(e.latlng.lat, e.latlng.lng);
      }
    });
    return map;
  }

  #moveMarker(lat, lon) {
    this.marker.setLatLng([lat, lon]);
    if (!this.map.hasLayer(this.marker)) this.marker.addTo(this.map);
  }

  // ---- route --------------------------------------------------------------------

  #toggleDrawing() {
    this.drawing = !this.drawing;
    if (this.drawing) this.#stop();
    this.#showRoute();
  }

  #clearRoute() {
    this.#stop();
    this.route = [];
    this.at = null;
    this.#showRoute();
  }

  #drive() {
    if (this.route.length < 2) return;
    this.drawing = false;
    this.at = this.at ?? { leg: 0, metres: 0 };
    this.driving = setInterval(() => this.#step(), STEP_MS);
    this.#showRoute();
  }

  #stop() {
    clearInterval(this.driving);
    this.driving = null;
    this.#showRoute();
  }

  // Move along the route by the distance the car covers in one tick (sped up by the time scale).
  #step() {
    let metres = (this.speed / 3.6) * (STEP_MS / 1000) * Number(this.timeScale.value);
    while (this.at.leg < this.route.length - 1) {
      const [a, b] = [this.route[this.at.leg], this.route[this.at.leg + 1]];
      const length = distance(a, b);
      if (this.at.metres + metres <= length) {
        this.at.metres += metres;
        break;
      }
      metres -= length - this.at.metres;
      this.at = { leg: this.at.leg + 1, metres: 0 };
    }
    const done = this.at.leg >= this.route.length - 1;
    const pos = done ? this.route.at(-1) : along(this.route[this.at.leg], this.route[this.at.leg + 1], this.at.metres);
    const now = performance.now();
    if (done || now - this.lastSent >= SEND_EVERY_MS) {
      this.lastSent = now;
      this.#report(pos[0], pos[1]);
    }
    if (done) {
      this.at = null;
      this.#stop();
    }
  }

  #showRoute() {
    this.routeLine?.setLatLngs(this.route);
    this.drawButton.classList.toggle('active', this.drawing);
    this.drawButton.textContent = this.drawing ? 'Done drawing' : 'Draw route';
    this.driveButton.textContent = this.driving ? 'Stop' : this.at ? 'Continue' : 'Drive route';
    let text;
    if (this.drawing) text = `Click the map to add points (${this.route.length} so far).`;
    else if (this.route.length < 2) text = 'Draw a route with at least two points, then drive it.';
    else if (this.driving && this.speed === 0) text = 'Driving at 0 km/h: set a speed in the Car panel.';
    else text = `${(routeLength(this.route) / 1000).toFixed(1)} km, driven at the Car panel's speed (${Math.round(this.speed)} km/h).`;
    this.routeInfo.textContent = text;
  }
}

// ---- geometry (good enough for a few kilometres) -------------------------------

function distance([lat1, lon1], [lat2, lon2]) {
  const r = 6371000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = p2 - p1;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

function along(a, b, metres) {
  const k = Math.min(1, metres / (distance(a, b) || 1));
  return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
}

function routeLength(route) {
  return route.slice(1).reduce((sum, p, i) => sum + distance(route[i], p), 0);
}

function round(x) {
  return Math.round(x * 1e6) / 1e6;
}
