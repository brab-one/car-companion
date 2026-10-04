// Videos and GIFs for the display, used by the Clips and Places tabs.
// A file is turned into frames here in the browser: scaled down to fit the
// display when it is bigger (never up), centred on black, at most MAX_S
// seconds at FPS frames a second, in the display's colours. It is stored as
// one tall PNG, frame under frame, sent to the companion in parts (clip_put).

import { SIZE, toPanelImage } from './render_canvas.js';

export const FPS = 10;
export const MAX_S = 10;
const PART_BYTES = 384 * 1024; // every upload message stays well under 1 MB

// Videos and GIFs; other images are still pictures.
export function isClipFile(file) {
  return isGif(file) || file.type.startsWith('video/');
}

function isGif(file) {
  return file.type === 'image/gif' || /\.gif$/i.test(file.name);
}

// Frames of the display's size, in its colours: {frames, fps, width, height, cut}.
export async function readClip(file, onProgress) {
  if (!isClipFile(file)) throw new Error('Choose a video or a GIF.');
  return isGif(file) ? readGif(file, onProgress) : readVideo(file, onProgress);
}

// What readClip() made of a file, e.g. "24 frames, scaled down from 320 × 240".
export function describe(clip) {
  const notes = [`${clip.frames.length} frames`];
  if (clip.width > SIZE || clip.height > SIZE) notes.push(`scaled down from ${clip.width} × ${clip.height}`);
  if (clip.cut) notes.push(`cut to ${MAX_S} s`);
  return notes.join(', ');
}

// Sends the frames as one tall PNG; the companion stores it as assets/clips/<name>.
export async function saveClip(request, name, frames, onProgress) {
  const bytes = new Uint8Array(await (await sheet(frames)).arrayBuffer());
  const parts = Math.max(1, Math.ceil(bytes.length / PART_BYTES));
  for (let part = 0; part < parts; part++) {
    onProgress(part + 1, parts);
    const data = toBase64(bytes.subarray(part * PART_BYTES, (part + 1) * PART_BYTES));
    const reply = await request({ type: 'clip_put', name, part, parts, data }, 'clip_result');
    if (!reply.ok) throw new Error(reply.error);
  }
}

// The frames of a stored clip, for previews.
export function loadFrames(file, count) {
  return new Promise((resolve, reject) => {
    const sheet = new Image();
    sheet.onload = () => {
      const frames = [];
      for (let i = 0; i < count; i++) frames.push(toPanelImage(sheet, 1, i * SIZE));
      resolve(frames);
    };
    sheet.onerror = () => reject(new Error(`${file} is missing in assets/clips.`));
    sheet.src = `clips/${encodeURIComponent(file)}?v=${Date.now()}`;
  });
}

// Plays frames on a preview canvas, in a loop; one frame is a still picture.
export class FramePlayer {
  constructor(canvas) {
    this.canvas = canvas;
    canvas.width = canvas.height = SIZE;
    this.timer = 0;
  }

  show(frames, fps = FPS) {
    clearInterval(this.timer);
    const ctx = this.canvas.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, SIZE, SIZE);
    if (!frames.length) return;
    let i = 0;
    const next = () => {
      ctx.putImageData(frames[i], 0, 0);
      i = (i + 1) % frames.length;
    };
    next();
    if (frames.length > 1) this.timer = setInterval(next, 1000 / fps);
  }
}

// ---- reading videos and GIFs ------------------------------------------------------

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

function toBase64(bytes) {
  let text = '';
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}
