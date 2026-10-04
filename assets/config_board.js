// Board tab: what the board is doing (processor, temperature, memory), and
// its settings. The time zone and the face updates per second are the
// companion's own (settings.json). The processor's limit and power policy and
// Wi-Fi power saving are in board.json, which the board helper applies as
// root (board/board_helper.py, installed once with tools/install_board_helper.sh).

import { patchConfig, saveConfig, showMessage } from './config_common.js';

const REFRESH_MS = 2000;
const OWN = ''; // the select value for "the board's own"
const WIFI = { [OWN]: null, off: false, on: true };

export class BoardEditor {
  constructor(root, ctx) {
    this.ctx = ctx;
    this.$ = (sel) => root.querySelector(sel);
    this.box = this.$('#board-message');
    this.timer = 0;
    this.choices = ''; // the processor's options shown in the selects, to refill only on change
    this.onBoard = false;
    this.helper = null; // what the board helper last did; null: not installed
    this.$('#board-form').addEventListener('submit', (e) => {
      e.preventDefault();
      this.#save();
    });
  }

  load() {
    this.#fill();
  }

  onConfig(name) {
    if (name === 'board' || name === 'settings') this.#fill();
  }

  // While the tab shows, the board says what it is doing every few seconds.
  shown(visible) {
    clearInterval(this.timer);
    if (!visible) return;
    this.#ask();
    this.timer = setInterval(() => this.#ask(), REFRESH_MS);
  }

  async #ask() {
    try {
      this.#show(await this.ctx.request({ type: 'board_info' }, 'board'));
    } catch {
      // no answer this time; the next try comes soon
    }
  }

  #show(info) {
    const cpu = info.cpu;
    this.onBoard = info.on_board;
    this.helper = info.helper;
    const rows = [];
    if (cpu) {
      rows.push(['Processor', `${ghz(cpu.cur_mhz)} now · limit ${ghz(cpu.max_mhz)} · up to ${ghz(cpu.hw_max_mhz)}`
        + ` · ${cpu.cores} cores · ${cpu.governor}`]);
    }
    if (info.temp_c != null) rows.push(['Temperature', `${info.temp_c.toFixed(1)} °C`]);
    if (info.memory_mb) rows.push(['Memory', `${gb(info.memory_mb.used)} of ${gb(info.memory_mb.total)} GB in use`]);
    if (info.load?.length) rows.push(['Load', `${info.load[0].toFixed(2)} (cores busy, last minute)`]);
    if (info.uptime_s != null) rows.push(['Running for', duration(info.uptime_s)]);
    this.$('#board-info').replaceChildren(...rows.flatMap(([name, value]) => [cell('dt', name), cell('dd', value)]));
    this.$('#board-where').textContent = info.on_board ? ''
      : 'This is the PC simulator: these values are this computer\'s. Open this tab on the board\'s page '
        + 'to see the board; the settings below are saved here and apply on the board after a deploy with --config.';
    if (cpu) this.#offer(cpu, info.helper?.board_default?.cpu?.policy0);
    this.$('#board-helper').textContent = helperText(info);
  }

  // The processor's frequencies and power policies, as the board lists them.
  #offer(cpu, own) {
    const key = JSON.stringify([cpu.freqs_mhz, cpu.governors, own]);
    if (key === this.choices) return;
    this.choices = key;
    const ownMax = own ? ` (${ghz(own.max_khz / 1000)})` : '';
    const ownGov = own ? ` (${own.governor})` : '';
    this.$('#board-cpu-max').replaceChildren(new Option(`the board's own${ownMax}`, OWN),
      ...[...cpu.freqs_mhz].reverse().map((mhz) => new Option(ghz(mhz), mhz)));
    this.$('#board-governor').replaceChildren(new Option(`the board's own${ownGov}`, OWN),
      ...cpu.governors.map((g) => new Option(g, g)));
    this.#fill();
  }

  #fill() {
    const settings = this.ctx.app.config.settings ?? {};
    const board = this.ctx.app.config.board ?? {};
    this.$('#board-timezone').value = settings.timezone ?? '';
    this.$('#board-fps').value = settings.fps ?? 30;
    pick(this.$('#board-cpu-max'), board.cpu_max_mhz ?? OWN);
    pick(this.$('#board-governor'), board.cpu_governor ?? OWN);
    this.$('#board-wifi').value = board.wifi_powersave == null ? OWN : board.wifi_powersave ? 'on' : 'off';
  }

  async #save() {
    const settings = { timezone: this.$('#board-timezone').value.trim(), fps: Number(this.$('#board-fps').value) };
    const max = this.$('#board-cpu-max').value;
    const board = {
      version: 1,
      cpu_max_mhz: max === OWN ? null : Number(max),
      cpu_governor: this.$('#board-governor').value || null,
      wifi_powersave: WIFI[this.$('#board-wifi').value],
    };
    if (await patchConfig(this.ctx.request, 'settings', settings, this.box)
        && await saveConfig(this.ctx.request, 'board', board, this.box)) {
      showMessage(this.box, !this.onBoard ? 'Saved here. The board gets it with tools/deploy.sh --config.'
        : this.helper ? 'Saved. The board helper applies the board\'s part within a few seconds.'
          : 'Saved. The board\'s part applies once the board helper is installed.', 'ok');
    }
  }
}

function helperText(info) {
  if (!info.on_board) return '';
  const h = info.helper;
  if (!h) {
    return 'The board helper is not installed yet, so these are only saved. Install it once with '
      + 'tools/install_board_helper.sh (it asks for the board\'s password).';
  }
  const now = h.now ?? {};
  const parts = [now.cpu_max_mhz && `limit ${ghz(now.cpu_max_mhz)}`, now.cpu_governor,
    now.wifi_powersave && `Wi-Fi power saving: ${now.wifi_powersave}`].filter(Boolean);
  const at = h.at ? new Date(h.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '?';
  return `The board helper applied this at ${at}: ${parts.join(', ')}.`
    + (h.problems?.length ? ` Problems: ${h.problems.join('; ')}.` : '');
}

function pick(select, value) {
  select.value = String(value);
  if (select.value !== String(value)) select.value = OWN; // not offered (yet): the board's own
}

function cell(tag, text) {
  const el = document.createElement(tag);
  el.textContent = text;
  return el;
}

const ghz = (mhz) => `${(mhz / 1000).toFixed(2)} GHz`;
const gb = (mb) => (mb / 1024).toFixed(1);

function duration(s) {
  const min = Math.floor(s / 60);
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${min % 60} min`;
}
