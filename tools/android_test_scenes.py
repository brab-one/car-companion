#!/usr/bin/env python3
"""Make the Android app's renderer test data: real scenes from the companion,
with what the page's renderer (assets/render_canvas.js) draws for each, as the
SHA-256 of its RGBA pixels. The app must draw the same pixels
(android/app/src/test/.../PanelTest.kt).

    python3 tools/android_test_scenes.py     (needs node)

Writes android/app/src/test/resources/scenes.json."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
from companion.core import Companion  # noqa: E402

OUT = ROOT / "android" / "app" / "src" / "test" / "resources" / "scenes.json"

# Draws each scene with the page's renderer and prints the SHA-256 of the pixels.
RENDER_JS = r"""
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
const images = [];
globalThis.document = { createElement: () => ({ getContext: () => ({
  createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
  putImageData: (img) => images.push(img) }) }) };
const { CanvasRenderer } = await import(process.argv[2]);
const scenes = JSON.parse(readFileSync(0, 'utf8'));
const out = scenes.map((scene) => {
  const screen = new CanvasRenderer({ append() {}, dataset: {} });
  images.length = 0;
  screen.draw(scene);
  return images.map((img) => createHash('sha256').update(img.data).digest('hex'));
});
console.log(JSON.stringify(out));
"""


def scenes():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(ROOT / "tests" / "fixtures" / "config", tmp / "config")
        (tmp / "images").mkdir()
        now = [0.0]
        brain = Companion(tmp / "config", lambda msg, to=None: None, images_dir=tmp / "images",
                          clock=lambda: now[0], echo=lambda line: None)

        def run(seconds):
            end = now[0] + seconds
            while now[0] < end:
                now[0] = round(now[0] + 0.05, 3)
                brain.tick()

        found = {}

        def keep(name):
            found[name] = json.loads(json.dumps(brain.scene))

        run(3)
        for mood in ("neutral", "angry", "worried", "surprised", "sleepy", "suspicious", "delighted", "wink"):
            brain.receive({"type": "play", "steps": [{"mood": mood, "ms": 0, "hold_ms": 2000}]})
            run(0.5)
            keep(mood)
        brain.receive({"type": "play", "name": "android_auto"})
        for i in range(6):
            run(0.4)
            keep(f"android_auto_{i}")
        brain.receive({"type": "sim_car", "speed_kmh": 95})
        run(0.3)
        keep("visor_coming")
        run(3)
        keep("visor_down")
        brain.receive({"type": "ask", "text": "How warm is the oil?"})
        run(0.5)
        keep("bubble")
        return found


def main():
    found = scenes()
    with tempfile.TemporaryDirectory() as tmp:
        renderer = Path(tmp) / "render_canvas.mjs"
        shutil.copy(ROOT / "assets" / "render_canvas.js", renderer)
        script = Path(tmp) / "render.mjs"
        script.write_text(RENDER_JS)
        names = list(found)
        out = subprocess.run(["node", script, renderer.as_uri()], input=json.dumps([found[n] for n in names]),
                             capture_output=True, text=True, check=True).stdout
    hashes = json.loads(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps([{"name": n, "scene": found[n], "sha256": h} for n, h in zip(names, hashes)], indent=1))
    print(f"{OUT.relative_to(ROOT)}: {len(names)} scenes")


if __name__ == "__main__":
    main()
