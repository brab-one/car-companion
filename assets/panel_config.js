// Configure dialog: the settings screens the Android app will have.
//   Places: add, edit and delete places, each with a picture. A photo you
//           choose is cropped to a square and scaled to 128×128 here in the
//           browser, then sent to the companion as a PNG.
//   Files:  edit any config file as JSON.
// The companion checks everything before it saves (config_set, image_put)
// and answers with the problems it found.

import { SIZE, toPanelImage } from './render_canvas.js';

const FILES = ['faces', 'animations', 'rules', 'places', 'settings'];
const REPLY_TIMEOUT_MS = 10000;
const NEW_PLACE = { name: '', lat: 46.6, lon: 11.62, radius_m: 1000, caption: '', say: '', show_s: 8, cooldown_min: 60 };
const NUMBER_FIELDS = ['lat', 'lon', 'radius_m', 'show_s', 'cooldown_min'];
const PLACE_ORDER = ['id', 'name', 'lat', 'lon', 'radius_m', 'image', 'caption', 'say', 'show_s', 'cooldown_min'];
const TEXT_FIELDS = ['name', 'caption', 'say'];

export class ConfigPanel {
  constructor(dialog, send, app) {
    this.dialog = dialog;
    this.send = send;
    this.app = app;           // shared state from app.js: config, status
    this.waiting = new Map(); // "config_result:places" -> resolve, for replies
    this.selected = -1;       // index of the place being edited; -1 is a new place
    this.photo = null;        // canvas with a newly chosen photo, not saved yet
    this.$ = (sel) => dialog.querySelector(sel);

    dialog.querySelector('#close-config').addEventListener('click', () => dialog.close());
    for (const tab of dialog.querySelectorAll('[data-tab]')) {
      tab.addEventListener('click', () => this.#showTab(tab.dataset.tab));
    }
    // Places
    this.form = this.$('#place-form');
    this.form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.#savePlace();
    });
    this.$('#add-place').addEventListener('click', () => this.#editPlace(-1));
    this.$('#delete-place').addEventListener('click', () => this.#deletePlace());
    this.$('#use-position').addEventListener('click', () => this.#usePosition());
    this.$('#photo').addEventListener('change', (e) => this.#choosePhoto(e.target.files[0]));
    this.preview = this.$('#photo-preview');
    this.preview.width = this.preview.height = SIZE;
    // Files
    this.fileSelect = this.$('#file-name');
    this.fileSelect.append(...FILES.map((name) => new Option(`${name}.json`, name)));
    this.fileSelect.addEventListener('change', () => this.#showFile());
    this.fileText = this.$('#file-text');
    this.fileText.addEventListener('input', () => (this.fileDirty = true));
    this.$('#file-revert').addEventListener('click', () => this.#showFile());
    this.$('#file-save').addEventListener('click', () => this.#saveFile());
  }

  open() {
    this.#renderPlaceList();
    this.#editPlace(this.selected < this.#places().length ? this.selected : -1);
    this.#showFile();
    this.dialog.showModal();
  }

  // A config file changed (saved here, in another tab, or on disk).
  setConfig(name) {
    if (!this.dialog.open) return;
    if (name === 'places') this.#renderPlaceList();
    if (name === this.fileSelect.value && !this.fileDirty) this.#showFile();
  }

  // Replies the companion sends to one client: config_result, image_result.
  onReply(msg) {
    const key = `${msg.type}:${msg.name}`;
    this.waiting.get(key)?.(msg);
    this.waiting.delete(key);
  }

  #request(msg, replyType) {
    const key = `${replyType}:${msg.name}`;
    return new Promise((resolve, reject) => {
      this.waiting.set(key, resolve);
      this.send(msg);
      setTimeout(() => this.waiting.delete(key) && reject(new Error('no answer from the companion')), REPLY_TIMEOUT_MS);
    });
  }

  #showTab(name) {
    for (const tab of this.dialog.querySelectorAll('[data-tab]')) tab.classList.toggle('active', tab.dataset.tab === name);
    for (const pane of this.dialog.querySelectorAll('.tab-pane')) pane.hidden = pane.id !== `tab-${name}`;
  }

  // ---- places ---------------------------------------------------------------------

  #places() {
    return this.app.config.places?.places ?? [];
  }

  #renderPlaceList() {
    const list = this.$('#place-list');
    list.replaceChildren(...this.#places().map((place, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = place.name;
      b.classList.toggle('active', i === this.selected);
      b.addEventListener('click', () => this.#editPlace(i));
      return b;
    }));
  }

  #editPlace(index) {
    this.selected = index;
    this.photo = null;
    this.$('#photo').value = '';
    const place = index >= 0 ? this.#places()[index] : NEW_PLACE;
    for (const field of [...TEXT_FIELDS, ...NUMBER_FIELDS]) this.form.elements[field].value = place[field] ?? '';
    this.$('#place-title').textContent = index >= 0 ? `Edit ${place.name}` : 'New place';
    this.$('#delete-place').hidden = index < 0;
    this.#message('');
    this.#renderPlaceList();
    this.#showPicture(place.image ? `images/${encodeURIComponent(place.image)}?v=${Date.now()}` : null);
  }

