"""Turns a mood name into eye parameters, using faces.json.

Every mood inherits from the default mood and only lists what changes.
Inside a mood, "left" and "right" change one eye only (as seen by the viewer).
Adding a mood needs no code: add an entry to config/faces.json."""

EYE_KEYS = ("w", "h", "r", "color", "slant", "cut")


def resolve(faces, name):
    """Return {"left": eye, "right": eye, "gap": px, "blink_s": [min, max] or None}.
    An unknown name gives the default mood."""
    moods = faces["moods"]
    base = moods[faces["default"]]
    mood = moods.get(name, base)
    pair = {}
    for side in ("left", "right"):
        eye = {}
        for layer in (base, base.get(side, {}), mood, mood.get(side, {})):
            eye.update((k, layer[k]) for k in EYE_KEYS if k in layer)
        pair[side] = eye
    pair["gap"] = mood.get("gap", base["gap"])
    pair["blink_s"] = mood.get("blink_s", base.get("blink_s"))
    return pair
