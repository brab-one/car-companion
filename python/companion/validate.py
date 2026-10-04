"""Checks for the config files, with messages that point at the problem, e.g.
    faces.json: moods.happy.h: expected a number, got "tall"

check(name, data) checks one file on its own. cross_check() then looks at
names one file takes from another (moods, animations, thresholds, images);
those problems are warnings, the companion just ignores what is missing.
To validate a new field, add a line to the matching _check_* function."""

import json
import re
import zoneinfo

from . import defaults
from .animator import EASES
from .faces import EYE_KEYS
from .rules import parse_condition

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
ID = re.compile(r"[a-z0-9_-]{1,40}")
IMAGE_NAME = re.compile(r"[a-z0-9_-]{1,40}\.png")
EYE_RANGES = {"w": (1, 128), "h": (1, 128), "r": (0, 64), "slant": (-64, 64), "cut": (0, 128)}
MOOD_KEYS = (*EYE_KEYS, "gap", "blink_s", "visor", "left", "right")
STEP_KEYS = ("mood", "look", "blink", "visor", "glint", "ms", "ease", "hold_ms", "repeat", "anim")
RULE_KEYS = ("id", "note", "when", "mood", "idle", "play", "play_end", "say", "level", "cooldown_s", "hold_s")
PLACE_KEYS = ("id", "name", "lat", "lon", "radius_m", "image", "clip", "caption", "say", "show_s", "cooldown_min")
PLACE_CLIP_KEYS = ("file", "frames", "fps")
CLIP_KEYS = ("id", "name", "file", "frames", "fps", "show_s", "every_min", "enabled", "when")


def check(name, data):
    """Return (data, errors) for one config file. Settings are completed with
    defaults first, so a settings file only needs the values it changes."""
    if name == "settings" and isinstance(data, dict):
        data = merged(defaults.SETTINGS, data)
    if name == "faces" and isinstance(data, dict) and isinstance(data.get("visor", {}), dict):
        data = {**data, "visor": merged(defaults.VISOR, data.get("visor", {}))}
    errors = []
    _CHECKS[name](data, errors)
    return data, [f"{name}.json: {e}" for e in errors]


def check_steps(steps):
    """Errors in a list of animation steps, e.g. sent by the app as a preview."""
    errors = []
    _steps(steps, "steps", errors)
    return errors


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
    _known_keys(data, ("version", "default", "moods", "visor"), "", errors)
    _version(data, errors)
    _visor(data.get("visor", defaults.VISOR), errors)
    moods = data.get("moods")
    if not isinstance(moods, dict) or not moods:
        errors.append("moods: expected an object with at least one mood")
        return
    for name, mood in moods.items():
        path = f"moods.{name}"
        if not ID.fullmatch(name):
            errors.append(f"{path}: use small letters, digits, - and _ in mood names")
        if not _object(mood, path, errors):
            continue
        _known_keys(mood, MOOD_KEYS, path, errors)
        _eye(mood, path, errors)
        if "gap" in mood:
            _number(mood["gap"], f"{path}.gap", errors, 0, 128)
        if "visor" in mood:
            _number(mood["visor"], f"{path}.visor", errors, 0, 1)
        if "blink_s" in mood and mood["blink_s"] is not None:  # null: no blinking
            _range(mood["blink_s"], f"{path}.blink_s", errors, 0.1, 600)
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


def _visor(visor, errors):
    if not _object(visor, "visor", errors):
        return
    _known_keys(visor, defaults.VISOR, "visor", errors)
    for key, (lo, hi) in {"y": (0, 128), "w": (1, 128), "h": (1, 128), "r": (0, 64), "alpha": (0, 1),
                          "glint": (-1, 2)}.items():
        _number(visor[key], f"visor.{key}", errors, lo, hi)
    for key in ("color", "shine"):
        if not (isinstance(visor[key], str) and HEX_COLOR.fullmatch(visor[key])):
            errors.append(f'visor.{key}: expected a colour like "#0B1E3A", got {_show(visor[key])}')


def _eye(eye, path, errors):
    for key, (lo, hi) in EYE_RANGES.items():
        if key in eye:
            _number(eye[key], f"{path}.{key}", errors, lo, hi)
    if "color" in eye and not (isinstance(eye["color"], str) and HEX_COLOR.fullmatch(eye["color"])):
        errors.append(f'{path}.color: expected a colour like "#00E5FF", got {_show(eye["color"])}')


