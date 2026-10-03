"""Rules from rules.json: how the companion reacts to the car and the world.

A rule is active while all its "when" conditions are true, and hold_s seconds
longer. While active, its "mood" and "idle" apply; when several active rules
have one, the first in the file wins, so the order is the priority. When a
rule becomes active, its "play" animation and "say" line fire, at most once
per cooldown_s; when it stops being active, its "play_end" animation plays.

A condition reads "<signal> <op> <value>", e.g. "speed_kmh > 100" or
"oil_c < $oil_warm_c", where $name is one of the thresholds in settings.json.
Signals with no value (e.g. motion_g without a sensor) make a condition false.
To offer a new signal, add it to SIGNALS and to Companion._signals()."""

import json
import math
import operator
import re

SIGNALS = ("ignition", "speed_kmh", "rpm", "oil_c", "coolant_c", "g_long", "g_lat",
           "motion_g", "place", "running_s")
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
       "==": operator.eq, "!=": operator.ne}
DEFAULT_COOLDOWN_S = 30
_CONDITION = re.compile(r"\s*([a-z_]+)\s*(<=|>=|==|!=|<|>)\s*(\S.*?)\s*")


def parse_condition(text, thresholds=None):
    """Return (signal, op, value). With thresholds=None, $names are not looked up.
    Raises ValueError with a readable message."""
    match = _CONDITION.fullmatch(text) if isinstance(text, str) else None
    if not match:
        raise ValueError(f'{json.dumps(text)} is not a condition like "speed_kmh > 100"')
    signal, op, raw = match.groups()
    if signal not in SIGNALS:
        raise ValueError(f'unknown signal "{signal}" (known: {", ".join(SIGNALS)})')
    if raw.startswith("$"):
        if not re.fullmatch(r"\$[a-z0-9_]+", raw):
            raise ValueError(f'"{raw}" is not a threshold name like $fast_kmh')
        if thresholds is None:
            return signal, op, raw
        if raw[1:] not in thresholds:
            raise ValueError(f'unknown threshold "{raw}" (settings.json has {", ".join(thresholds)})')
        return signal, op, thresholds[raw[1:]]
    try:
        return signal, op, json.loads(raw)
    except ValueError:
        return signal, op, raw  # a bare word, e.g. place == kastelruth


class Rule:
    def __init__(self, spec, thresholds):
        self.spec = spec
        self.id = spec["id"]
        self.conditions = [parse_condition(c, thresholds) for c in spec["when"]]
        self.active = False
        self.ended = False  # stopped being active in the last update
        self.true_until = -math.inf
        self.last_fired = -math.inf

    def update(self, signals, now):
        """Re-evaluate. Returns True when the rule fires (just became active, cooldown over)."""
        if holds_all(self.conditions, signals):
            self.true_until = now + self.spec.get("hold_s", 0)
        was_active = self.active
        self.active = now <= self.true_until
        self.ended = was_active and not self.active
        cooldown = self.spec.get("cooldown_s", DEFAULT_COOLDOWN_S)
        if self.active and not was_active and now - self.last_fired >= cooldown:
            self.last_fired = now
            return True
        return False


class Rules:
    """All usable rules, in file order. Rules whose conditions cannot be read
    are skipped (validate.cross_check() reports them)."""

    def __init__(self, rules_cfg, thresholds, previous=None):
        old = {rule.id: rule for rule in previous.rules} if previous else {}
        self.rules = []
        self.ended = []
        for spec in rules_cfg["rules"]:
            try:
                rule = Rule(spec, thresholds)
            except ValueError:
                continue
            if rule.id in old:  # an edit must not restart rules that are running
                prev = old[rule.id]
                rule.active, rule.true_until, rule.last_fired = prev.active, prev.true_until, prev.last_fired
            self.rules.append(rule)

    def update(self, signals, now):
        """Returns the active rules in file order, each as (rule, fired_just_now).
        Afterwards self.ended lists the rules that just stopped being active."""
        result = []
        for rule in self.rules:
            fired = rule.update(signals, now)
            if rule.active:
                result.append((rule, fired))
        self.ended = [rule for rule in self.rules if rule.ended]
        return result


def holds_all(conditions, signals):
    """True when every parsed condition holds for these signals."""
    return all(_holds(signals.get(signal), op, value) for signal, op, value in conditions)


def _holds(value, op, target):
    if value is None:
        return False
    try:
        return OPS[op](value, target)
    except TypeError:  # e.g. a number compared with text
        return False
