// Places tab: add, edit and delete places, each with a picture. A photo you
// choose is cropped to its middle square and scaled to 128×128 here in the
// browser, then sent to the companion as a PNG (image_put).

import { SIZE, toPanelImage } from './render_canvas.js';
import { saveConfig, showMessage } from './config_common.js';

const NEW_PLACE = { name: '', lat: 46.6, lon: 11.62, radius_m: 1000, caption: '', say: '', show_s: 8, cooldown_min: 60 };
const NUMBER_FIELDS = ['lat', 'lon', 'radius_m', 'show_s', 'cooldown_min'];
const TEXT_FIELDS = ['name', 'caption', 'say'];
const PLACE_ORDER = ['id', 'name', 'lat', 'lon', 'radius_m', 'image', 'caption', 'say', 'show_s', 'cooldown_min'];

export class PlacesEditor {
  constructor(root, ctx) {
    this.ctx = ctx;
    this.selected = -1; // index of the place being edited; -1 is a new place
    this.photo = null;  // canvas with a newly chosen photo, not saved yet
    this.$ = (sel) => root.querySelector(sel);
    this.form = this.$('#place-form');
    this.form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.#save();
    });
    this.$('#add-place').addEventListener('click', () => this.#edit(-1));
    this.$('#delete-place').addEventListener('click', () => this.#delete());
    this.$('#use-position').addEventListener('click', () => this.#usePosition());
    this.$('#photo').addEventListener('change', (e) => this.#choosePhoto(e.target.files[0]));
    this.preview = this.$('#photo-preview');
    this.preview.width = this.preview.height = SIZE;
    this.box = this.$('#place-message');
  }

  load() {
    this.#edit(this.selected < this.#places().length ? this.selected : -1);
  }

  onConfig(name) {
    if (name === 'places') this.#renderList();
  }

  #places() {
    return this.ctx.app.config.places?.places ?? [];
  }

  #renderList() {
    this.$('#place-list').replaceChildren(...this.#places().map((place, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = place.name;
      b.classList.toggle('active', i === this.selected);
      b.addEventListener('click', () => this.#edit(i));
      return b;
    }));
  }

  #edit(index) {
    this.selected = index;
    this.photo = null;
    this.$('#photo').value = '';
    const place = index >= 0 ? this.#places()[index] : NEW_PLACE;
    for (const field of [...TEXT_FIELDS, ...NUMBER_FIELDS]) this.form.elements[field].value = place[field] ?? '';
    this.$('#place-title').textContent = index >= 0 ? `Edit ${place.name}` : 'New place';
    this.$('#delete-place').hidden = index < 0;
    showMessage(this.box, '');
    this.#renderList();
    this.#showPicture(place.image ? `images/${encodeURIComponent(place.image)}?v=${Date.now()}` : null);
  }

  #usePosition() {
    const pos = this.ctx.app.status?.location;
    if (!pos) return showMessage(this.box, 'No position yet: click the map in the Location panel first.', 'error');
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
      showMessage(this.box, 'That file is not a picture this browser can read.', 'error');
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

  #read() {
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
    const base = name.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 30) || 'place';
    const ids = new Set(this.#places().map((p) => p.id));
    let id = base;
    for (let n = 2; ids.has(id); n++) id = `${base}_${n}`;
    return id;
  }

  async #save() {
    const place = this.#read();
    const places = structuredClone(this.ctx.app.config.places);
    try {
      if (this.photo) {
        const name = `${place.id}.png`;
        const png = this.photo.toDataURL('image/png').split(',')[1];
        const reply = await this.ctx.request({ type: 'image_put', name, png_base64: png }, 'image_result');
        if (!reply.ok) return showMessage(this.box, reply.error, 'error');
        place.image = name;
      }
    } catch (e) {
      return showMessage(this.box, e.message, 'error');
    }
    const tidy = Object.fromEntries(PLACE_ORDER.filter((k) => k in place).map((k) => [k, place[k]]));
    const ordered = { ...tidy, ...place }; // fields in the usual order, unknown ones kept at the end
    if (this.selected >= 0) places.places[this.selected] = ordered;
    else places.places.push(ordered);
    if (await saveConfig(this.ctx.request, 'places', places, this.box)) {
      this.ctx.app.config.places = places; // the companion's "config" message follows anyway
      const text = this.box.textContent;
      const kind = this.box.className.replace('message', '').trim();
      this.#edit(places.places.findIndex((p) => p.id === place.id));
      showMessage(this.box, text, kind);
    }
  }

  async #delete() {
    const place = this.#places()[this.selected];
    if (!place) return;
    const button = this.$('#delete-place');
    if (!this.confirming) { // a second click within 3 s deletes
      this.confirming = setTimeout(() => {
        this.confirming = null;
        button.textContent = 'Delete place';
      }, 3000);
      button.textContent = 'Click again to delete';
      return;
    }
    clearTimeout(this.confirming);
    this.confirming = null;
    button.textContent = 'Delete place';
    const places = structuredClone(this.ctx.app.config.places);
    places.places.splice(this.selected, 1);
    if (await saveConfig(this.ctx.request, 'places', places, this.box)) {
      this.ctx.app.config.places = places;
      this.#edit(-1);
      showMessage(this.box, `Deleted ${place.name}. Its picture file stays.`, 'ok');
    }
  }
}
