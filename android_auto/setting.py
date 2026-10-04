"""The Android Auto settings: android_auto in the companion's settings.json
(Configure > Board, later the phone app), which the bridge reads every few
seconds. No D-Bus here, so the tests run on any PC."""

import json
from pathlib import Path

# As in python/companion/defaults.py (a test checks they match).
DEFAULTS = {"enabled": False, "keep_wifi": True, "wifi_name": "", "wifi_password": "", "wifi_band": "2.4",
            "wifi_channel": 0, "country": "", "pairing_min": 3}


def read(config_dir):
    """The android_auto settings as the companion last checked them: its last good
    copy of settings.json (config/.good, rewritten whenever the file passes its
    checks), else settings.json itself; what they leave out from DEFAULTS."""
    config_dir = Path(config_dir)
    for path in (config_dir / ".good" / "settings.json", config_dir / "settings.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        aa = data.get("android_auto") if isinstance(data, dict) else None
        return {**DEFAULTS, **(aa if isinstance(aa, dict) else {})}
    return dict(DEFAULTS)
