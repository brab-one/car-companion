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
  }

  draw(scene) {
    this.#setCount(scene.displays?.length ?? Math.max(1, this.canvases.length));
    const draw = DRAW[scene.kind];
    if (!draw) console.warn('unknown scene kind', scene.kind);
    this.canvases.forEach((canvas, i) => {
      const ctx = canvas.getContext('2d');
      const img = ctx.createImageData(SIZE, SIZE);
      fillBlack(img);
      draw?.(img, scene, i);
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

// One function per scene kind: (image, scene, display index).
const DRAW = {
  off() {}, // everything stays black
  eyes(img, scene, i) {
    for (const eye of scene.displays[i]?.shapes ?? []) fillEye(img, eye, scene.brightness ?? 1);
  },
  // "image" and "value" arrive in later steps.
};

function fillBlack(img) {
  const d = img.data;
  for (let p = 0; p < d.length; p += 4) {
    d[p] = d[p + 1] = d[p + 2] = 0;
    d[p + 3] = 255;
  }
}

function fillEye(img, eye, brightness) {
  const [r, g, b] = panelColor(eye.color, brightness);
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
function panelColor(hex, brightness) {
  const n = parseInt(hex.slice(1), 16);
  const r5 = (n >> 19) & 31;
  const g6 = (n >> 10) & 63;
  const b5 = (n >> 3) & 31;
  return [(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)]
    .map((v) => Math.round(v * brightness));
}
