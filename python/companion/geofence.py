"""Geofences from places.json: notices when the car enters a place.

A place is entered within radius_m, but only left again beyond
radius_m * (1 + exit_margin). That gap keeps GPS jitter at the edge from
triggering the same place again and again. After a place triggered, it
stays quiet for its cooldown_min."""

import math

EARTH_RADIUS_M = 6371000.0


def distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class Geofences:
    def __init__(self):
        self.inside = []         # ids of the places we are in, in places.json order
        self._last_trigger = {}  # id -> time it last triggered

    def update(self, places, lat, lon, exit_margin, now):
        """Returns the places just entered, each as (place, minutes of cooldown left);
        0 minutes left means the place triggers now."""
        entered, inside = [], []
        for place in places:
            d = distance_m(lat, lon, place["lat"], place["lon"])
            if place["id"] in self.inside:
                if d <= place["radius_m"] * (1 + exit_margin):
                    inside.append(place["id"])
            elif d <= place["radius_m"]:
                inside.append(place["id"])
                last = self._last_trigger.get(place["id"], -math.inf)
                left_s = place.get("cooldown_min", 60) * 60 - (now - last)
                wait_min = math.ceil(left_s / 60) if left_s > 0 else 0
                if wait_min == 0:
                    self._last_trigger[place["id"]] = now
                entered.append((place, wait_min))
        self.inside = inside
        return entered

    @property
    def current(self):
        """The place we are in (the first one in places.json), or None."""
        return self.inside[0] if self.inside else None
