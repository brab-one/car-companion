"""Questions to the companion, and his answers, in English or German.

A question arrives as text: typed in the app, or (on the board, with a
microphone) heard after the wake word and turned into text. Questions about
the car and where you are get an exact answer from the data, at once
(direct_answer). Anything else goes to the AI model together with those
facts (messages()); a small model on the board needs a few seconds, so it
runs on a worker thread (Asker). Companion.on_ask puts it together."""

import queue
import re
import threading
import unicodedata

from .geofence import distance_m
from .poi import SETTLEMENTS, bearing_deg

LANGUAGES = ("en", "de")
UNKNOWN = {"en": "I can't answer that yet.", "de": "Das kann ich noch nicht beantworten."}
NO_MODEL = {"en": "Sorry, I can't think right now.", "de": "Tut mir leid, ich kann gerade nicht nachdenken."}
NOT_LOCATED = {"en": "I don't know where we are yet.", "de": "Ich weiß noch nicht, wo wir sind."}
NO_MAP = {"en": "I have no map of this area yet.", "de": "Ich habe noch keine Karte von dieser Gegend."}

SYSTEM = {
    "en": "You are a small, friendly companion that lives on the dashboard of a car. Answer the driver's "
          "question in English, in one or two short sentences (at most 30 words), as plain text without "
          "lists. Use only the facts below. If they don't answer the question, say that you don't know.\n\n"
          "Facts:\n",
    "de": "Du bist ein kleiner, freundlicher Begleiter auf dem Armaturenbrett eines Autos. Beantworte die "
          "Frage des Fahrers auf Deutsch, in ein oder zwei kurzen Sätzen (höchstens 30 Wörter), als "
          "einfacher Text ohne Listen. Verwende nur die Fakten unten. Wenn sie die Frage nicht beantworten, "
          "sag, dass du es nicht weißt.\n\nFakten:\n",
}

# How his face shows that he listens and thinks, when animations.json has no
# "listening" or "thinking" animation (the shipped animations.json has both).
FACE_STEPS = {
    "listening": [{"look": "center", "ms": 120, "ease": "out"},
                  {"mood": "surprised", "ms": 110, "ease": "out", "hold_ms": 500}],
    "thinking": [{"look": [-0.6, -0.85], "ms": 260, "ease": "out", "hold_ms": [500, 900]},
                 {"look": [0.6, -0.85], "ms": 300, "ease": "out", "hold_ms": [500, 900]}],
}

KIND_WORDS = {
    "en": {"city": "city", "town": "town", "village": "village", "peak": "peak", "pass": "mountain pass",
           "lake": "lake", "castle": "castle", "attraction": "sight", "viewpoint": "viewpoint",
           "fuel": "fuel station", "charging": "charging station", "place": "one of your places"},
    "de": {"city": "Stadt", "town": "Ort", "village": "Dorf", "peak": "Berg", "pass": "Pass", "lake": "See",
           "castle": "Burg", "attraction": "Sehenswürdigkeit", "viewpoint": "Aussichtspunkt",
           "fuel": "Tankstelle", "charging": "Ladestation", "place": "einer deiner Orte"},
}
COMPASS = {
    "en": ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"),
    "de": ("nördlich", "nordöstlich", "östlich", "südöstlich", "südlich", "südwestlich", "westlich",
           "nordwestlich"),
}

# Words that tell the two languages apart; umlauts count for German too.
_WORDS = {
    "en": set("i we you is are how where what why when which who not yet the and or there here near far hot "
              "cold engine oil please thanks show tell me us my our it's what's nearest fuel gas station "
              "petrol speed revs coolant mountain peak lake castle town village weather".split()),
    "de": set("ich wir du ist sind bin wie wo warum wann welche welcher welches wer nicht noch schon der die "
              "das den dem ein eine einen und oder gibt es hier nah weit heiss kalt motor bitte danke zeig "
              "sag mir mich uns tankstelle tanken drehzahl geschwindigkeit berg gipfel see burg dorf stadt "
              "wetter".split()),
}

# "Which mountain is that?": the peaks within this distance that look biggest
# from here, i.e. rise the most above you for how far away they are.
PEAKS_KM = 15