  #usePosition() {
    const pos = this.app.status?.location;
    if (!pos) return this.#message('No position yet: click the map in the Location panel first.', 'error');
    this.form.elements.lat.value = pos.lat;
    this.form.elements.lon.value = pos.lon;
  }

  async #choosePhoto(file) {
    if (!file) return;
    try {
      const bitmap = await createImageBitmap(file);
      const side = Math.min(bitmap.width, bitmap.height); // crop the middle square
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = SIZE;
      const ctx = canvas.getContext('2d');
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, SIZE, SIZE);
      this.photo = canvas;
      this.preview.getContext('2d').putImageData(toPanelImage(canvas), 0, 0);
      this.$('#photo-note').textContent = 'New picture, saved with the place.';
    } catch {
      this.#message('That file is not a picture this browser can read.', 'error');
    }
  }

  #showPicture(url) {
    const ctx = this.preview.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, SIZE, SIZE);
    this.$('#photo-note').textContent = url ? 'As the display shows it.' : 'No picture yet.';
    if (!url) return;
    const img = new Image();
    img.onload = () => ctx.putImageData(toPanelImage(img), 0, 0);
    img.src = url;
  }

  #readPlace() {
    const old = this.selected >= 0 ? this.#places()[this.selected] : {};
    const place = { ...old };
    for (const field of TEXT_FIELDS) {
      const value = this.form.elements[field].value.trim();
      if (value || field === 'name') place[field] = value;
      else delete place[field];
    }
    for (const field of NUMBER_FIELDS) place[field] = Number(this.form.elements[field].value);
    place.id = old.id ?? this.#newId(place.name);
    return place;
  }

  #newId(name) {
    const base = name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 30) || 'place';
    const ids = new Set(this.#places().map((p) => p.id));
    let id = base;
    for (let n = 2; ids.has(id); n++) id = `${base}_${n}`;
    return id;
  }

  async #savePlace() {
    const place = this.#readPlace();
    const places = structuredClone(this.app.config.places);
    try {
      if (this.photo) {
        const name = `${place.id}.png`;
        const png = this.photo.toDataURL('image/png').split(',')[1];
        const reply = await this.#request({ type: 'image_put', name, png_base64: png }, 'image_result');
        if (!reply.ok) return this.#message(reply.error, 'error');
        place.image = name;
      }
      const tidy = Object.fromEntries(PLACE_ORDER.filter((k) => k in place).map((k) => [k, place[k]]));
      const ordered = { ...tidy, ...place }; // fields in the usual order, unknown ones kept at the end
      if (this.selected >= 0) places.places[this.selected] = ordered;
      else places.places.push(ordered);
      const result = await this.#request({ type: 'config_set', name: 'places', data: places }, 'config_result');
      if (!result.ok) return this.#message(result.errors.join('\n'), 'error');
      this.app.config.places = places; // the companion's "config" message follows anyway
      this.#editPlace(places.places.findIndex((p) => p.id === place.id));
      this.#message(['Saved.', ...result.warnings].join('\n'), result.warnings.length ? 'warn' : 'ok');
    } catch (e) {
      this.#message(e.message, 'error');
    }
  }

  async #deletePlace() {
    const place = this.#places()[this.selected];
    if (!place || !confirm(`Delete ${place.name}? Its picture file stays.`)) return;
    const places = structuredClone(this.app.config.places);
    places.places.splice(this.selected, 1);
    try {
      const result = await this.#request({ type: 'config_set', name: 'places', data: places }, 'config_result');
      if (!result.ok) return this.#message(result.errors.join('\n'), 'error');
      this.app.config.places = places;
      this.#editPlace(-1);
      this.#message(`Deleted ${place.name}.`, 'ok');
    } catch (e) {
      this.#message(e.message, 'error');
    }
  }

  #message(text, kind = '') {
    const box = this.$('#place-message');
    box.textContent = text;
    box.className = `message ${kind}`;
  }

  // ---- files ----------------------------------------------------------------------

  #showFile() {
    const data = this.app.config[this.fileSelect.value];
    this.fileText.value = data ? compactJson(data) : '';
    this.fileDirty = false;
    this.#fileMessage('');
  }

  async #saveFile() {
    let data;
    try {
      data = JSON.parse(this.fileText.value);
    } catch (e) {
      return this.#fileMessage(`Not valid JSON: ${e.message}`, 'error');
    }
    try {
      const name = this.fileSelect.value;
      const result = await this.#request({ type: 'config_set', name, data }, 'config_result');
      if (!result.ok) return this.#fileMessage(result.errors.join('\n'), 'error');
      this.fileDirty = false;
      this.#fileMessage(['Saved and applied.', ...result.warnings].join('\n'), result.warnings.length ? 'warn' : 'ok');
    } catch (e) {
      this.#fileMessage(e.message, 'error');
    }
  }

  #fileMessage(text, kind = '') {
    const box = this.$('#file-message');
    box.textContent = text;
    box.className = `message ${kind}`;
  }
}

// JSON laid out like the files in config/: a record such as a place or a mood
// on one line, bigger structures over several lines (as jsonfile.dumps_compact).
export function compactJson(value, indent = 0) {
  const line = oneLine(value);
  if (typeof value !== 'object' || value === null || !Object.keys(value).length
      || isFlat(value) || indent + line.length <= 100) return line;
  const pad = ' '.repeat(indent + 2);
  const items = Array.isArray(value)
    ? value.map((v) => pad + compactJson(v, indent + 2))
    : Object.entries(value).map(([k, v]) => `${pad}${JSON.stringify(k)}: ${compactJson(v, indent + 2)}`);
  const [open, close] = Array.isArray(value) ? ['[', ']'] : ['{', '}'];
  return `${open}\n${items.join(',\n')}\n${' '.repeat(indent)}${close}`;
}

function oneLine(value) {
  if (Array.isArray(value)) return `[${value.map(oneLine).join(', ')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.entries(value).map(([k, v]) => `${JSON.stringify(k)}: ${oneLine(v)}`).join(', ')}}`;
  }
  return JSON.stringify(value);
}

function isFlat(value) {
  const plain = (v) => typeof v !== 'object' || v === null;
  return Object.values(value).every((v) => plain(v) || (Array.isArray(v) && v.every(plain)));
}
