// PC stand-in for the board's libs/arduino.js, served by tools/run_pc.py.
// Same API as Arduino's WebUI class, but it talks plain HTTP (Server-Sent
// Events in, POST out) instead of socket.io, so the PC side needs only
// Python's standard library. The simulator code is the same in both places.

class WebUI {
  #id = Math.random().toString(36).slice(2);
  #events = new EventSource(`/events?id=${this.#id}`);
  #queue = Promise.resolve(); // keeps outgoing messages in order

  on_connect(callback) {
    this.#events.addEventListener('open', () => callback());
  }

  on_disconnect(callback) {
    this.#events.addEventListener('error', () => callback());
  }

  on_message(eventName, callback) {
    this.#events.addEventListener(eventName, (e) => callback(JSON.parse(e.data)));
  }

  send_message(eventName, data) {
    const body = JSON.stringify({ name: eventName, data: data ?? {} });
    this.#queue = this.#queue
      .then(() => fetch(`/send?id=${this.#id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }))
      .catch((err) => console.error('send failed:', err));
  }
}