# ---- animations.json --------------------------------------------------------

def _check_animations(data, errors):
    if not _object(data, "", errors):
        return
    _known_keys(data, ("version", "animations"), "", errors)
    _version(data, errors)
    animations = data.get("animations")
    if not _object(animations, "animations", errors):
        return
    for name, anim in animations.items():
        path = f"animations.{name}"
        if not _object(anim, path, errors):
            continue
        _known_keys(anim, ("steps", "repeat", "keep"), path, errors)
        if "repeat" in anim:
            _range(anim["repeat"], f"{path}.repeat", errors, 1, 100, whole=True)
        if "keep" in anim and not isinstance(anim["keep"], bool):
            errors.append(f"{path}.keep: expected true or false, got {_show(anim['keep'])}")
        _steps(anim.get("steps"), f"{path}.steps", errors)


def _steps(steps, path, errors):
    if not isinstance(steps, list) or not steps:
        errors.append(f"{path}: expected a list with at least one step")
        return
    for i, step in enumerate(steps):
        p = f"{path}[{i}]"
        if not _object(step, p, errors):
            continue
        _known_keys(step, STEP_KEYS, p, errors)
        if not any(k in step for k in ("mood", "look", "blink", "visor", "glint", "anim", "hold_ms")):
            errors.append(f"{p}: a step needs mood, look, blink, visor, glint, anim or hold_ms")
        for key in ("mood", "anim"):
            if key in step and not isinstance(step[key], str):
                errors.append(f"{p}.{key}: expected a name, got {_show(step[key])}")
        if "look" in step:
            _look(step["look"], f"{p}.look", errors)
        if "blink" in step:
            _number(step["blink"], f"{p}.blink", errors, 0, 1)
        if "visor" in step:
            _number(step["visor"], f"{p}.visor", errors, 0, 1.2)  # above 1: a bounce past its place
        if "glint" in step:
            _number(step["glint"], f"{p}.glint", errors, -1, 2)
        for key in ("ms", "hold_ms"):
            if key in step:
                _range(step[key], f"{p}.{key}", errors, 0, 60000)
        if "repeat" in step:
            _range(step["repeat"], f"{p}.repeat", errors, 1, 100, whole=True)
        if "ease" in step and step["ease"] not in EASES:
            errors.append(f"{p}.ease: expected one of {', '.join(EASES)}, got {_show(step['ease'])}")


def _look(value, path, errors):
    if value in ("random", "center"):
        return
    if not (isinstance(value, list) and len(value) == 2):
        errors.append(f'{path}: expected [x, y] from -1 to 1, "random" or "center", got {_show(value)}')
        return
    for v in value:
        _number(v, path, errors, -1, 1)


# ---- rules.json -------------------------------------------------------------

def _check_rules(data, errors):
    if not _object(data, "", errors):
        return
    _known_keys(data, ("version", "rules"), "", errors)
    _version(data, errors)
    rules = data.get("rules")
    if not isinstance(rules, list):
        errors.append("rules: expected a list")
        return
    seen = set()
    for i, rule in enumerate(rules):
        path = _item_path("rules", i, rule, seen, errors)
        if path is None:
            continue
        _known_keys(rule, RULE_KEYS, path, errors)
        when = rule.get("when")
        if not isinstance(when, list) or not when:
            errors.append(f'{path}.when: expected a list of conditions like ["speed_kmh > 100"]')
        else:
            for j, condition in enumerate(when):
                try:
                    parse_condition(condition)
                except ValueError as e:
                    errors.append(f"{path}.when[{j}]: {e}")
        for key in ("mood", "play", "play_end", "say", "note"):
            if key in rule and not isinstance(rule[key], str):
                errors.append(f"{path}.{key}: expected text, got {_show(rule[key])}")
        if "idle" in rule:
            _idle(rule["idle"], f"{path}.idle", errors)
        if "level" in rule:
            _range(rule["level"], f"{path}.level", errors, 1, 3, whole=True)
        if "cooldown_s" in rule:
            _number(rule["cooldown_s"], f"{path}.cooldown_s", errors, 0, 86400)
        if "hold_s" in rule:
            _number(rule["hold_s"], f"{path}.hold_s", errors, 0, 3600)
        if not any(k in rule for k in ("mood", "idle", "play", "play_end", "say")):
            errors.append(f"{path}: does nothing; give it a mood, idle, play, play_end or say")


