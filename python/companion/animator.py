"""Animation player: moves the eyes through animations from animations.json.

Three channels change independently, each smoothly from where it is now:
  shape  the eye parameters of a mood (sizes, colour, slant, cut, visor and its glint)
  look   where the eyes look: x and y from -1 to 1
  blink  0 is open, 1 is closed

One animation plays at a time on the main track. When none plays, the eyes
rest in the base mood (chosen by the rules) and the idle animations start at
random times. Blinks run on a track of their own, as the mood's blink_s says.
After an animation the eyes go back to the middle and to the base mood,
unless the animation says "keep"."""

import math
import random

from . import faces

EASES = {
    "linear": lambda k: k,
    "in": lambda k: k * k,                        # slow start
    "out": lambda k: 1 - (1 - k) * (1 - k),       # fast start, soft stop (eye movements)
    "smooth": lambda k: k * k * (3 - 2 * k),      # soft start and stop
}
DEFAULT_MS = 250       # step transition time when a step does not say
RETURN_MS = 250        # back to the middle after an animation
MAX_NESTING = 4        # "anim" steps inside "anim" steps
SHAPE_STEPS = ("mood", "visor", "glint")  # step fields that change the shape channel


class Tween:
    """A value moving from a to b over `dur` seconds."""

    def __init__(self, value):
        self.a = self.b = value
        self.t0, self.dur, self.ease = 0.0, 0.0, "linear"

    def to(self, target, now, ms, ease="smooth"):
        self.a, self.b = self.value(now), target
        self.t0, self.dur, self.ease = now, ms / 1000, ease

    def value(self, now):
        if self.dur <= 0 or now >= self.t0 + self.dur:
            return self.b
        return mix(self.a, self.b, EASES[self.ease]((now - self.t0) / self.dur))


def mix(a, b, k):
    """Blend two values: numbers, (x, y) pairs, "#RRGGBB" colours, or dicts of these."""
    if isinstance(a, dict):
        return {key: mix(a[key], b[key], k) for key in b}
    if isinstance(a, (list, tuple)):
        return tuple(mix(x, y, k) for x, y in zip(a, b))
    if isinstance(a, str):
        ca, cb = int(a[1:], 16), int(b[1:], 16)
        rgb = 0
        for shift in (16, 8, 0):
            x, y = (ca >> shift) & 255, (cb >> shift) & 255
            rgb |= round(x + (y - x) * k) << shift
        return f"#{rgb:06X}"
    return a + (b - a) * k


class Track:
    """The expanded steps of one animation, and where we are in them."""

    def __init__(self, name, steps, keep=False, idle=False):
        self.name, self.steps, self.keep, self.idle = name, steps, keep, idle
        self.i = -1
        self.step_end = 0.0
        self.shapes = any(k in s for s in steps for k in SHAPE_STEPS)  # touches the shape channel
        self.blinks = any("blink" in s for s in steps)