# What a question is about, tested in this order on the plain text (see _plain).
INTENTS = [
    ("oil", r"\boil\b|\boel"),
    ("coolant", r"coolant|water temp|engine temp|kuehl|wassertemp|motortemp"),
    ("warm", r"(engine|motor)\b.*\bwarm|\bwarm\b.*\b(engine|motor)|warmed up|operating temp|betriebstemp"
             r"|warm ?gefahren"),
    ("rpm", r"\brpm\b|\brevs?\b|drehzahl|\btouren|umdrehung"),
    ("speed", r"how fast|\bspeed(?! limit)|wie schnell|geschwindigkeit(?!sbegrenzung)|\btempo(?!limit)"),
    ("fuel", r"\bfuel|gas station|petrol|\brefuel|tankstelle|tanken|\bsprit|benzin|diesel"),
    ("peak", r"mountain|\bpeaks?\b|summit|\bberg|gipfel"),
    ("where", r"where (am i|are we|is this)|what (place|town|village) is this|\blocation\b"
              r"|wo (bin ich|sind wir|ist das)\b|welche[rs]? ort|standort"),
]


def detect_language(text, languages=LANGUAGES):
    """The language the text looks like, from `languages`; the first one when unsure."""
    lower = text.lower()
    words = re.findall(r"[a-zäöüß']+", lower)
    scores = {lang: sum(w in _WORDS.get(lang, ()) for w in words) for lang in languages}
    if "de" in scores:
        scores["de"] += len(re.findall(r"[äöüß]", lower))
    return max(languages, key=scores.get)  # ties: the first language


class Facts:
    """What he knows when a question comes: the car, where you are, and what is around."""

    def __init__(self, car, thresholds, location=None, place=None, places=(), pois=(), nearby_km=20,
                 local_time=None):
        self.car = car
        self.thresholds = thresholds
        self.location = location      # {"lat", "lon"}, or None before the first position
        self.place = place            # the places.json place you are in, or None
        self.places = places          # places.json
        self.pois = pois              # points of interest (poi.py)
        self.nearby_km = nearby_km
        self.local_time = local_time  # time.struct_time, or None
        self._measured = None         # every place and point as (item, metres, bearing), nearest first

    def around(self, kinds=None, limit=5, max_km=None):
        """[(item, metres, bearing)] nearest first, within nearby_km (or max_km): your places
        (kind "place") and the points of interest."""
        reach = (max_km or self.nearby_km) * 1000
        found = []
        for hit in self._all():
            if hit[1] > reach or len(found) == limit:
                break
            if not kinds or hit[0]["kind"] in kinds:
                found.append(hit)
        return found

    def named(self, question, limit=3):
        """Places and points of interest the question names, at any distance."""
        q = f" {_plain(question)} "
        return [hit for hit in self._all() if any(f" {part} " in q for part in _name_parts(hit[0]))][:limit]

    def _all(self):
        if self._measured is None:
            self._measured = []
            if self.location:
                lat, lon = self.location["lat"], self.location["lon"]
                items = [{"name": p["name"], "kind": "place", "lat": p["lat"], "lon": p["lon"]}
                         for p in self.places]
                self._measured = sorted(((item, distance_m(lat, lon, item["lat"], item["lon"]),
                                          bearing_deg(lat, lon, item["lat"], item["lon"]))
                                         for item in items + list(self.pois)), key=lambda hit: hit[1])
        return self._measured


def direct_answer(question, lang, facts):
    """An exact answer from the data, or None when the AI model should answer."""
    q = _plain(question)
    for intent, pattern in INTENTS:
        if re.search(pattern, q):
            return _ANSWERS[intent](facts, lang)
    return None


def messages(question, lang, facts):
    """The chat for the AI model: instructions with the facts, then the question."""
    return [{"role": "system", "content": SYSTEM[lang] + facts_text(facts, lang, question)},
            {"role": "user", "content": question}]


def facts_text(f, lang, question=""):
    de = lang == "de"
    lines = []
    if f.local_time and f.local_time.tm_year >= 2025:  # an unset clock says 1970
        lines.append(f"{'Uhrzeit' if de else 'Time'}: {f.local_time.tm_hour}:{f.local_time.tm_min:02d}.")
    lines.append(_car_line(f, lang))
    where = _where(f, lang)
    if where:
        lines.append(f"{'Wir sind' if de else 'We are'} {where}.")
    else:
        lines.append("Position unbekannt." if de else "Position unknown.")
    near = _nearby(f, question)
    if near:
        lines.append(("In der Nähe: " if de else "Nearby: ") + "; ".join(_describe(*hit, lang) for hit in near) + ".")
    if f.location and not f.pois:
        lines.append("Keine Kartendaten für die Gegend." if de else "No map data for the area.")
    return "\n".join(lines)


