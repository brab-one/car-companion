"""Built-in fallbacks.

SETTINGS lists every setting with its default value. Settings missing from
settings.json are taken from here, so a new setting is added here first and
older settings files keep working.

FILES is used when a config file and its last good copy are both unusable,
so the companion always has a face to show."""

SETTINGS = {
    "version": 1,
    "displays": 1,             # 1: both eyes on one OLED, 2: one OLED per eye
    "fps": 30,                 # scene updates per second
    "brightness": {
        "mode": "manual",      # "manual" or "auto" (auto will follow sunrise/sunset)
        "manual": 100,         # percent
    },
    "layout": {
        "look_x_px": 18,       # how far the eyes move for look x = +-1
        "look_y_px": 12,       # how far the eyes move for look y = +-1
        "dual_scale": 2.0,     # eye size factor with two displays
    },
    "mood_ms": 350,            # how long a change from one mood to another takes
    "idle": {                  # what the eyes do when nothing else happens
        "play": ["glance_left", "glance_right", "look_up"],
        "every_s": [5, 12],
    },
    "chattiness": 2,           # 0 silent, 1 important lines only, 2 normal, 3 everything
    "bubble": {                # what he says, in a speech bubble on the display
        "enabled": True,
        "color": "#FFFFFF",    # outline and text
        "min_s": 2.5,          # shown at least this long,
        "per_char_s": 0.06,    # plus this per character (at most 10 s)
    },
    "say_gap_s": 8,            # at least this many seconds between two lines
    "sleep_after_off_s": 20,   # display off this long after the ignition is turned off
    "place_exit_margin": 0.2,  # a place is left at radius_m * (1 + this), see geofence.py
    "timezone": "",            # e.g. "Europe/Rome" for his answers; "" is the board's own (UTC)
    "assistant": {             # questions to him, see assistant.py
        "enabled": True,
        "car": "",             # its make and model, e.g. "Subaru BRZ", for "what car is it?"
        "wake_words": ["hey buddy", "hallo kumpel"],  # what makes him listen (with a microphone, on the board)
        "languages": ["en", "de"],  # what you may speak; the first is used when unsure
        "nearby_km": 20,       # how far around you he looks for places to talk about
        "llm_max_tokens": 60,  # the length of an answer from the AI model
        "llm_temperature": 0.3,  # 0 plain .. 1 creative
        "llm_timeout_s": 60,   # how long he waits for the AI model
    },
    "android_auto": {          # wireless Android Auto through the board (android_auto/bridge.py)
        "enabled": False,      # on: the board runs an access point for the phone
        "keep_wifi": True,     # meanwhile stay on your Wi-Fi too (the access point gets a second, virtual interface)
        "wifi_name": "",       # the access point's name; "" makes one up (CarCompanion-XXXX)
        "wifi_password": "",   # 8 to 63 characters; "" makes one up on the board
        "wifi_band": "2.4",    # "2.4" or "5" GHz (the UNO Q's Wi-Fi allows no access point on 5 GHz)
        "wifi_channel": 0,     # 0: 6 on 2.4 GHz, 36 on 5 GHz
        "country": "",         # the country you drive in, two letters ("IT"): its Wi-Fi rules; "" the board's
        "pairing_min": 3,      # how long a phone can pair after switching on or "Pair a phone"
    },
    "thresholds": {            # values rules.json can use as $name; add your own
        "fast_kmh": 100,
        "slow_kmh": 5,
        "shake_g": 0.35,
        "oil_warm_c": 80,
        "coolant_hot_c": 105,
        "redline_rpm": 7500,
    },
}

VISOR = {  # how the visor looks; moods say how far it is down ("visor": 0 up .. 1 down)
    "y": 62,              # centre when fully down
    "w": 100, "h": 44, "r": 12,
    "color": "#0B1E3A",   # the tint
    "alpha": 0.82,        # 0 clear .. 1 the eyes cannot be seen behind it
    "shine": "#9CC8FF",   # the reflection stripes
    "glint": 0.2,         # where the reflection rests, across the visor (0 left .. about 1.4 gone right)
}

FACES = {
    "version": 1,
    "default": "neutral",
    "moods": {
        "neutral": {"w": 36, "h": 44, "r": 10, "color": "#00E5FF",
                    "slant": 0, "cut": 0, "gap": 14, "blink_s": [3, 7]},
    },
}

ANIMATIONS = {
    "version": 1,
    "animations": {
        "blink": {"steps": [{"blink": 1, "ms": 70}, {"blink": 0, "ms": 90}]},
    },
}

RULES = {"version": 1, "rules": []}

PLACES = {"version": 1, "places": []}

CLIPS = {"version": 1, "clips": []}

BOARD = {  # applied by the board helper (board/board_helper.py); null leaves the board's own value
    "version": 1,
    "cpu_max_mhz": None,     # the processor's frequency limit
    "cpu_governor": None,    # its power policy, e.g. "schedutil" or "performance"
    "wifi_powersave": None,  # true or false
}

FILES = {"faces": FACES, "animations": ANIMATIONS, "rules": RULES,
         "places": PLACES, "clips": CLIPS, "settings": SETTINGS, "board": BOARD}