def _idle(value, path, errors):
    if not _object(value, path, errors):
        return
    _known_keys(value, ("play", "every_s"), path, errors)
    play = value.get("play", [])
    if not (isinstance(play, list) and all(isinstance(n, str) for n in play)):
        errors.append(f'{path}.play: expected a list of animation names, got {_show(play)}')
    if "every_s" in value:
        _range(value["every_s"], f"{path}.every_s", errors, 0.2, 3600)


# ---- places.json ------------------------------------------------------------

def _check_places(data, errors):
    if not _object(data, "", errors):
        return
    _known_keys(data, ("version", "places"), "", errors)
    _version(data, errors)
    places = data.get("places")
    if not isinstance(places, list):
        errors.append("places: expected a list")
        return
    seen = set()
    for i, place in enumerate(places):
        path = _item_path("places", i, place, seen, errors)
        if path is None:
            continue
        _known_keys(place, PLACE_KEYS, path, errors)
        if not (isinstance(place.get("name"), str) and place["name"].strip()):
            errors.append(f"{path}.name: expected text, got {_show(place.get('name'))}")
        _number(place.get("lat"), f"{path}.lat", errors, -90, 90)
        _number(place.get("lon"), f"{path}.lon", errors, -180, 180)
        _number(place.get("radius_m"), f"{path}.radius_m", errors, 10, 200000)
        if "image" in place and not (isinstance(place["image"], str) and IMAGE_NAME.fullmatch(place["image"])):
            errors.append(f'{path}.image: expected a file name like "schlern.png"'
                          f" (small letters, digits, - and _), got {_show(place['image'])}")
        if "clip" in place and _object(place["clip"], f"{path}.clip", errors):
            _known_keys(place["clip"], PLACE_CLIP_KEYS, f"{path}.clip", errors)
            _clip_file(place["clip"], f"{path}.clip", errors)
        for key in ("caption", "say"):
            if key in place and not isinstance(place[key], str):
                errors.append(f"{path}.{key}: expected text, got {_show(place[key])}")
        if "show_s" in place:
            _number(place["show_s"], f"{path}.show_s", errors, 1, 300)
        if "cooldown_min" in place:
            _number(place["cooldown_min"], f"{path}.cooldown_min", errors, 0, 10080)


# ---- clips.json -------------------------------------------------------------

def _check_clips(data, errors):
    if not _object(data, "", errors):
        return
    _known_keys(data, ("version", "clips"), "", errors)
    _version(data, errors)
    clips = data.get("clips")
    if not isinstance(clips, list):
        errors.append("clips: expected a list")
        return
    seen = set()
    for i, clip in enumerate(clips):
        path = _item_path("clips", i, clip, seen, errors)
        if path is None:
            continue
        _known_keys(clip, CLIP_KEYS, path, errors)
        if not (isinstance(clip.get("name"), str) and clip["name"].strip()):
            errors.append(f"{path}.name: expected text, got {_show(clip.get('name'))}")
        _clip_file(clip, path, errors)
        _number(clip.get("show_s"), f"{path}.show_s", errors, 1, 300)
        _number(clip.get("every_min"), f"{path}.every_min", errors, 0.5, 1440)
        if "enabled" in clip and not isinstance(clip["enabled"], bool):
            errors.append(f"{path}.enabled: expected true or false, got {_show(clip['enabled'])}")
        when = clip.get("when", [])
        if not isinstance(when, list):
            errors.append(f'{path}.when: expected a list of conditions like ["speed_kmh > 20"]')
        else:
            for j, condition in enumerate(when):
                try:
                    parse_condition(condition)
                except ValueError as e:
                    errors.append(f"{path}.when[{j}]: {e}")


