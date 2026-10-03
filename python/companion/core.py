"""The companion's brain.

Hosts (python/main.py on the board, tools/run_pc.py on a PC) do three things:
  - pass incoming messages to receive(); any thread may call it,
  - call tick() about `fps` times per second; all the work happens there,
  - deliver what the companion sends, through the send(msg, to) callback.

Messages are small dicts with a "type" field, documented in PROTOCOL.md.
To handle a new message type, add an on_<type> method and list it in HANDLERS."""

import collections
import queue
import time

from . import faces, layout
from .config_store import ConfigStore

PROTOCOL_VERSION = 1
CONFIG_POLL_S = 1.0  # how often to look for config files changed on disk
LOG_KEEP = 50        # log lines kept for clients that connect later
SOURCE_TEXT = {"file": "file", "last_good": "last good version", "defaults": "built-in defaults"}


class Companion:
    def __init__(self, config_dir, send, clock=time.monotonic):
        """send(msg, to): deliver msg to client `to`, or to every client when to is None."""
        self._send = send
        self._clock = clock
        self._inbox = queue.Queue()
        self._next_poll = 0.0
        self.recent_log = collections.deque(maxlen=LOG_KEEP)
        self.store = ConfigStore(config_dir, log=self.log)
        self.store.load_all()
        for name in self.store.names:
            self._report_config_errors(name)
        self.mood = self.store.data["faces"]["default"]
        self.scene = None
        self.status = None

    @property
    def fps(self):
        return self.store.data["settings"]["fps"]

    # ---- called by the host ---------------------------------------------------

    def receive(self, msg, client=None):
        """Queue an incoming message; it is handled in the next tick()."""
        self._inbox.put((msg, client))

    def tick(self):
        while True:
            try:
                msg, client = self._inbox.get_nowait()
            except queue.Empty:
                break
            self._dispatch(msg, client)
        now = self._clock()
        if now >= self._next_poll:
            self._next_poll = now + CONFIG_POLL_S
            for name in self.store.poll():
                self._config_reloaded(name)
        self._update_outputs()

    # ---- incoming messages ----------------------------------------------------

    def _dispatch(self, msg, client):
        kind = msg.get("type") if isinstance(msg, dict) else None
        handler = self.HANDLERS.get(kind)
        if handler is None:
            self.log("warn", f"ignored a message with unknown type {kind!r}", "protocol")
            return
        try:
            handler(self, msg, client)
        except Exception as e:  # a bad message must never stop the companion
            self.log("error", f"{kind}: {e!r}", "protocol")

    def on_hello(self, msg, client):
        self.send({
            "type": "state",
            "version": PROTOCOL_VERSION,
            "config": dict(self.store.data),
            "config_errors": {n: e for n, e in self.store.errors.items() if e},
            "config_source": dict(self.store.source),
            "scene": self.scene,
            "status": self.status,
            "log": list(self.recent_log),
        }, to=client)

    def on_config_get(self, msg, client):
        name = msg.get("name")
        if name not in self.store.data:
            self.log("warn", f"config_get: unknown config {name!r}", "protocol")
            return
        self.send(self._config_msg(name), to=client)

    def on_play(self, msg, client):
        # Step 1 stand-in: applies the mood of the last step at once.
        # The animation player (step 2) replaces this.
        moods = [s["mood"] for s in msg.get("steps", []) if isinstance(s, dict) and "mood" in s]
        if moods:
            self.set_mood(moods[-1])

    HANDLERS = {
        "hello": on_hello,
        "config_get": on_config_get,
        "play": on_play,
    }

    # ---- state ----------------------------------------------------------------

    def set_mood(self, name):
        if name not in self.store.data["faces"]["moods"]:
            self.log("warn", f"unknown mood {name!r}", "face")
        elif name != self.mood:
            self.mood = name
            self.log("info", f"mood: {name}", "face")

    def _update_outputs(self):
        """Work out what the display shows now; send scene and status when they change."""
        cfg = self.store.data
        if self.mood not in cfg["faces"]["moods"]:  # removed by a config edit
            self.mood = cfg["faces"]["default"]
        brightness = self._brightness()
        pair = faces.resolve(cfg["faces"], self.mood)
        scene = layout.eyes_scene(pair, cfg["settings"], brightness=brightness)
        if scene != self.scene:
            self.scene = scene
            self.send({"type": "scene", "scene": scene})
        status = {"mood": self.mood, "brightness": brightness}
        if status != self.status:
            self.status = status
            self.send({"type": "status", **status})

    def _brightness(self):
        b = self.store.data["settings"]["brightness"]
        # Step 4 adds "auto": dimming from sunrise/sunset at the current location.
        return round(b["manual"] / 100, 2) if b["mode"] == "manual" else 1.0

    # ---- config reporting -----------------------------------------------------

    def _config_msg(self, name):
        return {"type": "config", "name": name,
                "data": self.store.data[name], "source": self.store.source[name]}

    def _config_reloaded(self, name):
        if not self._report_config_errors(name):
            self.log("info", f"{name}.json reloaded", "config")
            self.send(self._config_msg(name))

    def _report_config_errors(self, name):
        errors = self.store.errors.get(name)
        if not errors:
            return False
        source = self.store.source[name]
        for e in errors:
            self.log("error", e, "config")
        self.log("warn", f"{name}.json: using the {SOURCE_TEXT[source]} until the file is fixed", "config")
        self.send({"type": "config_error", "name": name, "errors": errors, "source": source})
        return True

    # ---- output ---------------------------------------------------------------

    def log(self, level, text, source="companion"):
        """level: "info", "warn" or "error". Printed (App Lab shows it) and sent to clients."""
        entry = {"type": "log", "level": level, "text": text, "source": source}
        self.recent_log.append(entry)
        print(f"[{level}] {source}: {text}", flush=True)
        self.send(entry)

    def send(self, msg, to=None):
        try:
            self._send(msg, to)
        except Exception as e:  # a failing transport must not stop the companion
            print(f"[error] send failed: {e!r}", flush=True)