class Asker:
    """Sends questions to the AI model one at a time, on a worker thread.
    done(ask_id, text, error) is called from that thread when the answer is there."""

    def __init__(self, llm, done):
        self._llm = llm
        self._done = done
        self._jobs = queue.Queue()
        threading.Thread(target=self._run, name="asker", daemon=True).start()

    def ask(self, ask_id, chat, **options):
        self._jobs.put((ask_id, chat, options))

    def _run(self):
        while True:
            job = self._jobs.get()
            while not self._jobs.empty():  # only the newest question counts
                job = self._jobs.get_nowait()
            ask_id, chat, options = job
            try:
                self._done(ask_id, self._llm.chat(chat, **options), None)
            except Exception as e:  # the model being away must not stop the companion
                self._done(ask_id, None, e)


# ---- exact answers ------------------------------------------------------------

def _oil(f, lang):
    oil, warm = round(f.car["oil_c"]), f.thresholds.get("oil_warm_c", 80)
    if lang == "de":
        return f"Das Öl hat {oil} °C" + (", schön warm." if oil >= warm else
                                         f", noch kalt (warm ab {warm} °C). Lass es ruhig angehen.")
    return f"The oil is at {oil} °C" + (", nice and warm." if oil >= warm else
                                        f", still cold (warm from {warm} °C). Take it easy.")


def _coolant(f, lang):
    coolant, hot = round(f.car["coolant_c"]), f.thresholds.get("coolant_hot_c", 105)
    if lang == "de":
        return f"Das Kühlwasser hat {coolant} °C." + (" Das ist zu heiß!" if coolant >= hot else "")
    return f"The coolant is at {coolant} °C." + (" That's too hot!" if coolant >= hot else "")


def _warm(f, lang):
    oil, coolant, warm = round(f.car["oil_c"]), round(f.car["coolant_c"]), f.thresholds.get("oil_warm_c", 80)
    if oil >= warm:
        return (f"Ja, der Motor ist warm: Öl {oil} °C, Kühlwasser {coolant} °C." if lang == "de" else
                f"Yes, the engine is warm: oil {oil} °C, coolant {coolant} °C.")
    return (f"Noch nicht: Das Öl hat {oil} °C, warm ist es ab {warm} °C." if lang == "de" else
            f"Not yet: the oil is at {oil} °C, it's warm from {warm} °C.")


def _rpm(f, lang):
    rpm = round(f.car["rpm"])
    if not f.car.get("ignition") or rpm < 1:
        return "Der Motor ist aus." if lang == "de" else "The engine is off."
    return f"Der Motor dreht mit {rpm} U/min." if lang == "de" else f"The engine is at {rpm} rpm."


def _speed(f, lang):
    v = round(f.car["speed_kmh"])
    if v < 1:
        return "Wir stehen." if lang == "de" else "We're standing still."
    return f"Wir fahren {v} km/h." if lang == "de" else f"We're doing {v} km/h."


def _where_answer(f, lang):
    where = _where(f, lang)
    if not where:
        return NOT_LOCATED[lang]
    return f"Wir sind {where}." if lang == "de" else f"We're {where}."


def _fuel(f, lang):
    if not f.location:
        return NOT_LOCATED[lang]
    near = f.around(("fuel",), limit=1, max_km=max(f.nearby_km, 30))
    if not near:
        return NO_MAP[lang] if not f.pois else ("Ich kenne keine Tankstelle in der Nähe." if lang == "de" else
                                                 "I don't know a fuel station nearby.")
    item, m, bearing = near[0]
    if lang == "de":
        return f"Die nächste Tankstelle ist {_name(item, lang)}, {_direction(m, bearing, lang)}."
    return f"The nearest fuel station is {_name(item, lang)}, {_direction(m, bearing, lang)}."


def _peaks(f, lang):
    if not f.location:
        return NOT_LOCATED[lang]
    near = f.around(("peak",), limit=200, max_km=min(f.nearby_km, PEAKS_KM))
    if not near:
        return NO_MAP[lang] if not f.pois else ("Ich kenne hier keine Berge." if lang == "de" else
                                                 "I don't know any peaks around here.")
    ground = _ground(f)
    best = sorted(near, key=lambda hit: (ground - _ele(hit[0])) / max(hit[1], 300))[:2]
    parts = [f"{_name(item, lang)}{_height(item)}, {_direction(m, b, lang)}" for item, m, b in best]
    return ("Berge in der Nähe: " if lang == "de" else "Peaks nearby: ") + "; ".join(parts) + "."


