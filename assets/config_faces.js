// Faces tab: how each mood looks. Sliders change the selected mood, the
// preview draws it exactly like the display. Nothing is sent until you press
// Save; then faces.json is replaced (config_set) and applies at once.
//
// A mood only stores what differs from the default mood; ↺ next to a value
// removes it again (the mood then inherits it). "Left eye" / "Right eye"
// change one eye only.

import { CanvasRenderer } from './render_canvas.js';
import { button, el } from './dom.js';
import { saveConfig, showMessage } from './config_common.js';

const EYE_KEYS = ['w', 'h', 'r', 'color', 'slant', 'cut'];
const SLIDERS = [ // [field, label, min, max]
  ['w', 'Width', 4, 60],
  ['h', 'Height', 2, 80],
  ['r', 'Roundness', 0, 40],
  ['slant', 'Slant (− worried, + angry)', -30, 30],
  ['cut', 'Smile (cut from below)', 0, 40],
];
const NAME = /^[a-z0-9_-]{1,40}$/;

export class FacesEditor {
  constructor(root, ctx) {
    this.ctx = ctx;
    this.faces = null;   // working copy, sent with Save
    this.mood = null;    // the mood being edited
    this.side = 'both';  // which eye the controls change: both, left, right
    this.dirty = false;
    this.resets = {};    // field -> its ↺ button
    this.list = root.querySelector('#face-list');
    this.controls = root.querySelector('#face-controls');
    this.preview = new CanvasRenderer(root.querySelector('#face-preview'));
    this.box = root.querySelector('#face-message');
    this.newName = root.querySelector('#face-new-name');
    this.deleteButton = root.querySelector('#face-delete');
    root.querySelector('#face-add').addEventListener('click', () => this.#add());
    root.querySelector('#face-save').addEventListener('click', () => this.#save());
    root.querySelector('#face-revert').addEventListener('click', () => this.load());
    this.deleteButton.addEventListener('click', () => this.#delete());
    for (const radio of root.querySelectorAll('input[name="face-side"]')) {
      radio.addEventListener('change', () => {
        this.side = radio.value;
        this.#render();
      });
    }
  }

  load() {
    this.faces = structuredClone(this.ctx.app.config.faces);
    if (!(this.mood in this.faces.moods)) this.mood = this.faces.default;
    this.dirty = false;
    showMessage(this.box, '');
    this.#render();
  }

  onConfig(name) {
    if (name === 'faces' && !this.dirty) this.load();
    if (name === 'settings') this.#drawPreview();
  }

  // ---- drawing ----------------------------------------------------------------------

  #render() {
    const isDefault = this.mood === this.faces.default;
    this.list.replaceChildren(...Object.keys(this.faces.moods).map((name) => {
      const b = button(name === this.faces.default ? `${name} (default)` : name, () => {
        this.mood = name;
        this.#render();
      });
      b.classList.toggle('active', name === this.mood);
      return b;
    }));
    this.deleteButton.hidden = isDefault;
    const pair = resolveMood(this.faces, this.mood);
    const eye = this.side === 'right' ? pair.right : pair.left;
    this.resets = {};
    const rows = SLIDERS.map(([key, label, min, max]) => this.#slider(key, label, min, max, eye[key]));
    const color = el('input', { type: 'color', value: eye.color.toLowerCase() });
    color.addEventListener('input', () => this.#set('color', color.value.toUpperCase()));
    rows.push(this.#row('color', 'Colour', color));
    if (this.side === 'both') {
      rows.push(this.#slider('gap', 'Space between the eyes', 0, 60, pair.gap));
      rows.push(this.#blinkRow(pair.blink_s));
    }
    this.controls.replaceChildren(...rows);
    this.#drawPreview();
  }

  #slider(key, label, min, max, value) {
    const input = el('input', { type: 'range', min, max, step: 1, value });
    const out = el('output', { textContent: value });
    input.addEventListener('input', () => {
      out.textContent = input.value;
      this.#set(key, Number(input.value));
    });
    return this.#row(key, label, input, out);
  }

  #blinkRow(blinkS) {
    const on = el('input', { type: 'checkbox', checked: Boolean(blinkS) });
    const min = el('input', { type: 'number', min: 0.5, max: 60, step: 0.5, value: blinkS?.[0] ?? 3 });
    const max = el('input', { type: 'number', min: 0.5, max: 60, step: 0.5, value: blinkS?.[1] ?? 7 });
    const update = () => {
      min.disabled = max.disabled = !on.checked;
      this.#set('blink_s', on.checked ? [Number(min.value), Math.max(Number(min.value), Number(max.value))] : null);
    };
    for (const input of [on, min, max]) input.addEventListener('change', update);
    min.disabled = max.disabled = !on.checked;
    const label = el('label', { className: 'check' }, on, 'blinks every');
    return this.#row('blink_s', 'Blinking', label, min, 'to', max, 's');
  }

  #row(key, label, ...controls) {
    const reset = button('↺', () => {
      this.#reset(key);
      this.#render();
    }, 'reset');
    reset.title = 'Use the value of the default mood';
    reset.hidden = !this.#overrides(key);
    this.resets[key] = reset;
    return el('div', { className: 'face-row' }, el('span', { textContent: label }), el('div', {}, ...controls), reset);
  }

  #drawPreview() {
    if (this.faces) this.preview.draw(eyesScene(resolveMood(this.faces, this.mood), this.ctx.app.config.settings));
  }

  // ---- editing ----------------------------------------------------------------------

  #set(key, value) {
    const mood = this.faces.moods[this.mood];
    if (this.side === 'both' || !EYE_KEYS.includes(key)) {
      mood[key] = value;
      for (const side of ['left', 'right']) this.#dropSide(mood, side, key); // both eyes alike again
    } else {
      mood[this.side] ??= {};
      mood[this.side][key] = value;
    }
    this.dirty = true;
    if (this.resets[key]) this.resets[key].hidden = !this.#overrides(key);
    this.#drawPreview();
  }

  #overrides(key) {
    const mood = this.faces.moods[this.mood];
    if (this.side === 'both' || !EYE_KEYS.includes(key)) return this.mood !== this.faces.default && key in mood;
    return Boolean(mood[this.side] && key in mood[this.side]);
  }

  #reset(key) {
    const mood = this.faces.moods[this.mood];
    if (this.side === 'both' || !EYE_KEYS.includes(key)) delete mood[key];
    else this.#dropSide(mood, this.side, key);
    this.dirty = true;
  }

