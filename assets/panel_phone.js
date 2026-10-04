// Phone app panel: stands in for the Android app's main screen. What the
// companion is doing, buttons to preview moods and animations, and questions
// to him. The settings screens are in the Configure dialog (panel_config.js).

import { button } from './dom.js';

const SOURCE_TEXT = { last_good: 'the last good version', defaults: 'the built-in defaults' };
const PREVIEW_MS = 2500; // how long a mood preview lasts
const VOICES = { en: 'en-GB', de: 'de-DE' };
const SPEAK_KEY = 'car-companion.speak-answers'; // remembered in this browser only

export class PhonePanel {
  constructor(root, send) {
    this.send = send;
    this.moods = root.querySelector('#moods');
    this.animations = root.querySelector('#animations');
    this.errorBox = root.querySelector('#config-errors');
    this.statusLine = root.querySelector('#status-line');
    this.configErrors = {}; // file name -> {errors, source}
    this.mood = null;
    this.answer = root.querySelector('#ask-answer');
    this.speak = root.querySelector('#ask-speak');
    this.speak.checked = remembered() === '1';
    this.speak.addEventListener('change', () => remember(this.speak.checked ? '1' : '0'));
    root.querySelector('#ask-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const input = root.querySelector('#ask-text');
      if (!input.value.trim()) return;
      this.send({ type: 'ask', text: input.value.trim() });
      input.value = '';
    });
  }

  // His answer to a question (from this page or anywhere else).
  setAnswer(m) {
    this.answer.textContent = `“${m.question}” → ${m.text}`;
    if (this.speak.checked && 'speechSynthesis' in window) {
      speechSynthesis.cancel();
      const words = new SpeechSynthesisUtterance(m.text);
      words.lang = VOICES[m.lang] ?? 'en-GB';
      speechSynthesis.speak(words);
    }
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
    if (status.assistant && status.assistant !== 'idle') parts.push(`${status.assistant}…`);
    if (status.animation) parts.push(`playing: ${status.animation}`);
    if (status.clip) parts.push(`showing clip: ${status.clip}`);
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

function remembered() {
  try {
    return localStorage.getItem(SPEAK_KEY);
  } catch {
    return null; // storage blocked: the box just starts unticked
  }
}

function remember(value) {
  try {
    localStorage.setItem(SPEAK_KEY, value);
  } catch {
    // storage blocked: nothing to remember
  }
}
