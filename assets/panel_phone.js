// Phone app panel: stands in for the Android app's controls.
// Step 1: preview a mood. Editing settings, animations and places comes in step 5.

const SOURCE_TEXT = { last_good: 'the last good version', defaults: 'the built-in defaults' };

export class PhonePanel {
  constructor(root, send) {
    this.send = send;
    this.moods = root.querySelector('#moods');
    this.errorBox = root.querySelector('#config-errors');
    this.statusLine = root.querySelector('#status-line');
    this.configErrors = {}; // file name -> {errors, source}
    this.mood = null;
  }

  setFaces(faces) {
    const buttons = Object.keys(faces.moods).map((name) => {
      const button = document.createElement('button');
      button.textContent = name;
      button.dataset.mood = name;
      button.addEventListener('click', () => this.send({ type: 'play', steps: [{ mood: name }] }));
      return button;
    });
    this.moods.replaceChildren(...buttons);
    this.#highlight();
  }

  setStatus(status) {
    if (!status) return;
    this.mood = status.mood;
    this.#highlight();
    this.statusLine.textContent = `Mood: ${status.mood} · brightness ${Math.round(status.brightness * 100)} %`;
  }

  // errors: list of messages, or empty when the file is fine again.
  setConfigErrors(name, errors, source) {
    if (errors?.length) this.configErrors[name] = { errors, source };
    else delete this.configErrors[name];
    const lines = Object.entries(this.configErrors).map(([file, e]) => {
      const div = document.createElement('div');
      const count = e.errors.length === 1 ? '1 problem' : `${e.errors.length} problems`;
      div.textContent = `${file}.json has ${count}, using ${SOURCE_TEXT[e.source] ?? e.source}. Details in the log.`;
      return div;
    });
    this.errorBox.replaceChildren(...lines);
  }

  #highlight() {
    for (const button of this.moods.children) {
      button.classList.toggle('active', button.dataset.mood === this.mood);
    }
  }
}
