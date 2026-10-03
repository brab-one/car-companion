"""Turns a mood name into eye parameters, using faces.json.

Every mood inherits from the default mood and only lists what changes.
Inside a mood, "left" and "right" change one eye only (as seen by the viewer).
"visor" says how far the visor is down, from 0 (up, not shown) to 1.
Adding a mood needs no code: add an entry to config/faces.json."""

EYE_KEYS = ("w", "h", "r", "color", "slant", "cut")


def resolve(faces, name):
    """Return {"left": eye, "right": eye, "gap": px, "visor": 0..1, "blink_s": [min, max] or None}.
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
    pair["visor"] = mood.get("visor", base.get("visor", 0))
    pair["glint"] = faces.get("visor", {}).get("glint", 0.2)  # where the visor's reflection rests
    pair["blink_s"] = mood.get("blink_s", base.get("blink_s"))
    return pair
