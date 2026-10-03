// Configure dialog: the settings screens the Android app will have.
//   Faces     how each mood looks (config_faces.js)
//   Car data  which face goes with which range of a car value (config_ranges.js)
//   Places    places with their pictures (config_places.js)
//   Files     any config file as JSON (below)
// The companion checks everything before it saves (config_set, image_put)
// and answers with the problems it found.

import { FacesEditor } from './config_faces.js';
import { RangesEditor } from './config_ranges.js';
import { PlacesEditor } from './config_places.js';
import { compactJson, saveConfig, showMessage } from './config_common.js';

const FILES = ['faces', 'animations', 'rules', 'places', 'settings'];
const REPLY_TIMEOUT_MS = 10000;

export class ConfigPanel {
  constructor(dialog, send, app) {
    this.dialog = dialog;
    this.send = send;
    this.app = app;           // shared state from app.js: config, status
    this.waiting = new Map(); // "config_result:places" -> resolve, for replies
    this.tab = 'faces';
    const ctx = { app, request: (msg, replyType) => this.#request(msg, replyType) };
    const pane = (name) => dialog.querySelector(`#tab-${name}`);
    this.editors = {
      faces: new FacesEditor(pane('faces'), ctx),
      ranges: new RangesEditor(pane('ranges'), ctx),
      places: new PlacesEditor(pane('places'), ctx),
    };
    dialog.querySelector('#close-config').addEventListener('click', () => dialog.close());
    for (const tab of dialog.querySelectorAll('[data-tab]')) {
      tab.addEventListener('click', () => this.#showTab(tab.dataset.tab));
    }
    // Files
    this.fileSelect = dialog.querySelector('#file-name');
    this.fileSelect.append(...FILES.map((name) => new Option(`${name}.json`, name)));
    this.fileSelect.addEventListener('change', () => this.#showFile());
    this.fileText = dialog.querySelector('#file-text');
    this.fileText.addEventListener('input', () => (this.fileDirty = true));
    this.fileMessage = dialog.querySelector('#file-message');
    dialog.querySelector('#file-revert').addEventListener('click', () => this.#showFile());
    dialog.querySelector('#file-save').addEventListener('click', () => this.#saveFile());
  }

  open(tab = this.tab) {
    for (const editor of Object.values(this.editors)) editor.load();
    this.#showFile();
    this.#showTab(tab);
    this.dialog.showModal();
  }

  // A config file changed (saved here, in another tab, or on disk).
  setConfig(name) {
    if (!this.dialog.open) return;
    for (const editor of Object.values(this.editors)) editor.onConfig(name);
    if (name === this.fileSelect.value && !this.fileDirty) this.#showFile();
  }

  setStatus(status) {
    this.editors.ranges.onStatus(status);
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
    this.tab = name;
    for (const tab of this.dialog.querySelectorAll('[data-tab]')) tab.classList.toggle('active', tab.dataset.tab === name);
    for (const pane of this.dialog.querySelectorAll('.tab-pane')) pane.hidden = pane.id !== `tab-${name}`;
  }

  // ---- Files ------------------------------------------------------------------------

  #showFile() {
    const data = this.app.config[this.fileSelect.value];
    this.fileText.value = data ? compactJson(data) : '';
    this.fileDirty = false;
    showMessage(this.fileMessage, '');
  }

  async #saveFile() {
    let data;
    try {
      data = JSON.parse(this.fileText.value);
    } catch (e) {
      return showMessage(this.fileMessage, `Not valid JSON: ${e.message}`, 'error');
    }
    const result = await saveConfig(this.#request.bind(this), this.fileSelect.value, data, this.fileMessage);
    if (result) this.fileDirty = false;
  }
}
