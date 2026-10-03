"""Simulated car: stands in for the OBD-II dongle until it arrives.

A real source (obd_source.py, later) only needs the same interface: a `state`
dict with the fields below, and tick(now). The simulator panel sets values
with set() and plays scripted drives with start().

Signs: g_long > 0 speeds up, < 0 brakes; g_lat < 0 is a left turn."""

FIELDS = {"ignition": True, "speed_kmh": 0.0, "rpm": 800.0, "oil_c": 20.0,
          "coolant_c": 20.0, "g_long": 0.0, "g_lat": 0.0}
LIMITS = {"speed_kmh": (0, 260), "rpm": (0, 8000), "oil_c": (-30, 160),
          "coolant_c": (-30, 140), "g_long": (-1.5, 1.5), "g_lat": (-1.5, 1.5)}

# Scripted drives: (seconds from the start, values). Values ramp in a straight
# line from one point to the next; {} at 0 means "from the current values".
# To add a scenario, add an entry here; the simulator shows a button for it.
SCENARIOS = {
    "cold_start": [(0, {"ignition": True, "speed_kmh": 0, "rpm": 1500, "oil_c": 5,
                        "coolant_c": 5, "g_long": 0, "g_lat": 0}),
                   (5, {"rpm": 1100})],
    "warm_up": [(0, {}), (40, {"oil_c": 90, "coolant_c": 88, "rpm": 800})],
    "launch": [(0, {"ignition": True, "speed_kmh": 0, "rpm": 4500, "g_long": 0}),
               (0.4, {"rpm": 6800, "g_long": 0.7}),
               (6, {"speed_kmh": 125, "rpm": 7400, "g_long": 0.4}),
               (7, {"rpm": 3800, "g_long": 0})],
    "hard_brake": [(0, {}), (0.3, {"g_long": -0.95}),
                   (3, {"speed_kmh": 0, "rpm": 900, "g_long": -0.95}), (3.4, {"g_long": 0})],
    "corner_left": [(0, {}), (1, {"g_lat": -0.8}), (3.5, {"g_lat": -0.8}), (4.5, {"g_lat": 0})],
    "corner_right": [(0, {}), (1, {"g_lat": 0.8}), (3.5, {"g_lat": 0.8}), (4.5, {"g_lat": 0})],
    "park": [(0, {}), (6, {"speed_kmh": 0, "rpm": 800, "g_long": -0.2}), (6.5, {"g_long": 0}),
             (9, {"ignition": False, "rpm": 0})],
}


class CarSim:
    def __init__(self):
        self.state = dict(FIELDS)
        self.scenario = None   # name of the running scenario
        self._script = None    # (start time, keyframes with every field filled in)

    def set(self, values):
        """Set fields by hand (the simulator's sliders). Stops a running scenario."""
        self.scenario = self._script = None
        self._apply(values)

    def start(self, name, now):
        """Start a scripted drive. Returns False for an unknown name."""
        if name not in SCENARIOS:
            return False
        frames, values = [], dict(self.state)
        for t, change in SCENARIOS[name]:
            values = {**values, **change}
            frames.append((t, values))
        self.scenario, self._script = name, (now, frames)
        return True

    def tick(self, now):
        if not self._script:
            return
        start, frames = self._script
        t = now - start
        if t >= frames[-1][0]:
            self._apply(frames[-1][1])
            self.scenario = self._script = None
            return
        for (t0, a), (t1, b) in zip(frames, frames[1:]):
            if t0 <= t < t1:
                k = (t - t0) / (t1 - t0)
                self._apply({key: a[key] if isinstance(a[key], bool) else a[key] + (b[key] - a[key]) * k
                             for key in a})
                return

    def _apply(self, values):
        for key, value in values.items():
            if key not in FIELDS:
                raise ValueError(f"unknown car field {key!r}")
            if key == "ignition":
                self.state[key] = bool(value)
            else:
                lo, hi = LIMITS[key]
                self.state[key] = round(min(hi, max(lo, float(value))), 2)
