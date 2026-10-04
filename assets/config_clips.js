// Clips tab: short videos and GIFs shown on the display now and then.
// A video or GIF you choose is turned into frames here in the browser
// (clip_media.js). Saving sends them to the companion (clip_put), then saves
// clips.json (config_set).

import { button } from './dom.js';
import { saveConfig, showMessage } from './config_common.js';
import { FramePlayer, describe, loadFrames, readClip, saveClip } from './clip_media.js';

const NEW_CLIP = { name: '', show_s: 6, every_min: 5, enabled: true };
const CLIP_ORDER = ['id', 'name', 'file', 'frames', 'fps', 'show_s', 'every_min', 'enabled', 'when'];

export class ClipsEditor {
  constructor(root, ctx) {
    this.ctx = ctx;
    this.selected = -1;     // index of the clip being edited; -1 is a new clip
    this.converted = null;  // frames of a newly chosen file, not saved yet
    this.reading = null;    // the file being read; picking another clip drops it
    this.$ = (sel) => root.querySelector(sel);
    this.player = new FramePlayer(this.$('#clip-preview'));
    this.box = this.$('#clip-message');
    this.$('#add-clip').addEventListener('click', () => this.#edit(-1));
    this.$('#clip-file').addEventListener('change', (e) => this.#choose(e.target.files[0]));
    this.$('#clip-save').addEventListener('click', () => this.#save());
    this.$('#clip-play').addEventListener('click', () => this.#playNow());
    this.$('#clip-delete').addEventListener('click', () => this.#delete());
  }

  load() {
    this.#edit(this.selected < this.#clips().length ? this.selected : -1);
  }

  onConfig(name) {
    if (name === 'clips') this.#renderList();
  }

  #clips() {
    return this.ctx.app.config.clips?.clips ?? [];
  }

  #renderList() {
    this.$('#clip-list').replaceChildren(...this.#clips().map((clip, i) => {
      const b = button(clip.enabled === false ? `${clip.name} (off)` : clip.name, () => this.#edit(i));
      b.classList.toggle('active', i === this.selected);
      return b;
    }));
  }

  #edit(index) {
    this.selected = index;
    this.converted = this.reading = null;
    this.$('#clip-file').value = '';
    const clip = index >= 0 ? this.#clips()[index] : NEW_CLIP;
    this.$('#clip-name').value = clip.name;
    this.$('#clip-show').value = clip.show_s;
    this.$('#clip-every').value = clip.every_min;
    this.$('#clip-enabled').checked = clip.enabled !== false;
    this.$('#clip-when').value = (clip.when ?? []).join(', ');
    this.$('#clip-title').textContent = index >= 0 ? `Edit ${clip.name}` : 'New clip';
    this.$('#clip-delete').hidden = this.$('#clip-play').hidden = index < 0;
    showMessage(this.box, '');
    this.#renderList();
    this.player.show([]);
    if (index >= 0) {
      this.#note(`${clip.frames} frames, ${clip.fps} a second, as the display shows them.`);
      this.#previewStored(clip);
    } else {
      this.#note('No video or GIF yet.');
    }
  }

  #note(text) {
    this.$('#clip-note').textContent = text;
  }

  async #choose(file) {
    if (!file) return;
    const reading = (this.reading = file);
    try {
      this.#note('Reading frames…');
      const clip = await readClip(file, (n) => this.reading === reading && this.#note(`Reading frames… ${n}`));
      if (this.reading !== reading) return; // another clip was picked meanwhile
      this.converted = clip;
      if (!this.$('#clip-name').value) this.$('#clip-name').value = file.name.replace(/\.[^.]+$/, '');
      this.player.show(clip.frames, clip.fps);
      this.#note(`${describe(clip)}. Saved with the clip.`);
    } catch (e) {
      if (this.reading !== reading) return;
      this.converted = null;
      this.#note('');
      showMessage(this.box, e.message, 'error');
    }
  }

  async #previewStored(clip) {
    try {
      const frames = await loadFrames(clip.file, clip.frames);
      if (this.#clips()[this.selected] === clip) this.player.show(frames, clip.fps); // still the one picked
    } catch (e) {
      if (this.#clips()[this.selected] === clip) this.#note(e.message);
    }
  }

  #read() {
    const old = this.selected >= 0 ? this.#clips()[this.selected] : {};
    const clip = { ...old, name: this.$('#clip-name').value.trim() };
    clip.id = old.id ?? this.#newId(clip.name);
    clip.show_s = Number(this.$('#clip-show').value);
    clip.every_min = Number(this.$('#clip-every').value);
    clip.enabled = this.$('#clip-enabled').checked;
    const when = this.$('#clip-when').value.split(',').map((c) => c.trim()).filter(Boolean);
    if (when.length) clip.when = when;
    else delete clip.when;
    return clip;
  }

  #newId(name) {
    const base = name.toLowerCase().normalize('NFD').replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '').slice(0, 30) || 'clip';
    const ids = new Set(this.#clips().map((c) => c.id));
    let id = base;
    for (let n = 2; ids.has(id); n++) id = `${base}_${n}`;
    return id;
  }

  async #save() {
    const clip = this.#read();
    if (!clip.name) return showMessage(this.box, 'Give the clip a name.', 'error');
    if (!this.converted && !clip.file) return showMessage(this.box, 'Choose a video or a GIF first.', 'error');
    try {
      if (this.converted) {
        clip.file = `${clip.id}.png`;
        clip.frames = this.converted.frames.length;
        clip.fps = this.converted.fps;
        await saveClip(this.ctx.request, clip.file, this.converted.frames,
          (i, n) => showMessage(this.box, `Sending part ${i} of ${n}…`));
      }
    } catch (e) {
      return showMessage(this.box, e.message, 'error');
    }
    const data = structuredClone(this.ctx.app.config.clips);
    const tidy = Object.fromEntries(CLIP_ORDER.filter((k) => k in clip).map((k) => [k, clip[k]]));
    if (this.selected >= 0) data.clips[this.selected] = tidy;
    else data.clips.push(tidy);
    if (await saveConfig(this.ctx.request, 'clips', data, this.box)) {
      this.ctx.app.config.clips = data;
      const [text, kind] = [this.box.textContent, this.box.className.replace('message', '').trim()];
      this.#edit(data.clips.findIndex((c) => c.id === clip.id));
      showMessage(this.box, text, kind);
    }
  }

  #playNow() {
    const clip = this.#clips()[this.selected];
    if (!clip) return;
    this.ctx.send({ type: 'clip_play', id: clip.id });
    showMessage(this.box, 'Playing on the display now (close this window to watch).', 'ok');
  }

  async #delete() {
    const clip = this.#clips()[this.selected];
    if (!clip) return;
    const button = this.$('#clip-delete');
    if (!this.confirming) { // a second click within 3 s deletes
      this.confirming = setTimeout(() => {
        this.confirming = null;
        button.textContent = 'Delete clip';
      }, 3000);
      button.textContent = 'Click again to delete';
      return;
    }
    clearTimeout(this.confirming);
    this.confirming = null;
    button.textContent = 'Delete clip';
    const data = structuredClone(this.ctx.app.config.clips);
    data.clips.splice(this.selected, 1);
    if (await saveConfig(this.ctx.request, 'clips', data, this.box)) {
      this.ctx.app.config.clips = data;
      this.#edit(-1);
      showMessage(this.box, `Deleted ${clip.name}. Its file stays in assets/clips.`, 'ok');
    }
  }
}