def _clip_file(clip, path, errors):
    """file, frames and fps of a clip, in clips.json or a place's "clip"."""
    if not (isinstance(clip.get("file"), str) and IMAGE_NAME.fullmatch(clip["file"])):
        errors.append(f'{path}.file: expected a file name like "wheel.png", got {_show(clip.get("file"))}')
    frames = clip.get("frames")
    if isinstance(frames, bool) or not isinstance(frames, int):
        errors.append(f"{path}.frames: expected a whole number, got {_show(frames)}")
    else:
        _number(frames, f"{path}.frames", errors, 1, 300)
    _number(clip.get("fps"), f"{path}.fps", errors, 1, 30)


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
    _number(data["mood_ms"], "mood_ms", errors, 0, 5000)
    _idle(data["idle"], "idle", errors)
    _range(data["chattiness"], "chattiness", errors, 0, 3, whole=True)
    bubble = data["bubble"]
    if _object(bubble, "bubble", errors):
        _known_keys(bubble, spec["bubble"], "bubble", errors)
        if not isinstance(bubble["enabled"], bool):
            errors.append(f"bubble.enabled: expected true or false, got {_show(bubble['enabled'])}")
        if not (isinstance(bubble["color"], str) and HEX_COLOR.fullmatch(bubble["color"])):
            errors.append(f'bubble.color: expected a colour like "#FFFFFF", got {_show(bubble["color"])}')
        _number(bubble["min_s"], "bubble.min_s", errors, 0.5, 30)
        _number(bubble["per_char_s"], "bubble.per_char_s", errors, 0, 1)
    _number(data["say_gap_s"], "say_gap_s", errors, 0, 3600)
    _number(data["sleep_after_off_s"], "sleep_after_off_s", errors, 0, 3600)
    _number(data["place_exit_margin"], "place_exit_margin", errors, 0, 2)
    _timezone(data["timezone"], errors)
    _assistant(data["assistant"], spec["assistant"], errors)
    if _object(data["thresholds"], "thresholds", errors):
        for key, value in data["thresholds"].items():  # any names: rules use them as $name
            if not re.fullmatch(r"[a-z0-9_]+", key):
                errors.append(f"thresholds.{key}: use small letters, digits and _ in names")
            _number(value, f"thresholds.{key}", errors)


def _assistant(a, spec, errors):
    if not _object(a, "assistant", errors):
        return
    _known_keys(a, spec, "assistant", errors)
    if not isinstance(a["enabled"], bool):
        errors.append(f"assistant.enabled: expected true or false, got {_show(a['enabled'])}")
    if not isinstance(a["car"], str):
        errors.append(f'assistant.car: expected text like "Subaru BRZ", got {_show(a["car"])}')
    words = a["wake_words"]
    if not (isinstance(words, list) and words and all(isinstance(w, str) and w.strip() for w in words)):
        errors.append(f'assistant.wake_words: expected a list of phrases like ["hey buddy"], got {_show(words)}')
    langs = a["languages"]
    if not (isinstance(langs, list) and langs and all(lang in ("en", "de") for lang in langs)):
        errors.append(f'assistant.languages: expected a list of "en" and "de", got {_show(langs)}')
    _number(a["nearby_km"], "assistant.nearby_km", errors, 1, 200)
    _range(a["llm_max_tokens"], "assistant.llm_max_tokens", errors, 16, 1024, whole=True)
    _number(a["llm_temperature"], "assistant.llm_temperature", errors, 0, 2)
    _number(a["llm_timeout_s"], "assistant.llm_timeout_s", errors, 5, 600)


def _timezone(tz, errors):
    if tz == "":
        return
    try:
        zoneinfo.ZoneInfo(tz)
    except (ValueError, TypeError, zoneinfo.ZoneInfoNotFoundError):
        errors.append(f'timezone: expected a time zone like "Europe/Rome", or "", got {_show(tz)}')


# ---- board.json -------------------------------------------------------------

def _check_board(data, errors):
    """The board helper checks the values against what the hardware offers too."""
    if not _object(data, "", errors):
        return
    _known_keys(data, defaults.BOARD, "", errors)
    _version(data, errors)
    if data.get("cpu_max_mhz") is not None:
        _number(data["cpu_max_mhz"], "cpu_max_mhz", errors, 100, 5000)
    gov = data.get("cpu_governor")
    if gov is not None and not (isinstance(gov, str) and re.fullmatch(r"[a-z_]{1,30}", gov)):
        errors.append(f'cpu_governor: expected a name like "schedutil", or null, got {_show(gov)}')
    if data.get("wifi_powersave") is not None and not isinstance(data["wifi_powersave"], bool):
        errors.append(f"wifi_powersave: expected true, false or null, got {_show(data['wifi_powersave'])}")


