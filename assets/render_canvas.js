// Draws scenes on 128×128 canvases pixel by pixel, the way the OLED will:
// no anti-aliasing, colours reduced to RGB565, brightness applied.
// Scenes are plain data from the companion (PROTOCOL.md, "Scenes"); the
// sketch will draw the same shapes with the same rules on the real OLED.
// To support a new scene kind, add a function to DRAW.

export const SIZE = 128;

export class CanvasRenderer {
  constructor(container) {
    this.container = container;
    this.canvases = [];
    this.scene = null;
  }

  draw(scene) {
    this.scene = scene;
    this.#setCount(scene.displays?.length ?? Math.max(1, this.canvases.length));
    const draw = DRAW[scene.kind];
    if (!draw) console.warn('unknown scene kind', scene.kind);
    this.canvases.forEach((canvas, i) => {
      const ctx = canvas.getContext('2d');
      const img = ctx.createImageData(SIZE, SIZE);
      fillBlack(img);
      draw?.(img, scene, i, () => this.scene === scene && this.draw(scene));
      if (scene.bubble && i === 0) fillBubble(img, scene.bubble, scene.brightness ?? 1);
      ctx.putImageData(img, 0, 0);
    });
  }

  #setCount(n) {
    while (this.canvases.length < n) {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = SIZE;
      this.container.append(canvas);
      this.canvases.push(canvas);
    }
    while (this.canvases.length > n) this.canvases.pop().remove();
    this.container.dataset.count = n;
  }
}

// One function per scene kind: (image, scene, display index, redraw).
const DRAW = {
  off() {}, // everything stays black
  eyes(img, scene, i) {
    const display = scene.displays[i];
    for (const eye of display?.shapes ?? []) fillEye(img, eye, scene.brightness ?? 1);
    if (display?.visor) fillVisor(img, display.visor, scene.brightness ?? 1);
  },
  image(img, scene, i, redraw) {
    const picture = loadPicture(scene.image, redraw);
    if (picture) img.data.set(toPanelImage(picture, scene.brightness ?? 1).data);
  },
  // "value" (a big number such as the oil temperature) comes later.
};

// ---- pictures ---------------------------------------------------------------

const pictures = new Map(); // file name -> Image

function loadPicture(name, onLoad) {
  let picture = pictures.get(name);
  if (!picture) {
    picture = new Image();
    picture.src = `images/${encodeURIComponent(name)}?v=${Date.now()}`; // pictures can be replaced
    pictures.set(name, picture);
  }
  if (!picture.complete) picture.addEventListener('load', onLoad, { once: true });
  return picture.complete && picture.naturalWidth ? picture : null;
}

// Call when pictures were added or replaced.
export function forgetPictures() {
  pictures.clear();
}

// A picture (Image or canvas) as the OLED shows it: 128×128, RGB565, dimmed.
export function toPanelImage(picture, brightness = 1) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = SIZE;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(picture, 0, 0, SIZE, SIZE);
  const img = ctx.getImageData(0, 0, SIZE, SIZE);
  const d = img.data;
  for (let p = 0; p < d.length; p += 4) {
    [d[p], d[p + 1], d[p + 2]] = panelColor((d[p] << 16) | (d[p + 1] << 8) | d[p + 2], brightness);
    d[p + 3] = 255;
  }
  return img;
}

// ---- eyes -------------------------------------------------------------------

function fillBlack(img) {
  const d = img.data;
  for (let p = 0; p < d.length; p += 4) {
    d[p] = d[p + 1] = d[p + 2] = 0;
    d[p + 3] = 255;
  }
}

function fillEye(img, eye, brightness) {
  const [r, g, b] = panelColor(parseInt(eye.color.slice(1), 16), brightness);
  const x0 = Math.max(0, Math.floor(eye.x - eye.w / 2));
  const x1 = Math.min(SIZE, Math.ceil(eye.x + eye.w / 2));
  const y0 = Math.max(0, Math.floor(eye.y - eye.h / 2));
  const y1 = Math.min(SIZE, Math.ceil(eye.y + eye.h / 2));
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      if (!insideEye(x + 0.5, y + 0.5, eye)) continue; // test the pixel's centre
      const p = (y * SIZE + x) * 4;
      img.data[p] = r;
      img.data[p + 1] = g;
      img.data[p + 2] = b;
    }
  }
}

