"""How strongly the board is being moved, from Modulino Movement samples.

The sensor measures acceleration in g, including gravity. Gravity is tracked
as a slow average, so tilting the board does not count; what is left is the
movement. value() is about 0.01 g lying still, around 0.1 g when carried,
and 0.5 g and more when shaken. It is None while no samples arrive (no
sensor), so rules on motion_g simply stay off."""

import math
from collections import deque

GRAVITY_FOLLOW = 0.05  # how fast the gravity estimate follows slow tilts, per sample
WINDOW = 10            # samples averaged (about half a second at 20 per second)
STALE_S = 2.0          # no samples for this long: no sensor


class Motion:
    def __init__(self):
        self._gravity = None
        self._window = deque(maxlen=WINDOW)
        self._last_sample = -math.inf
        self._sim_g, self._sim_until = None, -math.inf

    def add(self, x, y, z, now):
        """One accelerometer sample, in g."""
        sample = (x, y, z)
        if self._gravity is None:
            self._gravity = list(sample)
        for i, v in enumerate(sample):
            self._gravity[i] += GRAVITY_FOLLOW * (v - self._gravity[i])
        self._window.append(math.dist(sample, self._gravity) ** 2)
        self._last_sample = now

    def simulate(self, g, seconds, now):
        """The simulator's "shake" button: pretend this much motion for a while."""
        self._sim_g, self._sim_until = g, now + seconds

    def has_sensor(self, now):
        return now - self._last_sample <= STALE_S

    def value(self, now):
        """Motion in g, or None when there is neither a sensor nor a simulated shake."""
        if now < self._sim_until:
            return self._sim_g
        if not self.has_sensor(now) or not self._window:
            return None
        return round(math.sqrt(sum(self._window) / len(self._window)), 3)