_CHECKS = {"faces": _check_faces, "animations": _check_animations, "rules": _check_rules,
           "places": _check_places, "clips": _check_clips, "settings": _check_settings,
           "board": _check_board}


# ---- names used across files ------------------------------------------------

def cross_check(data, image_names, clip_names=()):
    """Warnings for names that one config file uses but another does not have."""
    warnings = []
    moods = data["faces"]["moods"]
    animations = data["animations"]["animations"]
    thresholds = data["settings"]["thresholds"]
    for name, anim in animations.items():
        for i, step in enumerate(anim["steps"]):
            path = f"animations.json: animations.{name}.steps[{i}]"
            if "mood" in step and step["mood"] not in moods:
                warnings.append(f'{path}: unknown mood "{step["mood"]}"')
            if "anim" in step and step["anim"] not in animations:
                warnings.append(f'{path}: unknown animation "{step["anim"]}"')
    for rule in data["rules"]["rules"]:
        path = f"rules.json: rules.{rule['id']}"
        if "mood" in rule and rule["mood"] not in moods:
            warnings.append(f'{path}.mood: unknown mood "{rule["mood"]}"')
        for key in ("play", "play_end"):
            if key in rule and rule[key] not in animations:
                warnings.append(f'{path}.{key}: unknown animation "{rule[key]}"')
        for name in rule.get("idle", {}).get("play", []):
            if name not in animations:
                warnings.append(f'{path}.idle.play: unknown animation "{name}"')
        for condition in rule["when"]:
            try:
                parse_condition(condition, thresholds)
            except ValueError as e:
                warnings.append(f"{path}.when: {e}; the rule is ignored")
    for name in data["settings"]["idle"]["play"]:
        if name not in animations:
            warnings.append(f'settings.json: idle.play: unknown animation "{name}"')
    for place in data["places"]["places"]:
        if "image" in place and place["image"] not in image_names:
            warnings.append(f'places.json: places.{place["id"]}.image: "{place["image"]}"'
                            " is not in assets/images")
        if "clip" in place and place["clip"]["file"] not in clip_names:
            warnings.append(f'places.json: places.{place["id"]}.clip.file: "{place["clip"]["file"]}"'
                            " is not in assets/clips")
    for clip in data["clips"]["clips"]:
        path = f"clips.json: clips.{clip['id']}"
        if clip["file"] not in clip_names:
            warnings.append(f'{path}.file: "{clip["file"]}" is not in assets/clips')
        for condition in clip.get("when", []):
            try:
                parse_condition(condition, thresholds)
            except ValueError as e:
                warnings.append(f"{path}.when: {e}; the clip is skipped")
    return warnings


# ---- helpers ----------------------------------------------------------------

def _item_path(kind, i, item, seen, errors):
    """Path for a list item with an "id", e.g. rules.cold_oil. None if it is not an object."""
    path = f"{kind}[{i}]"
    if not _object(item, path, errors):
        return None
    item_id = item.get("id")
    if not (isinstance(item_id, str) and ID.fullmatch(item_id)):
        errors.append(f'{path}.id: expected a short name like "cold_oil" (small letters, digits,'
                      f" - and _), got {_show(item_id)}")
        return path
    if item_id in seen:
        errors.append(f"{path}.id: {item_id} is used twice")
        return path
    seen.add(item_id)
    return f"{kind}.{item_id}"


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


def _range(value, path, errors, lo, hi, whole=False):
    """A number, or [min, max] for a random value in between."""
    if isinstance(value, list) and len(value) != 2:
        errors.append(f"{path}: expected a number or [min, max], got {_show(value)}")
        return
    values = value if isinstance(value, list) else [value]
    for v in values:
        if whole and (isinstance(v, bool) or not isinstance(v, int)):
            errors.append(f"{path}: expected a whole number, got {_show(v)}")
            return
        if not _number(v, path, errors, lo, hi):
            return
    if len(values) == 2 and values[0] > values[1]:
        errors.append(f"{path}: min {values[0]} is larger than max {values[1]}")


def _version(data, errors):
    if data.get("version", 1) != 1:
        errors.append(f"version: expected 1, got {_show(data.get('version'))}")


def _join(path, key):
    return f"{path}.{key}" if path else str(key)


def _show(value):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 40 else text[:37] + "..."
