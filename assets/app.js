// Simulator entry point: connects to the companion and routes its messages
// to the panels. Every message is {type, ...} on the "msg" channel (PROTOCOL.md).

import { CanvasRenderer } from './render_canvas.js';
import { PhonePanel } from './panel_phone.js';
import { LogPanel } from './panel_log.js';

const CHANNEL = 'msg';
const ui = new WebUI(); // from libs/arduino.js
const send = (msg) => ui.send_message(CHANNEL, msg);

const screen = new CanvasRenderer(document.querySelector('#displays'));
const phone = new PhonePanel(document.querySelector('#phone'), send);
const log = new LogPanel(document.querySelector('#log'));
const connection = document.querySelector('#connection');

const config = {}; // latest copy of each config file, by name

// One handler per message type. To react to a new type, add it here.
const handlers = {
  state(m) {
    Object.assign(config, m.config);
    phone.setFaces(config.faces);
    phone.setStatus(m.status);
    for (const name of Object.keys(m.config_source)) {
      phone.setConfigErrors(name, m.config_errors[name], m.config_source[name]);
    }
    if (m.scene) screen.draw(m.scene);
    log.clear();
    m.log.forEach((entry) => log.add(entry));
  },
  config(m) {
    config[m.name] = m.data;
    phone.setConfigErrors(m.name, [], m.source);
    if (m.name === 'faces') phone.setFaces(m.data);
  },
  config_error(m) {
    phone.setConfigErrors(m.name, m.errors, m.source);
  },
  scene(m) {
    screen.draw(m.scene);
  },
  status(m) {
    phone.setStatus(m);
  },
  log(m) {
    log.add(m);
  },
};

ui.on_connect(() => {
  connection.textContent = 'connected';
  connection.classList.add('online');
  send({ type: 'hello', client: 'sim', version: 1 });
});

ui.on_disconnect(() => {
  connection.textContent = 'disconnected';
  connection.classList.remove('online');
});

ui.on_message(CHANNEL, (msg) => {
  const handler = handlers[msg?.type];
  if (handler) handler(msg);
  else console.warn('unhandled message', msg);
});
