// Car panel: stands in for the OBD-II dongle (and the board's motion sensor).
// The sliders set values on the companion's simulated car
// (python/companion/car_sim.py); scenarios play scripted drives there.
// Values coming back keep the sliders in sync, e.g. during a scenario.

import { button, el, words } from './dom.js';

const SLIDERS = [
  { field: 'speed_kmh', label: 'Speed', min: 0, max: 260, step: 1, unit: 'km/h' },
  { field: 'rpm', label: 'RPM', min: 0, max: 8000, step: 50, unit: '' },
  { field: 'oil_c', label: 'Oil', min: -20, max: 150, step: 1, unit: '°C' },
  { field: 'coolant_c', label: 'Coolant', min: -20, max: 130, step: 1, unit: '°C' },
  { field: 'g_long', label: 'Long. g', min: -1.5, max: 1.5, step: 0.05, unit: 'g' },
  { field: 'g_lat', label: 'Lat. g', min: -1.5, max: 1.5, step: 0.05, unit: 'g' },
];
const HOLD_MS = 800; // after you move a slider, values from the companion wait this long
const SHAKE = { g: 1.0, s: 2 }; // what "Shake the board" pretends the sensor measures

export class CarPanel {
  constructor(root, send) {
    this.send = send;
    this.thresholds = {};
    this.rows = {};
    this.touched = {};   // field -> when you last moved it
    this.pending = null; // slider values waiting for the next animation frame
    const box = root.querySelector('#sliders');
    for (const spec of SLIDERS) {
      const input = el('input', { type: 'range', min: spec.min, max: spec.max, step: spec.step, value: 0 });
      const out = el('output');
      input.addEventListener('input', () => {
        this.touched[spec.field] = performance.now();
        this.#show(spec, Number(input.value));
        this.#queue(spec.field, Number(input.value));
      });
      box.append(el('label', { className: 'slider' }, el('span', { textContent: spec.label }), input, out));
      this.rows[spec.field] = { spec, input, out };
    }
    this.ignition = root.querySelector('#ignition');
    this.ignition.addEventListener('change', () => this.send({ type: 'sim_car', ignition: this.ignition.checked }));
    this.motion = root.querySelector('#motion');
    root.querySelector('#shake').addEventListener('click', () => this.send({ type: 'sim_motion', ...SHAKE }));
    this.scenarios = root.querySelector('#scenarios');
  }

  setScenarios(names) {
    this.scenarios.replaceChildren(...names.map((name) => {
      const b = button(words(name), () => this.send({ type: 'sim_scenario', name }));
      b.dataset.name = name;
      return b;
    }));
  }

  setConfig(config) {
    this.thresholds = config.settings.thresholds;
  }

  setCar(car) {
    for (const { spec, input } of Object.values(this.rows)) {
      if (performance.now() - (this.touched[spec.field] ?? -Infinity) < HOLD_MS) continue;
      input.value = car[spec.field];
      this.#show(spec, car[spec.field]);
    }
    this.ignition.checked = car.ignition;
    this.motion.textContent = car.motion_g == null
      ? 'no data (no Modulino Movement connected)'
      : `${car.motion_g.toFixed(2)} g${car.sensor ? ' from the sensor' : ' (simulated)'}`;
    for (const b of this.scenarios.children) b.classList.toggle('active', b.dataset.name === car.scenario);
  }

  // Sliders send at most one message per animation frame while you drag.
  #queue(field, value) {
    if (!this.pending) {
      this.pending = {};
      requestAnimationFrame(() => {
        this.send({ type: 'sim_car', ...this.pending });
        this.pending = null;
      });
    }
    this.pending[field] = value;
  }

  #show(spec, value) {
    const row = this.rows[spec.field];
    let text = `${value.toFixed(spec.step < 1 ? 2 : 0)} ${spec.unit}`;
    if (spec.field === 'speed_kmh') {
      const { slow_kmh: slow, fast_kmh: fast } = this.thresholds;
      if (value < slow) text += ' · stopped';
      else if (value > fast) text += ' · fast';
    }
    row.out.textContent = text;
    row.out.classList.toggle('alert', spec.field === 'rpm' && value >= this.thresholds.redline_rpm);
  }
}
