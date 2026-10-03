"""The companion's brain.

Hosts (python/main.py on the board, tools/run_pc.py on a PC) do three things:
  - pass incoming messages to receive() and accelerometer samples to
    accel_sample(); any thread may call them,
  - call tick() about `fps` times per second; all the work happens there,
  - deliver what the companion sends, through the send(msg, to) callback.

Each tick reads the car (simulated until the OBD dongle arrives), lets the
rules choose mood and idle behaviour, moves the animations on and sends the
scene. Messages are small dicts with a "type" field, see PROTOCOL.md. To
handle a new message type, add an on_<type> method and list it in HANDLERS."""

import collections
import math
import queue
import time
from pathlib import Path

from . import layout, validate
from .animator import Animator
from .car_sim import SCENARIOS, CarSim
from .config_store import ConfigStore
from .geofence import Geofences
from .images import Images
from .motion import Motion
from .rules import Rules

PROTOCOL_VERSION = 1
CONFIG_POLL_S = 1.0  # how often to look for config files changed on disk
CAR_SEND_S = 0.2     # car data goes to the app at most 5 times a second
LOG_KEEP = 50        # log lines kept for apps that connect later
SOURCE_TEXT = {"file": "file", "last_good": "last good version", "defaults": "built-in defaults"}


class Companion:
    def __init__(self, config_dir, send, images_dir=None, clock=time.monotonic, echo=print):
        """send(msg, to): deliver msg to client `to`, or to every client when to is None.
        images_dir: where place pictures are (default: assets/images next to config/).
        echo(line): prints log lines (App Lab shows them); tests pass a silent one."""
        self._send = send
        self._clock = clock
        self._echo = echo
        self._inbox = queue.Queue()
        self._samples = queue.Queue()
        self.recent_log = collections.deque(maxlen=LOG_KEEP)
        config_dir = Path(config_dir)
        self.images = Images(images_dir or config_dir.parent / "assets" / "images")
        self.store = ConfigStore(config_dir, log=self.log)
        self.store.load_all()
        for name in self.store.names:
            self._report_config_errors(name)
        now = clock()
        self.car = CarSim()      # later: the OBD dongle, with the same `state` and tick()
        self.motion = Motion()   # Modulino Movement on the board, or the simulator's shake
        self.geo = Geofences()
        self.animator = Animator(self.store.data["faces"], self.store.data["animations"], now)
        self.rules = None
        self._apply_config(now)
        self.location = None     # last position from the phone (or the simulator's map)
        self.picture = None      # (place, until) while a place picture is shown
        self.asleep = True       # the first tick wakes him up when the ignition is on
        self.scene = self.status = None
        self._display_off_at = now + self.store.data["settings"]["sleep_after_off_s"]
        self._ignition_on_at = now
        self._active = []        # ids of the active rules
        self._last_say = -math.inf
        self._next_poll = now + CONFIG_POLL_S
        self._next_car = now
        self._car_sent = None
        self._had_sensor = False
        self._sensor_report = None   # what the sketch last said about the Modulino
        self._missing_logged = False

    @property
    def fps(self):
        return self.store.data["settings"]["fps"]

    # ---- called by the host ---------------------------------------------------

    def receive(self, msg, client=None):
        """Queue an incoming message; it is handled in the next tick()."""
        self._inbox.put((msg, client))

    def accel_sample(self, x, y, z):
        """One Modulino Movement sample in g, from the sketch."""
        self._samples.put((x, y, z, self._clock()))

    def motion_sensor(self, found):
        """The sketch says whether it finds a Modulino Movement (reported while it does not)."""
        self._sensor_report = bool(found)

    def tick(self):
        now = self._clock()
        while not self._inbox.empty():
            self._dispatch(*self._inbox.get_nowait())
        while not self._samples.empty():
            self.motion.add(*self._samples.get_nowait())
        if now >= self._next_poll:
            self._next_poll = now + CONFIG_POLL_S
            for name in self.store.poll():
                self._config_reloaded(name, now)
        self.car.tick(now)
        self._behave(now)
        self._update_outputs(now)

    # ---- behaviour --------------------------------------------------------------

    def _behave(self, now):
        """Ignition, sensors and rules decide mood and idle behaviour."""
        ignition = self.car.state["ignition"]
        if ignition and self.asleep:
            self._wake(now)
        elif not ignition and not self.asleep:
            self._sleep(now)
        has_sensor = self.motion.has_sensor(now)
        if has_sensor != self._had_sensor:
            self._had_sensor = has_sensor
            self.log("info", "Modulino Movement: " + ("receiving data" if has_sensor else "no data"), "sensor")
        if self._sensor_report is False and not self._missing_logged:
            self._missing_logged = True
            self.log("warn", "Modulino Movement: not found on the Qwiic connector; the sketch keeps looking", "sensor")
        if self.asleep:
            return
        cfg = self.store.data
        active = self.rules.update(self._signals(now), now)
        self._log_rule_changes([rule.id for rule, _ in active])
        mood = next((r.spec["mood"] for r, _ in active if "mood" in r.spec), cfg["faces"]["default"])
        if mood not in cfg["faces"]["moods"]:
            mood = cfg["faces"]["default"]
        idle = cfg["settings"]["idle"]
        idle = next(({**idle, **r.spec["idle"]} for r, _ in active if "idle" in r.spec), idle)
        self.animator.set_base(mood, idle, now)
        for rule, fired in active:
            if fired and "play" in rule.spec:
                self.animator.play(rule.spec["play"], now)
            if fired and "say" in rule.spec:
                self._say(rule.spec["say"], f"rule {rule.id}", rule.spec.get("level", 2), now)

    def _signals(self, now):
        """Everything rules.json can test. Add new signals here and in rules.SIGNALS."""
        return {
            **self.car.state,
            "motion_g": self.motion.value(now),
            "place": self.geo.current,
            "running_s": now - self._ignition_on_at,
        }

    def _wake(self, now):
        self.asleep = False
        self._display_off_at = math.inf
        self._ignition_on_at = now
        self.animator.set_awake(True, now)
        self.log("info", "ignition on: waking up", "car")

    def _sleep(self, now):
        self.asleep = True
        self._display_off_at = now + self.store.data["settings"]["sleep_after_off_s"]
        self.animator.set_awake(False, now)
        self.log("info", "ignition off: going to sleep", "car")

    def _log_rule_changes(self, ids):
        if ids == self._active:
            return
        for rule_id in ids:
            if rule_id not in self._active:
                self.log("info", f"rule {rule_id}: on", "rules")
        for rule_id in self._active:
            if rule_id not in ids:
                self.log("info", f"rule {rule_id}: off", "rules")
        self._active = ids

    def _enter_place(self, place, now):
        self.log("info", f"entered {place['name']}", f"place {place['id']}")
        if place.get("image") in self.images.names():
            self.picture = (place, now + place.get("show_s", 8))
        elif "image" in place:
            self.log("warn", f"picture {place['image']} not found in assets/images", f"place {place['id']}")
        if place.get("say"):
            self._say(place["say"], f"place {place['id']}", 2, now)

    def _say(self, text, source, level, now):
        """Say a line, if chattiness allows it and the last line was long enough ago."""
        settings = self.store.data["settings"]
        if level > settings["chattiness"] or now - self._last_say < settings["say_gap_s"]:
            return
        self._last_say = now
        self.send({"type": "say", "text": text, "source": source})
        self.log("say", text, source)

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
            "car": self._car_sent,
            "scenarios": list(SCENARIOS),
            "images": self.images.names(),
            "log": list(self.recent_log),
        }, to=client)

    def on_config_get(self, msg, client):
        name = msg.get("name")
        if name not in self.store.data:
            self.log("warn", f"config_get: unknown config {name!r}", "protocol")
            return
        self.send(self._config_msg(name), to=client)

    def on_config_set(self, msg, client):
        name = msg.get("name")
        if name in self.store.names:
            errors = self.store.save(name, msg.get("data"))
        else:
            errors = [f"unknown config {name!r}"]
        warnings = []
        if not errors:
            self.log("info", f"{name}.json saved from the app", "config")
            self._config_changed(name, self._clock())
            warnings = validate.cross_check(self.store.data, self.images.names())
        self.send({"type": "config_result", "name": name, "ok": not errors,
                   "errors": errors, "warnings": warnings}, to=client)

    def on_image_put(self, msg, client):
        name = msg.get("name")
        error = self.images.save(name, msg.get("png_base64"))
        self.send({"type": "image_result", "name": name, "ok": error is None, "error": error}, to=client)
        if error is None:
            self.log("info", f"picture {name} saved", "config")
            self.send({"type": "images", "names": self.images.names()})

    def on_play(self, msg, client):
        what = msg.get("name", msg.get("steps"))
        if isinstance(what, list) and (errors := validate.check_steps(what)):
            self.log("warn", "play: " + "; ".join(errors), "protocol")
        elif self.asleep:
            self.log("info", "he is asleep; turn the ignition on first", "face")
        elif not self.animator.play(what, self._clock()):
            self.log("warn", f"play: unknown animation {what!r}", "protocol")

    def on_location(self, msg, client):
        lat, lon = float(msg["lat"]), float(msg["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"no such place on earth: {lat}, {lon}")
        now = self._clock()
        self.location = {"lat": lat, "lon": lon}
        places = self.store.data["places"]["places"]
        margin = self.store.data["settings"]["place_exit_margin"]
        for place, wait_min in self.geo.update(places, lat, lon, margin, now):
            if wait_min:
                self.log("info", f"entered {place['name']}; quiet for {wait_min} more min"
                         " (cooldown_min in places.json)", f"place {place['id']}")
            else:
                self._enter_place(place, now)

    def on_sim_car(self, msg, client):
        self.car.set({k: v for k, v in msg.items() if k != "type"})

    def on_sim_scenario(self, msg, client):
        if self.car.start(msg.get("name"), self._clock()):
            self.log("info", f"scenario {msg['name']}", "car")
        else:
            self.log("warn", f"unknown scenario {msg.get('name')!r}", "protocol")

    def on_sim_motion(self, msg, client):
        g, seconds = float(msg.get("g", 1.0)), float(msg.get("s", 2.0))
        self.motion.simulate(g, min(seconds, 30.0), self._clock())

    HANDLERS = {
        "hello": on_hello,
        "config_get": on_config_get,
        "config_set": on_config_set,
        "image_put": on_image_put,
        "play": on_play,
        "location": on_location,
        "sim_car": on_sim_car,
        "sim_scenario": on_sim_scenario,
        "sim_motion": on_sim_motion,
    }

    # ---- output -----------------------------------------------------------------

    def _update_outputs(self, now):
        """Send the scene, the status and the car data when they changed."""
        settings = self.store.data["settings"]
        brightness = self._brightness()
        shape, look, blink = self.animator.update(now)
        if self.picture and now >= self.picture[1]:
            self.picture = None
        if now >= self._display_off_at:
            scene = {"kind": "off"}
        elif self.picture:
            place = self.picture[0]
            scene = {"kind": "image", "image": place["image"], "caption": place.get("caption", ""),
                     "brightness": brightness}
        else:
            scene = layout.eyes_scene(shape, settings, look, blink, brightness)
        if scene != self.scene:
            self.scene = scene
            self.send({"type": "scene", "scene": scene})
        status = {"mood": self.animator.base_mood, "animation": self.animator.playing,
                  "rules": self._active, "place": self.geo.current, "location": self.location,
                  "asleep": self.asleep, "brightness": brightness}
        if status != self.status:
            self.status = status
            self.send({"type": "status", **status})
        if now >= self._next_car:
            self._next_car = now + CAR_SEND_S
            car = {**self.car.state, "scenario": self.car.scenario,
                   "motion_g": self.motion.value(now), "sensor": self.motion.has_sensor(now)}
            if car != self._car_sent:
                self._car_sent = car
                self.send({"type": "car", **car})

    def _brightness(self):
        b = self.store.data["settings"]["brightness"]
        # "auto" (dimming from sunrise/sunset at the current location) comes later.
        return round(b["manual"] / 100, 2) if b["mode"] == "manual" else 1.0

    # ---- config -----------------------------------------------------------------

    def _apply_config(self, now):
        cfg = self.store.data
        settings = cfg["settings"]
        self.animator.set_config(cfg["faces"], cfg["animations"], settings["mood_ms"], now)
        self.rules = Rules(cfg["rules"], settings["thresholds"], previous=self.rules)
        for warning in validate.cross_check(cfg, self.images.names()):
            self.log("warn", warning, "config")

    def _config_msg(self, name):
        return {"type": "config", "name": name,
                "data": self.store.data[name], "source": self.store.source[name]}

    def _config_reloaded(self, name, now):
        if not self._report_config_errors(name):
            self.log("info", f"{name}.json reloaded", "config")
            self._config_changed(name, now)

    def _config_changed(self, name, now):
        self._apply_config(now)
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

    def log(self, level, text, source="companion"):
        """level: "info", "warn", "error" or "say". Echoed to the console and sent to clients."""
        entry = {"type": "log", "level": level, "text": text, "source": source}
        self.recent_log.append(entry)
        self._echo(f"[{level}] {source}: {text}")
        self.send(entry)

    def send(self, msg, to=None):
        try:
            self._send(msg, to)
        except Exception as e:  # a failing transport must not stop the companion
            self._echo(f"[error] send failed: {e!r}")
