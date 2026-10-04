// Plays the companion's scenes at the board's own pace. Each scene carries the
// time the board made it (t, in seconds), and the page shows it a fixed moment
// later than that, so scenes that a bumpy Wi-Fi delivers in bunches still show
// evenly. The delay adapts: about 30 ms over USB, a few hundred ms over a busy
// Wi-Fi. The OLED is driven by the board itself and needs none of this.

const MIN_S = 0.03;      // the delay on a smooth connection
const MAX_S = 0.5;       // scenes later than this are shown at once
const DECAY = 0.995;     // per scene: the delay shrinks again after a bumpy moment
const RESYNC_S = 600;    // the two clocks drift apart a little; start over now and then

export class ScenePlayer {
  constructor(draw) {
    this.draw = draw;
    this.reset();
  }

  // After (re)connecting: the board may have restarted, with a new clock.
  reset() {
    this.offset = null;      // page clock minus board clock, at the best moment of the network seen
    this.jitter = 0;         // how much later than that scenes have arrived, lately
    this.shown = -Infinity;  // board time of the scene on the display
    this.since = performance.now() / 1000;
  }

  // A scene the companion sent, made at board time t (without t: shown at once).
  push(scene, t) {
    if (typeof t !== 'number') {
      this.draw(scene);
      return;
    }
    const now = performance.now() / 1000;
    if (now - this.since > RESYNC_S) this.reset();
    const lag = now - t;
    if (this.offset === null || lag < this.offset) this.offset = lag;
    this.jitter = Math.max(lag - this.offset, this.jitter * DECAY);
    const wait = t + this.offset + Math.min(MAX_S, MIN_S + this.jitter) - now;
    const show = () => {
      if (t < this.shown) return; // a newer scene is already on the display
      this.shown = t;
      this.draw(scene);
    };
    if (wait <= 0) show();
    else setTimeout(show, wait * 1000);
  }
}
