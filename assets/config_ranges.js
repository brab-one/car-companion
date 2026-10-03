// Car data tab: which face goes with which range of a car value, e.g.
// "speed from 90 km/h: racing". Every row is a rule in rules.json, and the
// first matching row decides the face, so the order is the priority.
// "Keep" holds a row a few seconds after the value left its range; "⋯"
// shows the animations played when a row starts and when it ends.
// Rules about several values at once (such as cold_oil_rev) are listed too,
// so their place in the order is kept; edit those under Files.

import { button, el } from './dom.js';
import { saveConfig, showMessage } from './config_common.js';

const SIGNALS = {
  speed_kmh: 'Speed (km/h)',
  rpm: 'RPM',
  oil_c: 'Oil (°C)',
  coolant_c: 'Coolant (°C)',
  g_long: 'Braking − / accelerating + (g)',
  g_lat: 'Cornering left − / right + (g)',
  motion_g: 'Board shaken (g)',
};
const SHORT = { speed_kmh: 'speed', rpm: 'rpm', oil_c: 'oil', coolant_c: 'coolant', g_long: 'braking',
  g_lat: 'cornering', motion_g: 'shaken' }; // for the ids of new rules, e.g. "speed_angry"
const EYES = { // what the eyes do while the row is active -> rule "idle"
  normal: null,
  look_around: { play: ['look_around'], every_s: [0.5, 2] },
  nervous: { play: ['nervous'], every_s: [0.3, 1] },
  focused: { play: [], every_s: [5, 12] },
};
const EYES_TEXT = { normal: 'as usual', look_around: 'look around', nervous: 'nervous', focused: 'focused',
  custom: 'custom (see Files)' };
const RULE_ORDER = ['id', 'note', 'when', 'mood', 'idle', 'play', 'play_end', 'say', 'level', 'cooldown_s', 'hold_s'];
const CONDITION = /^\s*([a-z_]+)\s*(<=|>=|==|!=|<|>)\s*(\S.*?)\s*$/;

export class RangesEditor {
  constructor(root, ctx) {
    this.ctx = ctx;
    this.rows = [];
    this.dirty = false;
    this.table = root.querySelector('#range-rows');
    this.box = root.querySelector('#range-message');
    root.querySelector('#range-add').addEventListener('click', () => this.#add());
    root.querySelector('#range-save').addEventListener('click', () => this.#save());
    root.querySelector('#range-revert').addEventListener('click', () => this.load());
  }

  load() {
    const thresholds = this.ctx.app.config.settings.thresholds;
    this.rows = this.ctx.app.config.rules.rules.map((rule) => toRow(rule, thresholds) ?? { kind: 'other', rule });
    this.dirty = false;
    showMessage(this.box, '');
    this.#render();
  }

  onConfig(name) {
    if (['rules', 'faces', 'animations'].includes(name) && !this.dirty) this.load();
  }

  // Mark the rows that are active right now.
  onStatus(status) {
    for (const tr of this.table.querySelectorAll('tr[data-id]')) {
      tr.classList.toggle('live', status.rules.includes(tr.dataset.id));
    }
  }

  #render() {
    const config = this.ctx.app.config;
    const moods = Object.keys(config.faces.moods);
    const animations = Object.keys(config.animations.animations);
    const lines = [];
    this.rows.forEach((row, i) => {
      const toggle = row.kind === 'range' ? button('⋯', () => {
        row.open = !row.open;
        this.#render();
      }) : el('span');
      toggle.title = 'Animations when it starts and ends';
      const tools = el('td', { className: 'tools' },
        toggle, button('↑', () => this.#move(i, -1)), button('↓', () => this.#move(i, 1)), button('✕', () => this.#remove(i)));
      const cells = row.kind === 'range'
        ? this.#rangeCells(row, moods)
        : [el('td', { colSpan: 7, className: 'other', textContent: describe(row.rule) })];
      const tr = el('tr', { className: row.kind }, ...cells, tools);
      tr.dataset.id = row.rule.id ?? '';
      lines.push(tr);
      if (row.kind === 'range' && row.open) lines.push(this.#detailsLine(row, animations));
    });
    this.table.replaceChildren(...lines);
    if (this.ctx.app.status) this.onStatus(this.ctx.app.status);
  }

  #rangeCells(row, moods) {
    const changed = () => {
      this.dirty = true;
    };
    const signal = select(SIGNALS, row.signal, (v) => {
      row.signal = v;
      row.changedWhen = true;
      changed();
    });
    const number = (key, onChange) => {
      const input = el('input', { type: 'number', step: 'any', value: row[key] ?? '', placeholder: key === 'hold' ? '0' : 'any' });
      input.addEventListener('input', () => {
        row[key] = input.value === '' ? null : Number(input.value);
        onChange?.();
        changed();
      });
      return input;
    };
    const whenChanged = () => {
      row.changedWhen = true;
    };
    const face = select({ '': '(no change)', ...Object.fromEntries(moods.map((m) => [m, m])) }, row.mood, (v) => {
      row.mood = v;
      changed();
    });
    const eyesOptions = Object.fromEntries(Object.keys(EYES).map((k) => [k, EYES_TEXT[k]]));
    if (row.eyes === 'custom') eyesOptions.custom = EYES_TEXT.custom;
    const eyes = select(eyesOptions, row.eyes, (v) => {
      row.eyes = v;
      changed();
    });
    const say = el('input', { value: row.say, placeholder: 'nothing' });
    say.addEventListener('input', () => {
      row.say = say.value;
      changed();
    });
    const hold = number('hold');
    hold.className = 'short';
    return [signal, number('from', whenChanged), number('to', whenChanged), face, eyes, hold, say]
      .map((control) => el('td', {}, control));
  }

  // The second line of a row: animations when it starts and when it ends.
  #detailsLine(row, animations) {
    const options = { '': 'nothing', ...Object.fromEntries(animations.map((a) => [a, a])) };
    const pick = (key) => select(options, row[key], (v) => {
      row[key] = v;
      this.dirty = true;
    });
    return el('tr', { className: 'details' },
      el('td', { colSpan: 8 },
        el('label', {}, 'When it starts, play ', pick('play')),
        el('label', {}, 'When it ends, play ', pick('playEnd'))));
  }

  #add() {
    const mood = this.ctx.app.config.faces.default;
    this.rows.push({ kind: 'range', rule: {}, isNew: true, signal: 'speed_kmh', from: null, to: null, mood,
      eyes: 'normal', hold: null, play: '', playEnd: '', say: '', changedWhen: true });
    this.dirty = true;
    this.#render();
    showMessage(this.box, 'Added a row at the end (lowest priority). Set it up, move it, then save.', 'ok');
  }

  #move(i, step) {
    const j = i + step;
    if (j < 0 || j >= this.rows.length) return;
    [this.rows[i], this.rows[j]] = [this.rows[j], this.rows[i]];
    this.dirty = true;
    this.#render();
  }

