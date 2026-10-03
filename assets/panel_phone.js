// Phone app panel: stands in for the Android app's main screen. What the
// companion is doing, and buttons to preview moods and animations.
// The settings screens are in the Configure dialog (panel_config.js).

import { button } from './dom.js';

const SOURCE_TEXT = { last_good: 'the last good version', defaults: 'the built-in defaults' };
const PREVIEW_MS = 2500; // how long a mood preview lasts

export class PhonePanel {
  constructor(root, send) {
    this.send = send;
    this.moods = root.querySelector('#moods');
    this.animations = root.querySelector('#animations');
    this.errorBox = root.querySelector('#config-errors');
    this.statusLine = root.querySelector('#status-line');
    this.configErrors = {}; // file name -> {errors, source}
    this.mood = null;
  }

  setConfig(config) {
    this.moods.replaceChildren(...Object.keys(config.faces.moods).map((name) =>
      button(name, () => this.send({ type: 'play', steps: [{ mood: name, ms: 300, hold_ms: PREVIEW_MS }] }))));
    this.animations.replaceChildren(...Object.keys(config.animations.animations).map((name) =>
      button(name, () => this.send({ type: 'play', name }))));
    this.#highlight();
  }

  setStatus(status) {
    this.mood = status.mood;
    this.#highlight();
    const parts = [
      status.asleep ? 'Asleep' : `Mood: ${status.mood}`,
      status.rules.length ? `rules: ${status.rules.join(', ')}` : 'no rule active',
    ];
    if (status.animation) parts.push(`playing: ${status.animation}`);
    if (status.place) parts.push(`in: ${status.place}`);
    parts.push(`brightness ${Math.round(status.brightness * 100)} %`);
    this.statusLine.textContent = parts.join(' · ');
  }

  // errors: list of messages, or empty when the file is fine again.
  setConfigErrors(name, errors, source) {
    if (errors?.length) this.configErrors[name] = { errors, source };
    else delete this.configErrors[name];
    const lines = Object.entries(this.configErrors).map(([file, e]) => {
      const div = document.createElement('div');
      const count = e.errors.length === 1 ? '1 problem' : `${e.errors.length} problems`;
      div.textContent = `${file}.json has ${count}, using ${SOURCE_TEXT[e.source] ?? e.source}. Details in the log.`;
      return div;
    });
    this.errorBox.replaceChildren(...lines);
  }

  #highlight() {
    for (const b of this.moods.children) b.classList.toggle('active', b.textContent === this.mood);
  }
}
