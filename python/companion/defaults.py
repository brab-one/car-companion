"""Built-in fallbacks.

SETTINGS lists every setting with its default value. Settings missing from
settings.json are taken from here, so a new setting is added here first and
older settings files keep working.

FILES is used when a config file and its last good copy are both unusable,
so the companion always has a face to show."""

SETTINGS = {
    "version": 1,
    "displays": 1,          # 1: both eyes on one OLED, 2: one OLED per eye
    "fps": 30,              # scene updates per second
    "brightness": {
        "mode": "manual",   # "manual" or "auto" (auto follows sunrise/sunset from step 4)
        "manual": 100,      # percent
    },
    "layout": {
        "look_x_px": 18,    # how far the eyes move for look x = +-1
        "look_y_px": 12,    # how far the eyes move for look y = +-1
        "dual_scale": 2.0,  # eye size factor with two displays
    },
}

FACES = {
    "version": 1,
    "default": "neutral",
    "moods": {
        "neutral": {"w": 36, "h": 44, "r": 10, "color": "#00E5FF",
                    "slant": 0, "cut": 0, "gap": 14, "blink_s": [3, 7]},
    },
}

FILES = {"faces": FACES, "settings": SETTINGS}