  #remove(i) {
    const [row] = this.rows.splice(i, 1);
    this.dirty = true;
    this.#render();
    showMessage(this.box, `Removed ${row.rule.id ?? 'the new row'}. Save to apply; Revert brings it back.`, 'warn');
  }

  async #save() {
    const problems = [];
    this.rows.forEach((row, i) => {
      if (row.kind !== 'range') return;
      const name = `Row ${i + 1} (${SIGNALS[row.signal]})`;
      if (row.from === null && row.to === null) problems.push(`${name}: give a "from" or a "to" value.`);
      else if (row.from !== null && row.to !== null && row.from >= row.to) problems.push(`${name}: "from" must be smaller than "to".`);
      if (!row.mood && !row.play && !row.playEnd && !row.say.trim()) problems.push(`${name}: choose a face, an animation or a line.`);
    });
    if (problems.length) return showMessage(this.box, problems.join('\n'), 'error');
    const ids = new Set(this.rows.filter((r) => !r.isNew).map((r) => r.rule.id));
    for (const row of this.rows.filter((r) => r.isNew)) { // name new rules after what they do
      const base = `${SHORT[row.signal]}_${row.mood || row.play || 'range'}`;
      let id = base;
      for (let n = 2; ids.has(id); n++) id = `${base}_${n}`;
      ids.add(id);
      row.rule = { ...row.rule, id };
    }
    const data = { ...this.ctx.app.config.rules, rules: this.rows.map(toRule) };
    if (await saveConfig(this.ctx.request, 'rules', data, this.box)) {
      this.ctx.app.config.rules = data;
      const [text, kind] = [this.box.textContent, this.box.className.replace('message', '').trim()];
      this.load(); // rows as saved
      showMessage(this.box, text, kind);
    }
  }
}

// A rule about one range of one car value, as a table row; else null.
function toRow(rule, thresholds) {
  let signal = null;
  let from = null;
  let to = null;
  for (const text of rule.when) {
    const m = CONDITION.exec(text);
    if (!m || !(m[1] in SIGNALS) || (signal && m[1] !== signal)) return null;
    signal = m[1];
    const value = m[3].startsWith('$') ? thresholds[m[3].slice(1)] : Number(m[3]);
    if (!Number.isFinite(value)) return null;
    if ((m[2] === '>' || m[2] === '>=') && from === null) from = value;
    else if ((m[2] === '<' || m[2] === '<=') && to === null) to = value;
    else return null;
  }
  const play = JSON.stringify(rule.idle?.play ?? null);
  const eyes = Object.keys(EYES).find((k) => JSON.stringify(EYES[k]?.play ?? null) === play) ?? 'custom';
  return { kind: 'range', rule, signal, from, to, mood: rule.mood ?? '', eyes, hold: rule.hold_s ?? null,
    play: rule.play ?? '', playEnd: rule.play_end ?? '', say: rule.say ?? '', changedWhen: false };
}

function toRule(row) {
  if (row.kind !== 'range') return row.rule;
  const rule = { ...row.rule };
  if (row.changedWhen) {
    rule.when = [];
    if (row.from !== null) rule.when.push(`${row.signal} >= ${row.from}`);
    if (row.to !== null) rule.when.push(`${row.signal} < ${row.to}`);
  }
  const put = (key, value) => {
    if (value === '' || value === null || value === undefined) delete rule[key];
    else rule[key] = value;
  };
  put('mood', row.mood);
  if (row.eyes !== 'custom') put('idle', EYES[row.eyes]);
  put('hold_s', row.hold || null);
  put('play', row.play);
  put('play_end', row.playEnd);
  put('say', row.say.trim());
  const tidy = Object.fromEntries(RULE_ORDER.filter((k) => k in rule).map((k) => [k, rule[k]]));
  return { ...tidy, ...rule };
}

function describe(rule) {
  const action = [rule.mood && `face ${rule.mood}`, rule.play && `plays ${rule.play}`, rule.say && `says “${rule.say}”`]
    .filter(Boolean).join(', ');
  return `${rule.id}: when ${rule.when.join(' and ')} → ${action}  (edit under Files)`;
}

function select(options, value, onChange) {
  const node = el('select');
  node.append(...Object.entries(options).map(([v, text]) => new Option(text, v, false, v === value)));
  node.addEventListener('change', () => onChange(node.value));
  return node;
}
