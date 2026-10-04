"""Points of interest around you, from OpenStreetMap: towns and villages,
peaks, passes, lakes, castles, sights, fuel and charging stations.

tools/fetch_poi.py downloads them for an area into assets/poi.json
(© OpenStreetMap contributors, ODbL). Without that file he only knows the
places in places.json. Each point: {"name", "kind", "lat", "lon"} and
optionally "name_de", "name_en" and "ele" (metres)."""

import json
import math
from pathlib import Path

KINDS = ("city", "town", "village", "peak", "pass", "lake", "castle", "attraction", "viewpoint",
         "fuel", "charging")
SETTLEMENTS = ("city", "town", "village")


def bearing_deg(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 to point 2: 0 is north, 90 east."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


class Pois:
    """The points in assets/poi.json, read again when the file changes."""

    def __init__(self, path):
        self.path = Path(path)
        self.error = None  # why the file could not be read, if it could not
        self._stamp = None
        self._items = []

    def all(self):
        try:
            stamp = self.path.stat().st_mtime_ns
        except OSError:
            self._stamp, self._items, self.error = None, [], None  # no file: nothing to know
            return self._items
        if stamp != self._stamp:
            self._stamp = stamp
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._items = [p for p in data["pois"] if _usable(p)]
                self.error = None
            except (OSError, ValueError, KeyError, TypeError) as e:
                self._items, self.error = [], f"{self.path.name}: {e}"
        return self._items


def _usable(p):
    return (isinstance(p, dict) and isinstance(p.get("name"), str) and p.get("kind") in KINDS
            and all(isinstance(p.get(k), (int, float)) and not isinstance(p.get(k), bool) for k in ("lat", "lon")))
