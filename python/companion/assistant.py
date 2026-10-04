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
import time
import unicodedata
import urllib.parse

from .geofence import distance_m
from .poi import SETTLEMENTS, bearing_deg

LANGUAGES = ("en", "de")
UNKNOWN = {"en": "I can't answer that yet.", "de": "Das kann ich noch nicht beantworten."}
NO_MODEL = {"en": "Sorry, I can't think right now.", "de": "Tut mir leid, ich kann gerade nicht nachdenken."}
NOT_LOCATED = {"en": "I don't know where we are yet.", "de": "Ich weiß noch nicht, wo wir sind."}
NO_MAP = {"en": "I have no map of this area yet.", "de": "Ich habe noch keine Karte von dieser Gegend."}
ASLEEP = {"en": "I'm asleep. Turn the ignition on first.", "de": "Ich schlafe. Mach zuerst die Zündung an."}
SWITCHED_OFF = {"en": "Questions are switched off (assistant.enabled in settings.json).",
                "de": "Fragen sind ausgeschaltet (assistant.enabled in settings.json)."}

# Short on purpose: on the board the AI model reads about 10 tokens a second, so
# it only gets the facts a question is about (facts_text). The instructions come
# first and never change, so the model can skip reading them again.
SYSTEM = {
    "en": "You are a little companion on a car's dashboard. Answer in English, in one short sentence that "
          "names the places. Use only the facts given with the question; if they don't answer it, say you "
          "don't know.",
    "de": "Du bist ein kleiner Begleiter auf dem Armaturenbrett eines Autos. Antworte auf Deutsch, in einem "
          "kurzen Satz, und nenne die Orte beim Namen. Verwende nur die Fakten bei der Frage; wenn sie die "
          "Frage nicht beantworten, sag, dass du es nicht weißt.",
}
SLOTS = {"en": 0, "de": 1}  # one slot of the model's server per language keeps its instructions read

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
              "petrol speed revs coolant mountain peak lake castle town village weather navigate take drive "
              "directions to".split()),
    "de": set("ich wir du ist sind bin wie wo warum wann welche welcher welches wer nicht noch schon der die "
              "das den dem ein eine einen und oder gibt es hier nah weit heiss kalt motor bitte danke zeig "
              "sag mir mich uns tankstelle tanken drehzahl geschwindigkeit berg gipfel see burg dorf stadt "
              "wetter navigiere fahr fahre bring bringe nach zum zur hause".split()),
}

# "Which mountain is that?": the peaks within this distance that look biggest
# from here, i.e. rise the most above you for how far away they are.
PEAKS_KM = 15

# Words in a question -> the kinds of places the AI model hears about (plain text, see _plain).
TOPICS = [
    (("castle",), r"castle|ruin|\bburg|schloss|ruine"),
    (("lake",), r"\blakes?\b|\bsee\b|\bseen\b|weiher"),
    (("pass",), r"\bpass(es)?\b|\bjoch|paesse"),
    (SETTLEMENTS, r"village|\btowns?\b|\bcity\b|\bdorf|\bort\b|\borte\b|stadt"),
    (("peak",), r"mountain|\bpeaks?\b|summit|\bberg|gipfel|kofel|spitze"),
    (("viewpoint",), r"\bview|aussicht"),
    (("attraction", "castle", "viewpoint"), r"sight|visit|interesting|worth|sehenswert|besichtig|anschauen"),
    (("charging",), r"charg|\blade|electric|strom"),
    (("fuel",), r"\bfuel|\bgas\b|petrol|tank|sprit|benzin|diesel"),
]
CAR_WORDS = r"\bcar\b|engine|\boil\b|coolant|speed|fast|\brpm|\bdriv|\bauto\b|motor|\boel|kuehl|schnell|fahr"
TIME_WORDS = r"\btime\b|clock|\blate\b|\buhr|spaet"

