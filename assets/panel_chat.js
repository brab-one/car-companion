// Chat panel: questions to the companion, typed (until the board has a
// microphone), and his answers ("ask" and "answer" in PROTOCOL.md). Answers to
// questions asked on another screen show up too.

const VOICES = { en: 'en-GB', de: 'de-DE' };
const SPEAK_KEY = 'car-companion.speak-answers'; // remembered in this browser only
const SOURCE_TEXT = { data: 'from the data', model: 'AI model', none: "couldn't answer" };
const WAITING_TEXT = { listening: 'listening…', thinking: 'thinking…' };

export class ChatPanel {
  constructor(root, send) {
    this.send = send;
    this.list = root.querySelector('#chat');
    this.input = root.querySelector('#chat-text');
    this.speak = root.querySelector('#chat-speak');
    this.pending = [];   // {text, sent} asked here, waiting for the answer
    this.waiting = null; // the "thinking…" bubble while he listens or thinks
    this.speak.checked = remembered() === '1';
    this.speak.addEventListener('change', () => remember(this.speak.checked ? '1' : '0'));
    root.querySelector('#chat-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const text = this.input.value.split(/\s+/).filter(Boolean).join(' ');
      if (!text) return;
      this.send({ type: 'ask', text });
      this.pending.push({ text, sent: performance.now() });
      this.#add('you', text);
      this.input.value = '';
    });
  }

  // status.assistant: "idle", "listening", "thinking" or "speaking".
  setStatus(status) {
    const text = WAITING_TEXT[status.assistant];
    this.waiting?.remove();
    this.waiting = text ? this.#add('him waiting', text) : null;
  }

  setAnswer(m) {
    this.waiting?.remove();
    this.waiting = null;
    let meta = SOURCE_TEXT[m.source] ?? m.source;
    const i = this.pending.findIndex((p) => p.text === m.question);
    if (i >= 0) {
      const [asked] = this.pending.splice(i, 1);
      meta += ` · ${((performance.now() - asked.sent) / 1000).toFixed(1)} s`;
    } else {
      this.#add('you other', m.question); // asked on another screen
    }
    this.#add('him', m.text, meta);
    if (this.speak.checked && 'speechSynthesis' in window) {
      speechSynthesis.cancel();
      const words = new SpeechSynthesisUtterance(m.text);
      words.lang = VOICES[m.lang] ?? 'en-GB';
      speechSynthesis.speak(words);
    }
  }

  // He started navigation: the phone app will open Google Maps; until it exists, a link does.
  setNavigation(m) {
    const item = this.#add('him', `Route to ${m.name}`);
    const link = document.createElement('a');
    link.href = m.url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Open in Google Maps';
    item.append(link);
  }

  #add(kind, text, meta) {
    this.list.querySelector('.hint')?.remove(); // the examples, until the first message
    const item = document.createElement('div');
    item.className = `msg ${kind}`;
    const body = document.createElement('div');
    body.textContent = text;
    item.append(body);
    if (meta) {
      const small = document.createElement('div');
      small.className = 'meta';
      small.textContent = meta;
      item.append(small);
    }
    this.list.append(item);
    this.list.scrollTop = this.list.scrollHeight;
    return item;
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
