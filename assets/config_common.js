// Helpers shared by the tabs of the Configure dialog.

// Send a whole config file; show "Saved", the errors or the warnings in `box`.
// Returns true when it was saved.
export async function saveConfig(request, name, data, box) {
  try {
    const result = await request({ type: 'config_set', name, data }, 'config_result');
    if (!result.ok) {
      showMessage(box, result.errors.join('\n'), 'error');
      return false;
    }
    showMessage(box, ['Saved and applied.', ...result.warnings].join('\n'), result.warnings.length ? 'warn' : 'ok');
    return true;
  } catch (e) {
    showMessage(box, e.message, 'error');
    return false;
  }
}

export function showMessage(box, text, kind = '') {
  box.textContent = text;
  box.className = `message ${kind}`;
}

// JSON laid out like the files in config/: a record such as a place or a mood
// on one line, bigger structures over several lines (as jsonfile.dumps_compact).
export function compactJson(value, indent = 0) {
  const line = oneLine(value);
  if (typeof value !== 'object' || value === null || !Object.keys(value).length
      || isFlat(value) || indent + line.length <= 100) return line;
  const pad = ' '.repeat(indent + 2);
  const items = Array.isArray(value)
    ? value.map((v) => pad + compactJson(v, indent + 2))
    : Object.entries(value).map(([k, v]) => `${pad}${JSON.stringify(k)}: ${compactJson(v, indent + 2)}`);
  const [open, close] = Array.isArray(value) ? ['[', ']'] : ['{', '}'];
  return `${open}\n${items.join(',\n')}\n${' '.repeat(indent)}${close}`;
}

function oneLine(value) {
  if (Array.isArray(value)) return `[${value.map(oneLine).join(', ')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.entries(value).map(([k, v]) => `${JSON.stringify(k)}: ${oneLine(v)}`).join(', ')}}`;
  }
  return JSON.stringify(value);
}

function isFlat(value) {
  const plain = (v) => typeof v !== 'object' || v === null;
  return Object.values(value).every((v) => plain(v) || (Array.isArray(v) && v.every(plain)));
}
