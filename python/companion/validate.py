"""Checks for the config files, with messages that point at the problem, e.g.
    faces.json: moods.happy.h: expected a number, got "tall"

check(name, data) is the entry point. To validate a new field, add a line to
the matching _check_* function; for a new file, add a function to _CHECKS."""

import json
import re

from . import defaults
from .faces import EYE_KEYS

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
EYE_RANGES = {"w": (1, 128), "h": (1, 128), "r": (0, 64), "slant": (-64, 64), "cut": (0, 128)}
MOOD_KEYS = (*EYE_KEYS, "gap", "blink_s", "left", "right")


def check(name, data):
    """Return (data, errors) for one config file. Settings are completed with
    defaults first, so a settings file only needs the values it changes."""
    if name == "settings" and isinstance(data, dict):
        data = merged(defaults.SETTINGS, data)
    errors = []
    _CHECKS[name](data, errors)
    return data, [f"{name}.json: {e}" for e in errors]


def merged(base, override):
    """Copy of base with override's values on top; nested objects are merged too."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            value = merged(base[key], value)
        out[key] = value
    return out


# ---- faces.json -------------------------------------------------------------

def _check_faces(data, errors):
    if not _object(data, "", errors):
        return
    _known_keys(data, ("version", "default", "moods"), "", errors)
    _version(data, errors)
    moods = data.get("moods")
    if not isinstance(moods, dict) or not moods:
        errors.append("moods: expected an object with at least one mood")
        return
    for name, mood in moods.items():
        path = f"moods.{name}"
        if not _object(mood, path, errors):
            continue
        _known_keys(mood, MOOD_KEYS, path, errors)
        _eye(mood, path, errors)
        if "gap" in mood:
            _number(mood["gap"], f"{path}.gap", errors, 0, 128)
        if "blink_s" in mood:
            _blink(mood["blink_s"], f"{path}.blink_s", errors)
        for side in ("left", "right"):
            if side in mood and _object(mood[side], f"{path}.{side}", errors):
                _known_keys(mood[side], EYE_KEYS, f"{path}.{side}", errors)
                _eye(mood[side], f"{path}.{side}", errors)
    default = data.get("default")
    if not isinstance(default, str) or default not in moods:
        errors.append(f"default: {_show(default)} is not one of the moods")
    elif isinstance(moods[default], dict):
        missing = [k for k in (*EYE_KEYS, "gap") if k not in moods[default]]
        if missing:
            errors.append(f"moods.{default}: the default mood must set {', '.join(missing)}"
                          " (the other moods inherit from it)")


def _eye(eye, path, errors):
    for key, (lo, hi) in EYE_RANGES.items():
        if key in eye:
            _number(eye[key], f"{path}.{key}", errors, lo, hi)
    if "color" in eye and not (isinstance(eye["color"], str) and HEX_COLOR.fullmatch(eye["color"])):
        errors.append(f'{path}.color: expected a colour like "#00E5FF", got {_show(eye["color"])}')


def _blink(value, path, errors):
    if value is None:
        return  # no blinking
    if not (isinstance(value, list) and len(value) == 2):
        errors.append(f"{path}: expected [min, max] seconds or null, got {_show(value)}")
    elif all(_number(v, path, errors, 0.1, 600) for v in value) and value[0] > value[1]:
        errors.append(f"{path}: min {value[0]} is larger than max {value[1]}")


# ---- settings.json ----------------------------------------------------------

def _check_settings(data, errors):
    if not _object(data, "", errors):
        return
    spec = defaults.SETTINGS
    _known_keys(data, spec, "", errors)
    _version(data, errors)
    if type(data["displays"]) is not int or data["displays"] not in (1, 2):
        errors.append(f"displays: expected 1 or 2, got {_show(data['displays'])}")
    _number(data["fps"], "fps", errors, 1, 60)
    b = data["brightness"]
    if _object(b, "brightness", errors):
        _known_keys(b, spec["brightness"], "brightness", errors)
        if b["mode"] not in ("manual", "auto"):
            errors.append(f'brightness.mode: expected "manual" or "auto", got {_show(b["mode"])}')
        _number(b["manual"], "brightness.manual", errors, 0, 100)
    lay = data["layout"]
    if _object(lay, "layout", errors):
        _known_keys(lay, spec["layout"], "layout", errors)
        _number(lay["look_x_px"], "layout.look_x_px", errors, 0, 64)
        _number(lay["look_y_px"], "layout.look_y_px", errors, 0, 64)
        _number(lay["dual_scale"], "layout.dual_scale", errors, 0.5, 4)


_CHECKS = {"faces": _check_faces, "settings": _check_settings}


# ---- helpers ----------------------------------------------------------------

def _object(value, path, errors):
    if isinstance(value, dict):
        return True
    errors.append(f"{path or 'file'}: expected an object {{...}}, got {_show(value)}")
    return False


def _known_keys(obj, allowed, path, errors):
    """Unknown keys are usually typos ("heigth"), so they are reported."""
    for key in obj:
        if key not in allowed:
            errors.append(f"{_join(path, key)}: unknown field (allowed: {', '.join(allowed)})")


def _number(value, path, errors, lo=None, hi=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path}: expected a number, got {_show(value)}")
        return False
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        errors.append(f"{path}: {value} is outside the allowed range {lo} to {hi}")
        return False
    return True


def _version(data, errors):
    if data.get("version", 1) != 1:
        errors.append(f"version: expected 1, got {_show(data.get('version'))}")


def _join(path, key):
    return f"{path}.{key}" if path else str(key)


def _show(value):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 40 else text[:37] + "..."
