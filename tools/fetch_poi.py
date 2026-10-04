#!/usr/bin/env python3
"""Download points of interest around your places from OpenStreetMap into
assets/poi.json: towns and villages, peaks, passes, lakes, castles, sights,
viewpoints, fuel and charging stations. He uses them to answer questions
about the surroundings, offline.

    python3 tools/fetch_poi.py                          around the places in places.json
    python3 tools/fetch_poi.py --lat 46.5 --lon 11.35 --radius-km 60

Needs internet once (the Overpass API); run it again for another area. The
data is © OpenStreetMap contributors, under the ODbL. Standard library only."""

import argparse
import datetime
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from companion.geofence import distance_m  # noqa: E402  (needs the path above)
from companion.jsonfile import dumps_compact, write_text_atomic  # noqa: E402

OVERPASS = "https://overpass-api.de/api/interpreter"
OUT = ROOT / "assets" / "poi.json"

# OpenStreetMap tags -> our kinds (poi.KINDS). Fuel and charging stations may have no name.
QUERIES = [
    ('node["place"~"^(city|town|village)$"]["name"]', None),
    ('node["natural"="peak"]["name"]', "peak"),
    ('node["mountain_pass"="yes"]["name"]', "pass"),
    ('nwr["natural"="water"]["water"="lake"]["name"]', "lake"),
    ('nwr["historic"="castle"]["name"]', "castle"),
    ('nwr["tourism"="attraction"]["name"]', "attraction"),
    ('node["tourism"="viewpoint"]["name"]', "viewpoint"),
    ('nwr["amenity"="fuel"]', "fuel"),
    ('nwr["amenity"="charging_station"]', "charging"),
]


def main():
    parser = argparse.ArgumentParser(description="Download points of interest from OpenStreetMap.")
    parser.add_argument("--lat", type=float, help="centre (default: the middle of your places)")
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius-km", type=float, default=40)
    args = parser.parse_args()
    lat, lon = args.lat, args.lon
    if lat is None or lon is None:
        places = json.loads((ROOT / "config" / "places.json").read_text(encoding="utf-8"))["places"]
        if not places:
            sys.exit("No places in config/places.json: give --lat and --lon.")
        lat = sum(p["lat"] for p in places) / len(places)
        lon = sum(p["lon"] for p in places) / len(places)
    radius_m = round(args.radius_km * 1000)
    print(f"Asking OpenStreetMap for points within {args.radius_km:g} km of {lat:.4f}, {lon:.4f} ...")
    elements = overpass(lat, lon, radius_m)
    pois = convert(elements)
    data = {
        "source": "© OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright)",
        "created": datetime.date.today().isoformat(),
        "center": [round(lat, 5), round(lon, 5)],
        "radius_km": args.radius_km,
        "pois": pois,
    }
    write_text_atomic(OUT, dumps_compact(data) + "\n")
    kinds = {}
    for p in pois:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print(f"Wrote {len(pois)} points to {OUT.relative_to(ROOT)}: "
          + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])))


def overpass(lat, lon, radius_m):
    parts = "".join(f"{q}(around:{radius_m},{lat},{lon});" for q, _ in QUERIES)
    query = f"[out:json][timeout:120];({parts});out center tags;"
    request = urllib.request.Request(
        OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "car-companion (https://github.com/brab-one/car-companion)"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))["elements"]


def convert(elements):
    pois = []
    for e in elements:
        tags = e.get("tags", {})
        where = e if "lat" in e else e.get("center")
        kind = kind_of(tags)
        if not where or not kind:
            continue
        name = tags.get("name") or tags.get("brand") or tags.get("operator")
        if not name:
            name = "fuel station" if kind == "fuel" else "charging station"
        poi = {"name": name, "kind": kind, "lat": round(where["lat"], 5), "lon": round(where["lon"], 5)}
        for lang in ("de", "en"):
            if tags.get(f"name:{lang}") and tags[f"name:{lang}"] != name:
                poi[f"name_{lang}"] = tags[f"name:{lang}"]
        ele = elevation(tags.get("ele"))
        if ele is not None:
            poi["ele"] = ele
        pois.append(poi)
    return dedupe(pois)


def kind_of(tags):
    if tags.get("place") in ("city", "town", "village"):
        return tags["place"]
    return next((kind for query, kind in QUERIES[1:] if _matches(query, tags)), None)


def _matches(query, tags):
    """Do an element's tags fit a query's filters, ["key"="value"] and ["key"]?"""
    for part in query.split("[")[1:]:
        part = part.rstrip("]")
        if "=" not in part:
            if part.strip('"') not in tags:
                return False
            continue
        key, value = (s.strip('"') for s in part.split("=", 1))
        if tags.get(key) != value:
            return False
    return True


def elevation(text):
    try:
        return round(float(str(text).replace("m", "").replace(",", ".").strip()))
    except (TypeError, ValueError):
        return None


def dedupe(pois):
    """The same name and kind within 300 m is one point (e.g. a lake drawn in pieces)."""
    kept, seen = [], {}  # (name, kind) -> points kept with it
    for p in pois:
        same = seen.setdefault((p["name"], p["kind"]), [])
        if not any(distance_m(p["lat"], p["lon"], q["lat"], q["lon"]) < 300 for q in same):
            same.append(p)
            kept.append(p)
    return kept


if __name__ == "__main__":
    main()