# What a question is about, tested in this order on the plain text (see _plain).
INTENTS = [
    ("oil", r"\boil\b|\boel"),
    ("coolant", r"coolant|water temp|engine temp|kuehl|wassertemp|motortemp"),
    ("warm", r"(engine|motor)\b.*\bwarm|\bwarm\b.*\b(engine|motor)|warmed up|operating temp|betriebstemp"
             r"|warm ?gefahren"),
    ("rpm", r"\brpm\b|\brevs?\b|drehzahl|\btouren|umdrehung"),
    ("height", r"how high|how tall|elevation|altitude|wie hoch|hoehe"),  # of a place the question names
    ("distance", r"how far|distance|wie weit|entfern"),
    ("speed", r"how fast|\bspeed(?! limit)|wie schnell|geschwindigkeit(?!sbegrenzung)|\btempo(?!limit)"),
    ("fuel", r"\bfuel|gas station|petrol|\brefuel|tankstelle|tanken|\bsprit|benzin|diesel"),
    ("peak", r"mountain|\bpeaks?\b|summit|\bberg|gipfel"),
    ("where", r"where (am i|are we|is this)|what (place|town|village) is this|\blocation\b"
              r"|wo (bin ich|sind wir|ist das)\b|welche[rs]? ort|standort"),
    ("time", r"what time|time is it|wie spaet|wieviel uhr|wie viel uhr|\buhrzeit"),
    ("car", r"what (car|vehicle)|which car|car model|kind of car|what am i driving|welche[sn]? auto"
            r"|was fuer ein auto|automarke|welche[sn]? fahrzeug|was fahre ich"),
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
                 local_time=None, car_name=""):
        self.car = car
        self.car_name = car_name      # e.g. "Subaru BRZ" (settings: assistant.car)
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

    def find(self, text, limit=1):
        """Places and points of interest the text names, the nearest first when the
        position is known; for navigation, which needs no position."""
        if self.location:
            return [hit[0] for hit in self.named(text, limit)]
        q = f" {_plain(text)} "
        return [item for item in self._items() if any(f" {part} " in q for part in _name_parts(item))][:limit]

    def _items(self):
        return [{"name": p["name"], "kind": "place", "lat": p["lat"], "lon": p["lon"]} for p in self.places] \
            + list(self.pois)

    def _all(self):
        if self._measured is None:
            self._measured = []
            if self.location:
                lat, lon = self.location["lat"], self.location["lon"]
                self._measured = sorted(((item, distance_m(lat, lon, item["lat"], item["lon"]),
                                          bearing_deg(lat, lon, item["lat"], item["lon"]))
                                         for item in self._items()), key=lambda hit: hit[1])
        return self._measured


# "Navigate to Bozen", "Fahr mich zur nächsten Tankstelle": the words after these are the destination.
NAVIGATE = re.compile(
    r"\b(?:navigate|navigation|directions|route|take|drive|bring|guide|get|go)\s+(?:me\s+|us\s+)?(?:to|towards)\s+"
    r"(?P<en>.+)"
    r"|\b(?:navigier\w*|navigation|fahr\w*|bring\w*|führ\w*|route|wie komme ich|lass uns)\s+(?:mich\s+|uns\s+)?"
    r"(?:nach|zu|zum|zur|in die|ins|in den|an den|auf den)\s+(?P<de>.+)"
    r"|\b(?:navigate|take|drive|bring|get|go)\s+(?:me\s+|us\s+)?(?P<home>home)\b", re.IGNORECASE)
NEAREST = [(("fuel",), r"\bfuel|\bgas\b|petrol|tankstelle|tanken", {"en": "gas station", "de": "Tankstelle"}),
           (("charging",), r"charg|ladestation|\blade", {"en": "charging station", "de": "Ladestation"})]
HOME = r"^(home|my home|hause|zuhause|daheim)$"


