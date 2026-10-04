// Board tab: what the board is doing (processor, temperature, memory), and
// its settings. The time zone, the face updates per second and wireless
// Android Auto are the companion's own (settings.json; the Android Auto bridge
// follows its android_auto.enabled). The processor's limit and power policy and
// Wi-Fi power saving are in board.json, which the board helper applies as
// root (board/board_helper.py, installed once with tools/install_board_helper.sh).

import { patchConfig, saveConfig, showMessage } from './config_common.js';

const REFRESH_MS = 2000;
const OWN = ''; // the select value for "the board's own"
const WIFI = { [OWN]: null, off: false, on: true };
// Android Auto's access point: the channels per band (5 GHz: the ones without radar checks).
const CHANNELS = { '2.4': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], 5: [36, 40, 44, 48] };
const DEFAULT_CHANNEL = { '2.4': 6, 5: 36 };
const AA_SILENT_S = 10; // longer without a report from the bridge: it does not run

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
    this.$('#board-aa-toggle').addEventListener('click', () => this.#toggleAndroidAuto());
    this.$('#board-aa-pair').addEventListener('click', () => this.#pairPhone());
    this.$('#board-aa-band').addEventListener('change', () => this.#channels(0));
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
    this.$('#board-aa-status').textContent = androidAutoText(info);
    this.$('#board-aa-pair').disabled = info.android_auto?.state !== 'on';
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
    const aa = settings.android_auto ?? {};
    this.$('#board-aa-toggle').textContent = aa.enabled ? 'Disable Android Auto' : 'Enable Android Auto';
    this.$('#board-aa-keep-wifi').checked = aa.keep_wifi ?? true;
    this.$('#board-aa-name').value = aa.wifi_name ?? '';
    this.$('#board-aa-password').value = aa.wifi_password ?? '';
    this.$('#board-aa-band').value = aa.wifi_band ?? '2.4';
    this.#channels(aa.wifi_channel ?? 0);
    this.$('#board-aa-country').value = aa.country ?? '';
    this.$('#board-aa-pairing').value = aa.pairing_min ?? 3;
    pick(this.$('#board-cpu-max'), board.cpu_max_mhz ?? OWN);
    pick(this.$('#board-governor'), board.cpu_governor ?? OWN);
    this.$('#board-wifi').value = board.wifi_powersave == null ? OWN : board.wifi_powersave ? 'on' : 'off';
  }

  async #save() {
    const settings = {
      timezone: this.$('#board-timezone').value.trim(),
      fps: Number(this.$('#board-fps').value),
      // Switched on and off by its own button, at once.
      android_auto: {
        keep_wifi: this.$('#board-aa-keep-wifi').checked,
        wifi_name: this.$('#board-aa-name').value.trim(),
        wifi_password: this.$('#board-aa-password').value,
        wifi_band: this.$('#board-aa-band').value,
        wifi_channel: Number(this.$('#board-aa-channel').value),
        country: this.$('#board-aa-country').value.trim().toUpperCase(),
        pairing_min: Number(this.$('#board-aa-pairing').value),
      },
    };
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

  // Android Auto goes on and off at once; the bridge follows within 2 s.
  async #toggleAndroidAuto() {
    const enabled = !(this.ctx.app.config.settings?.android_auto?.enabled ?? false);
    if (await patchConfig(this.ctx.request, 'settings', { android_auto: { enabled } }, this.box)) {
      showMessage(this.box, enabled
        ? 'Android Auto is enabled: pair your phone with the board over Bluetooth in the next minutes.'
        : 'Android Auto is disabled: the board\'s Wi-Fi and Bluetooth are back to normal.', 'ok');
    }
  }

  #pairPhone() {
    this.ctx.send({ type: 'android_auto_pair' });
    showMessage(this.box, 'Pairing opens within 2 s: pair your phone with the board in its Bluetooth settings.', 'ok');
  }

  // The chosen band's channels; 0 is automatic.
  #channels(value) {
    const band = this.$('#board-aa-band').value;
    const select = this.$('#board-aa-channel');
    select.replaceChildren(new Option(`automatic (${DEFAULT_CHANNEL[band]})`, 0),
      ...CHANNELS[band].map((ch) => new Option(ch, ch)));
    select.value = CHANNELS[band].includes(value) ? value : 0;
  }
}

function androidAutoText(info) {
  if (!info.on_board) {
    return 'Android Auto runs on the board only. Here in the simulator the button only switches the setting, '
      + 'and the Car panel\'s "Android Auto connected" stands in for your phone.';
  }
  const aa = info.android_auto;
  if (!aa || aa.age_s > AA_SILENT_S) {
    return 'The Android Auto bridge is not running on the board. Start it once with tools/android_auto.sh; '
      + 'then it starts with the board.';
  }
  const paired = aa.paired?.length ? `Paired: ${aa.paired.join(', ')}.` : 'No phone paired yet.';
  if (aa.state === 'error') return `Could not start: ${aa.error}. It tries again every minute. ${paired}`;
  if (aa.state !== 'on') return `Disabled: the board's Wi-Fi and Bluetooth are as usual. ${paired}`;
  const pairing = aa.pairing_s > 0
    ? `pairing open for ${Math.floor(aa.pairing_s / 60)}:${String(aa.pairing_s % 60).padStart(2, '0')}`
    : 'pairing closed';
  const own = aa.interface === 'ap0'
    ? (aa.home ? `the board stays on "${aa.home}"` : 'the board\'s own Wi-Fi is free for your network')
    : 'the board left your Wi-Fi meanwhile';
  return `Enabled: Wi-Fi "${aa.wifi_name}" (password ${aa.wifi_password}), ${aa.band} GHz, channel ${aa.channel}`
    + ` · ${own} · ${aa.phone ? 'your phone is connected' : 'waiting for your phone'} · ${pairing}. ${paired}`;
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