def _ground(f):
    """About how high you are: the nearest village's elevation (later the phone's GPS)."""
    return next((_ele(item) for item, _, _ in f.around(SETTLEMENTS, limit=3, max_km=5) if _ele(item)), 0)


_ANSWERS = {"oil": _oil, "coolant": _coolant, "warm": _warm, "rpm": _rpm, "speed": _speed,
            "fuel": _fuel, "peak": _peaks, "where": _where_answer}


# ---- wording --------------------------------------------------------------------

def _car_line(f, lang):
    c = f.car
    if not c.get("ignition"):
        return "Auto: Zündung aus." if lang == "de" else "Car: ignition off."
    warm = c["oil_c"] >= f.thresholds.get("oil_warm_c", 80)
    if lang == "de":
        return (f"Auto: {round(c['speed_kmh'])} km/h, {round(c['rpm'])} U/min, Öl {round(c['oil_c'])} °C "
                f"({'warm' if warm else 'noch kalt'}), Kühlwasser {round(c['coolant_c'])} °C.")
    return (f"Car: {round(c['speed_kmh'])} km/h, {round(c['rpm'])} rpm, oil {round(c['oil_c'])} °C "
            f"({'warm' if warm else 'still cold'}), coolant {round(c['coolant_c'])} °C.")


def _where(f, lang):
    """Where you are, e.g. "in Kastelruth" or "1.2 km south of Seis"; None when unknown."""
    if not f.location:
        return None
    if f.place:
        return f"in {f.place['name']}"
    near = f.around(SETTLEMENTS, limit=1)
    if near:
        item, m, bearing = near[0]
        if m < 1000:
            return f"in {_name(item, lang)}"
        back = (bearing + 180) % 360  # from the village to you
        return f"{_direction(m, back, lang)} {'von' if lang == 'de' else 'of'} {_name(item, lang)}"
    lat, lon = (_num(f.location[k], lang, 4) for k in ("lat", "lon"))
    return f"bei {lat}, {lon}" if lang == "de" else f"at {lat}, {lon}"


def _nearby(f, question):
    """A short mix of what is around, plus what the question names, without repeats."""
    picks = (f.named(question) + f.around(SETTLEMENTS, 2) + f.around(("place",), 1) + f.around(("peak",), 2)
             + f.around(("pass", "lake", "castle", "attraction", "viewpoint"), 2) + f.around(("fuel",), 1))
    seen, out = set(), []
    for hit in picks:
        if hit[0]["name"] not in seen:
            seen.add(hit[0]["name"])
            out.append(hit)
    return out


def _describe(item, m, bearing, lang):
    """e.g. "Petz (peak, 2563 m) 5.1 km south-east"."""
    kind = KIND_WORDS[lang][item["kind"]]
    return f"{_name(item, lang)} ({kind}{_height(item, ', ')}) {_direction(m, bearing, lang)}"


def _height(item, prefix=" "):
    """The elevation of peaks and passes, e.g. " 2563 m"."""
    return f"{prefix}{round(_ele(item))} m" if _ele(item) and item["kind"] in ("peak", "pass") else ""


def _ele(item):
    ele = item.get("ele")
    return ele if isinstance(ele, (int, float)) and not isinstance(ele, bool) else 0


def _name(item, lang):
    """The name in the question's language when the map has it, else the first one:
    names in South Tyrol list every language ("Kastelruth - Ciastel - Castelrotto")."""
    if item["kind"] == "place":
        return item["name"]  # your own name for it
    return item.get(f"name_{lang}") or item.get("name_de") or item["name"].split(" - ")[0]


def _direction(m, bearing, lang):
    return f"{_distance(m, lang)} {COMPASS[lang][int((bearing + 22.5) // 45) % 8]}"


def _distance(m, lang):
    if m < 950:
        return f"{max(50, round(m / 50) * 50)} m"
    km = m / 1000
    return f"{_num(km, lang, 1 if km < 9.95 else 0)} km"


def _num(value, lang, digits=0):
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang == "de" else text


def _plain(text):
    """Lower case, umlauts spelled out, no accents: for matching words."""
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9/' ]+", " ", text)


def _name_parts(item):
    """The words a name can be asked by: "Kastelruth / Castelrotto" gives both halves."""
    names = {item["name"], item.get("name_de") or "", item.get("name_en") or ""}
    parts = {" ".join(_plain(part).split()) for name in names for part in re.split(r"\s[-/]\s|/", name)}
    return [p for p in parts if len(p) >= 4]
