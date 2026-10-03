// Small helpers for building the panels.

export function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

export function button(label, onClick, className = '') {
  const node = el('button', { type: 'button', textContent: label, className });
  node.addEventListener('click', onClick);
  return node;
}

// "corner_left" -> "corner left"
export function words(name) {
  return name.replaceAll('_', ' ');
}