class Animator:
    def __init__(self, faces_cfg, animations_cfg, now, mood_ms=350, rng=None):
        self.rng = rng or random.Random()
        self.faces = faces_cfg
        self.animations = animations_cfg["animations"]
        self.mood_ms = mood_ms
        self.base_mood = faces_cfg["default"]
        self.idle = {"play": [], "every_s": [5, 12]}
        self.awake = False     # starts asleep; set_awake(True) plays "wake_up"
        self.shape = Tween(self._shape_of(self.base_mood))
        self.look = Tween((0.0, 0.0))
        self.blink = Tween(1.0)
        self.main = None       # Track on the main track, or None
        self.blinker = None    # Track of the current blink, or None
        self.next_idle = self.next_blink = math.inf
        self._last_look = (0.0, 0.0)

    # ---- control --------------------------------------------------------------

    def set_awake(self, awake, now):
        """Wake up (plays "wake_up") or fall asleep (plays "sleep"; no blinks or idle while asleep)."""
        if awake == self.awake:
            return
        self.awake = awake
        self.blinker = None
        if awake:
            self.next_idle = now + self._pick(self.idle["every_s"])
            self._schedule_blink(now)
            if not self.play("wake_up", now):
                self.blink.to(0.0, now, RETURN_MS)
        else:
            self.next_idle = self.next_blink = math.inf
            if not self.play("sleep", now):
                self.blink.to(1.0, now, RETURN_MS)

    def set_config(self, faces_cfg, animations_cfg, mood_ms, now):
        """New faces.json / animations.json: the eyes take on the edited mood at once."""
        self.faces, self.animations, self.mood_ms = faces_cfg, animations_cfg["animations"], mood_ms
        if not (self.main and self.main.shapes):
            self.shape.to(self._shape_of(self.base_mood), now, mood_ms)

    def set_base(self, mood, idle, now):
        """The mood and idle behaviour to rest in, chosen by the rules."""
        if mood != self.base_mood:
            self.base_mood = mood
            if not (self.main and self.main.shapes):  # else it applies when the animation ends
                self.shape.to(self._shape_of(mood), now, self.mood_ms)
            if self.awake and self.blinker is None:
                self._schedule_blink(now)
        if idle != self.idle:
            self.idle = idle
            if self.main and self.main.idle:  # the old idle animation stops
                self.main = None
                self.look.to((0.0, 0.0), now, RETURN_MS)
            if self.awake:
                self.next_idle = now + self._pick(idle["every_s"])

    def play(self, what, now, idle=False):
        """Play an animation by name, or a list of steps. Returns False if there is nothing to play."""
        if not isinstance(what, (str, list)):
            return False
        anim = self.animations.get(what) if isinstance(what, str) else {"steps": what}
        steps = self._expand(anim, 0) if anim else []
        if not steps:
            return False
        self.main = Track(what if isinstance(what, str) else "preview", steps,
                          anim.get("keep", False), idle)
        self.main.step_end = now
        return True

    def update(self, now):
        """Move on to `now`. Returns (shape, look, blink) for layout.eyes_scene()."""
        self._advance(self.main, now)
        if self.main is None and now >= self.next_idle:
            names = [n for n in self.idle["play"] if n in self.animations]
            if not (names and self.play(self.rng.choice(names), now, idle=True)):
                self.next_idle = now + self._pick(self.idle["every_s"])
        self._advance(self.blinker, now)
        if self.blinker is None and now >= self.next_blink:
            self._start_blink(now)
        return self.shape.value(now), self.look.value(now), self.blink.value(now)

    @property
    def playing(self):
        return self.main.name if self.main else None

    # ---- tracks -----------------------------------------------------------------

    def _advance(self, track, now):
        while track and now >= track.step_end:
            track.i += 1
            if track.i >= len(track.steps):
                self._finish(track, now)
                return
            self._start_step(track, track.steps[track.i], now)

    def _start_step(self, track, step, now):
        ms = self._pick(step.get("ms", DEFAULT_MS))
        ease = step.get("ease", "smooth")
        if track is self.main:  # the blink track only moves the eyelids
            if any(k in step for k in SHAPE_STEPS):
                target = self._shape_of(step["mood"]) if "mood" in step else dict(self.shape.b)
                for key in ("visor", "glint"):  # move the visor or its reflection on their own
                    if key in step:
                        target[key] = float(step[key])
                self.shape.to(target, now, ms, ease)
            if "look" in step:
                self.look.to(self._look_target(step["look"]), now, ms, ease)
        if "blink" in step:
            self.blink.to(float(step["blink"]), now, ms, ease)
        track.step_end = now + (ms + self._pick(step.get("hold_ms", 0))) / 1000

    def _finish(self, track, now):
        if track is self.blinker:
            self.blinker = None
            if self.awake:
                self._schedule_blink(now)
            return
        self.main = None
        if not track.keep:
            if track.shapes:
                self.shape.to(self._shape_of(self.base_mood), now, self.mood_ms)
            if track.blinks:
                self.blink.to(0.0, now, RETURN_MS)
            if self.look.b != (0.0, 0.0):
                self.look.to((0.0, 0.0), now, RETURN_MS)
        if self.awake:
            self.next_idle = now + self._pick(self.idle["every_s"])

    def _start_blink(self, now):
        if self.main and self.main.blinks:  # the animation moves the eyelids itself
            self._schedule_blink(now)
            return
        name = "double_blink" if self.rng.random() < 0.15 else "blink"
        anim = self.animations.get(name) or self.animations.get("blink")
        if not anim:
            self._schedule_blink(now)
            return
        self.blinker = Track(name, self._expand(anim, 0))
        self.blinker.step_end = now

    def _schedule_blink(self, now):
        blink_s = faces.resolve(self.faces, self.base_mood)["blink_s"]
        self.next_blink = now + self._pick(blink_s) if blink_s else math.inf

    # ---- helpers ----------------------------------------------------------------

    def _expand(self, anim, depth):
        """Flatten repeats and nested "anim" steps into one list of steps."""
        steps = []
        for _ in range(self._count(anim.get("repeat", 1))):
            for step in anim["steps"]:
                for _ in range(self._count(step.get("repeat", 1))):
                    if "anim" not in step:
                        steps.append(step)
                    elif step["anim"] in self.animations and depth < MAX_NESTING:
                        steps += self._expand(self.animations[step["anim"]], depth + 1)
        return steps

    def _shape_of(self, mood):
        pair = faces.resolve(self.faces, mood)
        return {"left": pair["left"], "right": pair["right"], "gap": pair["gap"],
                "visor": pair["visor"], "glint": pair["glint"]}

    def _look_target(self, spec):
        if spec == "random":
            target = self._random_look()
        elif spec == "center":
            target = (0.0, 0.0)
        else:
            target = (float(spec[0]), float(spec[1]))
        self._last_look = target
        return target

    def _random_look(self):
        """A corner 40% of the time, else any spot away from the middle;
        never right next to the last spot."""
        for _ in range(12):
            if self.rng.random() < 0.4:
                x = self.rng.choice((-1, 1)) * self.rng.uniform(0.85, 1.0)
                y = self.rng.choice((-1, 1)) * self.rng.uniform(0.85, 1.0)
            else:
                angle, r = self.rng.uniform(0, 2 * math.pi), self.rng.uniform(0.5, 1.0)
                x, y = r * math.cos(angle), r * math.sin(angle)
            target = (round(x, 2), round(y, 2))
            if math.dist(target, self._last_look) >= 0.7:
                break
        return target

    def _pick(self, value):
        """A number, or a random one from [min, max]."""
        return self.rng.uniform(*value) if isinstance(value, list) else float(value)

    def _count(self, value):
        return self.rng.randint(*value) if isinstance(value, list) else int(value)