def navigation(question, lang, facts):
    """For "navigate to ...": (destination, answer), where destination is what the
    `navigate` message carries (PROTOCOL.md); None for any other question."""
    m = NAVIGATE.search(question)
    if not m:
        return None
    wanted = re.sub(r"^(the|der|die|das|dem|den)\s+|[\s.!?]+$|\s+(please|bitte)$", "",
                    (m["en"] or m["de"] or m["home"]).strip(), flags=re.IGNORECASE)
    plain = _plain(wanted).strip()
    dest = None
    for kinds, words, query in NEAREST:  # the nearest one, if he knows it; Maps finds one otherwise
        if re.search(words, plain):
            near = facts.around(kinds, limit=1, max_km=60)
            dest = _destination(near[0][0], lang) if near else {"name": query[lang], "query": query[lang]}
    if dest is None and re.search(HOME, plain):
        dest = {"name": "Zuhause" if lang == "de" else "home", "query": "Home"}  # Home as saved in Google Maps
    if dest is None:
        found = facts.find(wanted)  # by the name you used for it, where he knows it
        dest = {**_destination(found[0], lang), "name": wanted} if found else {"name": wanted, "query": wanted}
    target = f"{dest['lat']},{dest['lon']}" if "lat" in dest else dest["query"]
    dest["url"] = "https://www.google.com/maps/dir/?api=1&" + urllib.parse.urlencode(
        {"destination": target, "travelmode": "driving", "dir_action": "navigate"})
    name = dest["name"]
    if lang == "de":  # no "nach", "zu", "zum": which one fits depends on the place
        return dest, f"Ich starte die Navigation auf deinem Handy: {name}."
    return dest, "Starting navigation home on your phone." if dest.get("query") == "Home" else \
        f"Starting navigation to {name} on your phone."


def _destination(item, lang):
    return {"name": _name(item, lang), "lat": item["lat"], "lon": item["lon"]}


def direct_answer(question, lang, facts):
    """An exact answer from the data, or None when the AI model should answer."""
    q = _plain(question)
    for intent, pattern in INTENTS:
        if re.search(pattern, q):
            answer = _ANSWERS[intent](facts, lang, question)
            if answer:
                return answer
    return None


def messages(question, lang, facts):
    """The chat for the AI model: the instructions (always the same, so the model can
    skip reading them again), then the facts right before the question, where a small
    model pays most attention."""
    label = ("Fakten", "Frage") if lang == "de" else ("Facts", "Question")
    return [{"role": "system", "content": SYSTEM[lang]},
            {"role": "user", "content": f"{label[0]}:\n{facts_text(facts, lang, question)}\n\n{label[1]}: {question}"}]


def facts_text(f, lang, question=""):
    """The facts for the AI model: where you are, and only what the question is about."""
    de = lang == "de"
    q = _plain(question)
    where = _where(f, lang)
    lines = [f"{'Wir sind' if de else 'We are'} {where}." if where else
             ("Position unbekannt." if de else "Position unknown.")]
    picks = f.named(question, 2) + [hit for kinds, words in TOPICS if re.search(words, q)
                                    for hit in f.around(kinds, 2)]
    if not picks and not re.search(CAR_WORDS + "|" + TIME_WORDS, q):
        picks = _nearby(f)  # nothing particular: a little of everything around
    seen, places = set(), []
    for item, m, bearing in picks:
        if item["name"] not in seen:
            seen.add(item["name"])
            places.append(_describe(item, m, bearing, lang))
    if places:
        lines.append(("Orte: " if de else "Places: ") + "; ".join(places) + ".")
    if f.location and not f.pois:
        lines.append("Keine Kartendaten für die Gegend." if de else "No map data for the area.")
    if re.search(CAR_WORDS, q):
        lines.append(_car_line(f, lang))
    if re.search(TIME_WORDS, q) and _clock_set(f):
        lines.append(f"{'Uhrzeit' if de else 'Time'}: {f.local_time.tm_hour}:{f.local_time.tm_min:02d}.")
    return "\n".join(lines)