// The visor: a rounded band laid over the eyes, tinted by `alpha` (0 clear,
// 1 solid), with two "/" reflection stripes at `glint`. The OLED sketch must
// draw it the same way (PROTOCOL.md, "Scenes").
function fillVisor(img, visor, brightness) {
  const tint = panelColor(parseInt(visor.color.slice(1), 16), brightness);
  const shine = panelColor(parseInt(visor.shine.slice(1), 16), brightness);
  const band = { ...visor, slant: 0, cut: 0 };
  const left = visor.x - visor.w / 2;
  const top = visor.y - visor.h / 2;
  const stripe = (visor.glint ?? 0.2) * visor.w; // where the first stripe starts along the diagonal
  for (let y = Math.max(0, Math.floor(top)); y < Math.min(SIZE, Math.ceil(top + visor.h)); y++) {
    for (let x = Math.max(0, Math.floor(left)); x < Math.min(SIZE, Math.ceil(left + visor.w)); x++) {
      if (!insideEye(x + 0.5, y + 0.5, band)) continue;
      const s = x + 0.5 - left + (y + 0.5 - top); // distance along the "/" diagonal
      const shiny = (s >= stripe && s < stripe + 5) || (s >= stripe + 9 && s < stripe + 11);
      const [color, alpha] = shiny ? [shine, 0.9] : [tint, visor.alpha];
      const p = (y * SIZE + x) * 4;
      for (let c = 0; c < 3; c++) img.data[p + c] = Math.round(color[c] * alpha + img.data[p + c] * (1 - alpha));
    }
  }
}

// The speech bubble: a black rounded box with a 1 px outline, a solid tail
// pointing up at the face, and the text as a 1-bit picture made in Python
// (speech.py). Drawn over everything else, on the first display only.
function fillBubble(img, bubble, brightness) {
  const [r, g, b] = panelColor(parseInt(bubble.color.slice(1), 16), brightness);
  const set = (x, y, on) => {
    if (x < 0 || y < 0 || x >= SIZE || y >= SIZE) return;
    const p = (y * SIZE + x) * 4;
    [img.data[p], img.data[p + 1], img.data[p + 2]] = on ? [r, g, b] : [0, 0, 0];
  };
  const outer = { ...bubble, slant: 0, cut: 0 };
  const inner = { ...outer, w: bubble.w - 2, h: bubble.h - 2, r: Math.max(0, bubble.r - 1) };
  const top = bubble.y - bubble.h / 2;
  const [tipX, tipY] = bubble.tail;
  for (let y = Math.floor(tipY); y < Math.ceil(bubble.y + bubble.h / 2); y++) {
    for (let x = Math.floor(bubble.x - bubble.w / 2); x < Math.ceil(bubble.x + bubble.w / 2); x++) {
      const px = x + 0.5;
      const py = y + 0.5;
      if (insideEye(px, py, outer)) set(x, y, !insideEye(px, py, inner)); // outline, black inside
      else if (py < top && Math.abs(px - tipX) <= (4 * (py - tipY)) / (top - tipY)) set(x, y, true); // tail
    }
  }
  const text = bubble.text;
  const bits = Uint8Array.from(atob(text.bits), (c) => c.charCodeAt(0));
  const stride = Math.ceil(text.w / 8);
  for (let y = 0; y < text.h; y++) {
    for (let x = 0; x < text.w; x++) {
      if (bits[y * stride + (x >> 3)] & (0x80 >> (x & 7))) set(text.x + x, text.y + y, true);
    }
  }
}

// The eye shape: a rounded rectangle, its top edge slanted, its bottom bitten
// off by an ellipse for happy eyes. The OLED sketch must use the same rules.
export function insideEye(px, py, eye) {
  const hw = eye.w / 2;
  const hh = eye.h / 2;
  const ax = Math.abs(px - eye.x);
  const ay = Math.abs(py - eye.y);
  if (ax > hw || ay > hh) return false;

  // Rounded corners.
  const dx = ax - (hw - eye.r);
  const dy = ay - (hh - eye.r);
  if (dx > 0 && dy > 0 && dx * dx + dy * dy > eye.r * eye.r) return false;

  // Slant: the top edge drops by `slant` px at the inner side (towards the
  // other eye); a negative slant drops the outer side instead.
  const fromLeft = (px - (eye.x - hw)) / eye.w;
  const t = eye.inner === 'right' ? fromLeft : 1 - fromLeft; // 0 outer edge, 1 inner edge
  const drop = eye.slant >= 0 ? eye.slant * t : -eye.slant * (1 - t);
  if (py < eye.y - hh + drop) return false;

  // Cut: an ellipse covers the bottom `cut` px (happy eyes).
  if (eye.cut > 0) {
    const rx = eye.w * 0.75;
    const ry = eye.h * 0.5;
    const cy = eye.y + hh - eye.cut + ry;
    const u = (px - eye.x) / rx;
    const v = (py - cy) / ry;
    if (u * u + v * v < 1) return false;
  }
  return true;
}

// The panel stores RGB565 (5 bits red, 6 green, 5 blue). Dimming is assumed
// to happen in the panel (its master current), so it is applied afterwards.
function panelColor(rgb, brightness) {
  const r5 = (rgb >> 19) & 31;
  const g6 = (rgb >> 10) & 63;
  const b5 = (rgb >> 3) & 31;
  return [(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)]
    .map((v) => Math.round(v * brightness));
}
