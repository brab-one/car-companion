// Clips tab: short videos and GIFs shown on the display now and then.
// A video or GIF you choose is turned into frames here in the browser:
// scaled down to fit the display when it is bigger (never up), centred on
// black, at most MAX_S seconds at FPS frames a second, in the display's
// colours. Saving sends the frames as one tall PNG, frame under frame, in
// parts (clip_put), then saves clips.json (config_set).

import { SIZE, toPanelImage } from './render_canvas.js';
import { button } from './dom.js';
import { saveConfig, showMessage } from './config_common.js';

const FPS = 10;
const MAX_S = 10;
const PART_BYTES = 384 * 1024; // every upload message stays well under 1 MB
const NEW_CLIP = { name: '', show_s: 6, every_min: 5, enabled: true };
const CLIP_ORDER = ['id', 'name', 'file', 'frames', 'fps', 'show_s', 'every_min', 'enabled', 'when'];

export class ClipsEditor {
  constructor(root, ctx) {
    this.ctx = ctx;
    this.selected = -1;     // index of the clip being edited; -1 is a new clip
    this.converted = null;  // frames of a newly chosen file, not saved yet
    this.timer = 0;         // preview animation
    this.$ = (sel) => root.querySelector(sel);
    this.canvas = this.$('#clip-preview');
    this.canvas.width = this.canvas.height = SIZE;
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
    this.converted = null;
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
    if (index >= 0) {
      this.#note(`${clip.frames} frames, ${clip.fps} a second, as the display shows them.`);
      this.#previewStored(clip);
    } else {
      this.#note('No video or GIF yet.');
      this.#showFrames([], FPS);
    }
  }

  #note(text) {
    this.$('#clip-note').textContent = text;
  }

  async #choose(file) {
    if (!file) return;
    try {
      this.#note('Reading frames…');
      const clip = await readClip(file, (n) => this.#note(`Reading frames… ${n}`));
      this.converted = clip;
      if (!this.$('#clip-name').value) this.$('#clip-name').value = file.name.replace(/\.[^.]+$/, '');
      this.#showFrames(clip.frames, clip.fps);
      const notes = [`${clip.frames.length} frames`];
      if (clip.width > SIZE || clip.height > SIZE) notes.push(`scaled down from ${clip.width} × ${clip.height}`);
      if (clip.cut) notes.push(`cut to ${MAX_S} s`);
      this.#note(`${notes.join(', ')}. Saved with the clip.`);
    } catch (e) {
      this.converted = null;
      this.#note('');
      showMessage(this.box, e.message, 'error');
    }
  }

  #previewStored(clip) {
    const sheet = new Image();
    sheet.onload = () => {
      if (this.#clips()[this.selected] !== clip) return; // another clip was picked meanwhile
      const frames = [];
      for (let i = 0; i < clip.frames; i++) frames.push(toPanelImage(sheet, 1, i * SIZE));
      this.#showFrames(frames, clip.fps);
    };
    sheet.src = `clips/${encodeURIComponent(clip.file)}?v=${Date.now()}`;
  }

  #showFrames(frames, fps) {
    clearInterval(this.timer);
    const ctx = this.canvas.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, SIZE, SIZE);
    if (!frames.length) return;
    let i = 0;
    const show = () => {
      ctx.putImageData(frames[i], 0, 0);
      i = (i + 1) % frames.length;
    };
    show();
    this.timer = setInterval(show, 1000 / fps);
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
        const png = await sheet(this.converted.frames);
        await upload(this.ctx.request, clip.file, png, (i, n) => showMessage(this.box, `Sending part ${i} of ${n}…`));
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

// ---- reading videos and GIFs ------------------------------------------------------

// Frames of the display's size, in its colours: {frames, fps, width, height, cut}.
async function readClip(file, onProgress) {
  const gif = file.type === 'image/gif' || /\.gif$/i.test(file.name);
  if (!gif && !file.type.startsWith('video/')) throw new Error('Choose a video or a GIF.');
  return gif ? readGif(file, onProgress) : readVideo(file, onProgress);
}

// Scaled down to fit the display when bigger (never up), centred on black.
function fit(source, width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = SIZE;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const k = Math.min(1, SIZE / width, SIZE / height);
  const w = Math.round(width * k);
  const h = Math.round(height * k);
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(source, Math.floor((SIZE - w) / 2), Math.floor((SIZE - h) / 2), w, h);
  return toPanelImage(canvas);
}

async function readVideo(file, onProgress) {
  const video = document.createElement('video');
  video.muted = true;
  video.preload = 'auto';
  const url = URL.createObjectURL(file);
  try {
    await new Promise((resolve, reject) => {
      video.onloadeddata = resolve;
      video.onerror = () => reject(new Error('This browser cannot play that video.'));
      video.src = url;
    });
    const length = Number.isFinite(video.duration) ? video.duration : MAX_S;
    const frames = [];
    for (let t = 0; t < Math.min(length, MAX_S); t += 1 / FPS) {
      await new Promise((resolve) => {
        video.onseeked = resolve;
        video.currentTime = t;
      });
      frames.push(fit(video, video.videoWidth, video.videoHeight));
      onProgress(frames.length);
    }
    return { frames, fps: FPS, width: video.videoWidth, height: video.videoHeight, cut: length > MAX_S };
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function readGif(file, onProgress) {
  if (!('ImageDecoder' in window)) {
    throw new Error('This browser cannot read animated GIFs; try Chrome or Edge, or use a video.');
  }
  const decoder = new ImageDecoder({ data: await file.arrayBuffer(), type: 'image/gif' });
  await decoder.tracks.ready;
  const count = decoder.tracks.selectedTrack.frameCount;
  const decoded = []; // {frame, start in s}
  let time = 0;
  let width = 0;
  let height = 0;
  for (let i = 0; i < count && time < MAX_S; i++) {
    const { image } = await decoder.decode({ frameIndex: i });
    width = image.displayWidth;
    height = image.displayHeight;
    decoded.push({ frame: fit(image, width, height), start: time });
    const ms = (image.duration ?? 0) / 1000; // the duration is in microseconds
    time += (ms >= 20 ? ms : 100) / 1000;    // browsers show too-short GIF frames for 100 ms
    image.close();
    onProgress(decoded.length);
  }
  decoder.close();
  // The same FPS as videos, so every clip plays the same way.
  const frames = [];
  for (let t = 0, j = 0; t < Math.min(time, MAX_S); t += 1 / FPS) {
    while (j + 1 < decoded.length && decoded[j + 1].start <= t) j++;
    frames.push(decoded[j].frame);
  }
  return { frames, fps: FPS, width, height, cut: decoded.length < count };
}

// ---- sending --------------------------------------------------------------------

function sheet(frames) {
  const canvas = document.createElement('canvas');
  canvas.width = SIZE;
  canvas.height = SIZE * frames.length;
  const ctx = canvas.getContext('2d');
  frames.forEach((frame, i) => ctx.putImageData(frame, 0, i * SIZE));
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
}

async function upload(request, name, blob, onProgress) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const parts = Math.max(1, Math.ceil(bytes.length / PART_BYTES));
  for (let part = 0; part < parts; part++) {
    onProgress(part + 1, parts);
    const data = toBase64(bytes.subarray(part * PART_BYTES, (part + 1) * PART_BYTES));
    const reply = await request({ type: 'clip_put', name, part, parts, data }, 'clip_result');
    if (!reply.ok) throw new Error(reply.error);
  }
}

function toBase64(bytes) {
  let text = '';
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}