class Asker:
    """Sends questions to the AI model one at a time, on a worker thread.
    done(ask_id, text, error) is called from that thread when the answer is there.
    warm_up: languages to have the model load and read the instructions for first,
    so the first question after a start does not wait for that."""

    WARM_UP_TRIES = 6     # the model's server may still be starting
    WARM_UP_WAIT_S = 10

    def __init__(self, llm, done, warm_up=()):
        self._llm = llm
        self._done = done
        self._jobs = queue.Queue()
        self.warmed_up = threading.Event()
        threading.Thread(target=self._run, args=(tuple(warm_up),), name="asker", daemon=True).start()

    def ask(self, ask_id, chat, **options):
        self._jobs.put((ask_id, chat, options))

    def _warm_up(self, languages):
        for lang in languages:
            chat = [{"role": "system", "content": SYSTEM[lang]}, {"role": "user", "content": "Hi"}]
            for _ in range(self.WARM_UP_TRIES):
                try:
                    self._llm.chat(chat, max_tokens=1, timeout=120, slot=SLOTS[lang])
                    break
                except Exception:  # not up yet; a question would load it later anyway
                    time.sleep(self.WARM_UP_WAIT_S)
        self.warmed_up.set()

    def _run(self, warm_up):
        self._warm_up(warm_up)
        while True:
            ask_id, chat, options = self._jobs.get()  # one after the other: every question gets its answer
            try:
                self._done(ask_id, self._llm.chat(chat, **options), None)
            except Exception as e:  # the model being away must not stop the companion
                self._done(ask_id, None, e)


# ---- exact answers ------------------------------------------------------------

def _oil(f, lang, question=""):
    oil, warm = round(f.car["oil_c"]), f.thresholds.get("oil_warm_c", 80)
    if lang == "de":
        return f"Das Öl hat {oil} °C" + (", schön warm." if oil >= warm else
                                         f", noch kalt (warm ab {warm} °C). Lass es ruhig angehen.")
    return f"The oil is at {oil} °C" + (", nice and warm." if oil >= warm else
                                        f", still cold (warm from {warm} °C). Take it easy.")


def _coolant(f, lang, question=""):
    coolant, hot = round(f.car["coolant_c"]), f.thresholds.get("coolant_hot_c", 105)
    if lang == "de":
        return f"Das Kühlwasser hat {coolant} °C." + (" Das ist zu heiß!" if coolant >= hot else "")
    return f"The coolant is at {coolant} °C." + (" That's too hot!" if coolant >= hot else "")


def _warm(f, lang, question=""):
    oil, coolant, warm = round(f.car["oil_c"]), round(f.car["coolant_c"]), f.thresholds.get("oil_warm_c", 80)
    if oil >= warm:
        return (f"Ja, der Motor ist warm: Öl {oil} °C, Kühlwasser {coolant} °C." if lang == "de" else
                f"Yes, the engine is warm: oil {oil} °C, coolant {coolant} °C.")
    return (f"Noch nicht: Das Öl hat {oil} °C, warm ist es ab {warm} °C." if lang == "de" else
            f"Not yet: the oil is at {oil} °C, it's warm from {warm} °C.")


def _rpm(f, lang, question=""):
    rpm = round(f.car["rpm"])
    if not f.car.get("ignition") or rpm < 1:
        return "Der Motor ist aus." if lang == "de" else "The engine is off."
    return f"Der Motor dreht mit {rpm} U/min." if lang == "de" else f"The engine is at {rpm} rpm."


def _speed(f, lang, question=""):
    v = round(f.car["speed_kmh"])
    if v < 1:
        return "Wir stehen." if lang == "de" else "We're standing still."
    return f"Wir fahren {v} km/h." if lang == "de" else f"We're doing {v} km/h."


def _where_answer(f, lang, question=""):
    where = _where(f, lang)
    if not where:
        return NOT_LOCATED[lang]
    return f"Wir sind {where}." if lang == "de" else f"We're {where}."


