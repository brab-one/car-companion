// Log panel: what the companion says and why, plus warnings and errors.

const MAX_LINES = 300;

export class LogPanel {
  constructor(list) {
    this.list = list;
  }

  clear() {
    this.list.replaceChildren();
  }

  add({ level = 'info', source = '', text = '' }) {
    const li = document.createElement('li');
    li.className = level;
    li.append(span('time', new Date().toLocaleTimeString()), span('source', source), span('text', text));
    this.list.prepend(li); // newest on top
    while (this.list.children.length > MAX_LINES) this.list.lastChild.remove();
  }
}

function span(className, text) {
  const el = document.createElement('span');
  el.className = className;
  el.textContent = text;
  return el;
}