  #dropSide(mood, side, key) {
    if (!mood[side]) return;
    delete mood[side][key];
    if (!Object.keys(mood[side]).length) delete mood[side];
  }

  #add() {
    const name = this.newName.value.trim().toLowerCase().replace(/\s+/g, '_');
    if (!NAME.test(name)) return showMessage(this.box, 'Use small letters, digits, - and _ for the name.', 'error');
    if (name in this.faces.moods) return showMessage(this.box, `There is a mood called ${name} already.`, 'error');
    const copy = this.mood === this.faces.default ? {} : structuredClone(this.faces.moods[this.mood]);
    this.faces.moods[name] = copy; // starts looking like the mood you had selected
    this.mood = name;
    this.dirty = true;
    this.newName.value = '';
    this.#render();
    showMessage(this.box, `Added ${name}. Change it, then save.`, 'ok');
  }

  #delete() {
    const name = this.mood;
    delete this.faces.moods[name];
    this.mood = this.faces.default;
    this.dirty = true;
    this.#render();
    showMessage(this.box, `Deleted ${name}. Save to apply; Revert brings it back.`, 'warn');
  }

  async #save() {
    if (await saveConfig(this.ctx.request, 'faces', this.faces, this.box)) {
      this.dirty = false;
      this.ctx.app.config.faces = structuredClone(this.faces);
    }
  }
}

// The same as python/companion/faces.py: a mood's eyes, with what it does not
// set taken from the default mood.
export function resolveMood(faces, name) {
  const base = faces.moods[faces.default];
  const mood = faces.moods[name] ?? base;
  const eye = (side) => Object.fromEntries(EYE_KEYS.map((key) =>
    [key, [mood[side], mood, base[side], base].find((layer) => layer && key in layer)[key]]));
  return { left: eye('left'), right: eye('right'), gap: mood.gap ?? base.gap,
    blink_s: 'blink_s' in mood ? mood.blink_s : base.blink_s };
}

// The same as python/companion/layout.py, looking straight ahead with open eyes.
function eyesScene(pair, settings) {
  const shape = (eye, x, y, inner, scale = 1) => {
    const w = Math.round(eye.w * scale);
    const h = Math.max(2, Math.round(eye.h * scale));
    return { x: Math.round(x), y: Math.round(y), w, h, inner, color: eye.color,
      r: Math.min(Math.round(eye.r * scale), Math.floor(w / 2), Math.floor(h / 2)),
      slant: Math.round(eye.slant * scale), cut: Math.round(eye.cut * scale) };
  };
  if (settings.displays === 2) {
    const s = settings.layout.dual_scale;
    return { kind: 'eyes', brightness: 1, displays: [
      { shapes: [shape(pair.left, 64, 64, 'right', s)] }, { shapes: [shape(pair.right, 64, 64, 'left', s)] }] };
  }
  const half = pair.gap / 2;
  return { kind: 'eyes', brightness: 1, displays: [{ shapes: [
    shape(pair.left, 64 - half - pair.left.w / 2, 64, 'right'),
    shape(pair.right, 64 + half + pair.right.w / 2, 64, 'left')] }] };
}
