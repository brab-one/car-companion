// Simulator entry point: connects to the companion and routes its messages
// to the panels. Every message is {type, ...} on the "msg" channel (PROTOCOL.md).

import { CanvasRenderer, forgetPictures } from './render_canvas.js';
import { ScenePlayer } from './scene_player.js';
import { PhonePanel } from './panel_phone.js';
import { ChatPanel } from './panel_chat.js';
import { CarPanel } from './panel_car.js';
import { LocationPanel } from './panel_location.js';
import { ConfigPanel } from './panel_config.js';
import { LogPanel } from './panel_log.js';

const CHANNEL = 'msg';
const ui = new WebUI(); // from libs/arduino.js
const send = (msg) => ui.send_message(CHANNEL, msg);

const app = { config: {}, status: null }; // shared with the Configure dialog

const screen = new CanvasRenderer(document.querySelector('#displays'));
const player = new ScenePlayer((scene) => screen.draw(scene)); // evenly, also over a bumpy Wi-Fi
const phone = new PhonePanel(document.querySelector('#phone'), send);
const chat = new ChatPanel(document.querySelector('#chat-card'), send);
const car = new CarPanel(document.querySelector('#car'), send);
const where = new LocationPanel(document.querySelector('#location'), send);
const configure = new ConfigPanel(document.querySelector('#config'), send, app);
const log = new LogPanel(document.querySelector('#log'));
const connection = document.querySelector('#connection');

document.querySelector('#open-config').addEventListener('click', () => configure.open());
document.querySelector('#edit-faces').addEventListener('click', () => configure.open('faces'));

function configChanged(name) {
  phone.setConfig(app.config);
  car.setConfig(app.config);
  where.setConfig(app.config);
  configure.setConfig(name);
}

// One handler per message type. To react to a new type, add it here.
const handlers = {
  state(m) {
    app.config = m.config;
    car.setScenarios(m.scenarios);
    configChanged(null);
    for (const name of Object.keys(m.config_source)) {
      phone.setConfigErrors(name, m.config_errors[name], m.config_source[name]);
    }
    player.reset();
    if (m.scene) screen.draw(m.scene);
    if (m.status) handlers.status(m.status);
    if (m.car) handlers.car(m.car);
    log.clear();
    m.log.forEach((entry) => log.add(entry));
  },
  config(m) {
    app.config[m.name] = m.data;
    phone.setConfigErrors(m.name, [], m.source);
    configChanged(m.name);
  },
  config_error(m) {
    phone.setConfigErrors(m.name, m.errors, m.source);
  },
  config_result(m) {
    configure.onReply(m);
  },
  image_result(m) {
    configure.onReply(m);
  },
  clip_result(m) {
    configure.onReply(m);
  },
  images() {
    forgetPictures();
  },
  clip_files() {
    forgetPictures();
  },
  scene(m) {
    player.push(m.scene, m.t);
  },
  status(m) {
    app.status = m;
    phone.setStatus(m);
    chat.setStatus(m);
    where.setStatus(m);
    configure.setStatus(m);
  },
  car(m) {
    car.setCar(m);
    where.setCar(m);
  },
  say() {
    // Shown on the display as a speech bubble (part of the scene); later also spoken aloud.
  },
  answer(m) {
    chat.setAnswer(m);
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