def _fuel(f, lang, question=""):
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


def _peaks(f, lang, question=""):
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


def _time(f, lang, question=""):
    if not _clock_set(f):
        return "Ich weiß die Uhrzeit nicht." if lang == "de" else "I don't know the time."
    t = f"{f.local_time.tm_hour}:{f.local_time.tm_min:02d}"
    return f"Es ist {t} Uhr." if lang == "de" else f"It's {t}."


def _height_of(f, lang, question):
    named = f.named(question, 1)
    if not named:
        return None  # not about a place on the map: the AI model may know
    item, m, bearing = named[0]
    name, away = _name(item, lang), _direction(m, bearing, lang)
    if not _ele(item):
        return (f"Ich weiß nicht, wie hoch {name} liegt." if lang == "de" else
                f"I don't know how high {name} is.")
    if lang == "de":
        return f"{name} ist {round(_ele(item))} m hoch, {away} von hier."
    return f"{name} is {round(_ele(item))} m high, {away} of here."


def _distance_to(f, lang, question):
    named = f.named(question, 1)
    if not named:
        return None  # e.g. "how far is the next fuel station": the other answers know
    item, m, bearing = named[0]
    away = _direction(m, bearing, lang)
    return f"{_name(item, lang)} ist {away} von hier." if lang == "de" else f"{_name(item, lang)} is {away} of here."


def _car_name(f, lang, question=""):
    if not f.car_name:
        return None  # nobody told him: the AI model will say it does not know
    return f"Wir sitzen in einem {f.car_name}." if lang == "de" else f"We're in a {f.car_name}."


def _clock_set(f):
    return f.local_time is not None and f.local_time.tm_year >= 2025  # an unset clock says 1970


def _ground(f):
    """About how high you are: the nearest village's elevation (later the phone's GPS)."""
    return next((_ele(item) for item, _, _ in f.around(SETTLEMENTS, limit=3, max_km=5) if _ele(item)), 0)


_ANSWERS = {"oil": _oil, "coolant": _coolant, "warm": _warm, "rpm": _rpm, "speed": _speed,
            "fuel": _fuel, "peak": _peaks, "where": _where_answer, "time": _time,
            "height": _height_of, "distance": _distance_to, "car": _car_name}


# ---- wording --------------------------------------------------------------------

def _car_line(f, lang):
    c, de = f.car, lang == "de"
    label = ("Auto" if de else "Car") + (f" ({f.car_name})" if f.car_name else "")
    if not c.get("ignition"):
        return f"{label}: {'Zündung aus' if de else 'ignition off'}."
    warm = c["oil_c"] >= f.thresholds.get("oil_warm_c", 80)
    if de:
        return (f"{label}: {round(c['speed_kmh'])} km/h, {round(c['rpm'])} U/min, Öl {round(c['oil_c'])} °C "
                f"({'warm' if warm else 'noch kalt'}), Kühlwasser {round(c['coolant_c'])} °C.")
    return (f"{label}: {round(c['speed_kmh'])} km/h, {round(c['rpm'])} rpm, oil {round(c['oil_c'])} °C "
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


def _nearby(f):
    """A little of everything around."""
    return (f.around(SETTLEMENTS, 1) + f.around(("place",), 1, max_km=3) + f.around(("peak",), 2)
            + f.around(("pass", "lake", "castle", "attraction", "viewpoint"), 1) + f.around(("fuel",), 1))


def _describe(item, m, bearing, lang):
    """Spelled out for a small model, e.g. "Santner: peak, 2414 m high, 4.6 km south"."""
    high = f", {round(_ele(item))} m {'hoch' if lang == 'de' else 'high'}" if _height(item) else ""
    return f"{_name(item, lang)}: {KIND_WORDS[lang][item['kind']]}{high}, {_direction(m, bearing, lang)}"


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
