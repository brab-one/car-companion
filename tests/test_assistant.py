import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from companion import assistant, speech
from companion.assistant import Facts, detect_language, direct_answer, facts_text, messages
from companion.llm import LlmClient, clean
from companion.poi import Pois

CAR = {"ignition": True, "speed_kmh": 62.4, "rpm": 2400, "oil_c": 45, "coolant_c": 88}
THRESHOLDS = {"oil_warm_c": 80, "coolant_hot_c": 105}
PLACES = [{"id": "kastelruth", "name": "Kastelruth / Castelrotto", "lat": 46.567, "lon": 11.567}]
POIS = [
    {"name": "Seis am Schlern - Siusi allo Sciliar", "name_de": "Seis am Schlern", "kind": "village",
     "lat": 46.545, "lon": 11.567, "ele": 1004},
    {"name": "Santner", "kind": "peak", "lat": 46.511, "lon": 11.586, "ele": 2414},
    {"name": "Katzenlochbühel", "kind": "peak", "lat": 46.537, "lon": 11.551, "ele": 1162},
    {"name": "Eni", "kind": "fuel", "lat": 46.551, "lon": 11.560},
    {"name": "Bolzano - Bozen", "name_de": "Bozen", "kind": "city", "lat": 46.498, "lon": 11.354},
]
NEAR_SEIS = {"lat": 46.540, "lon": 11.570}


def facts(location=NEAR_SEIS, pois=POIS, car=CAR, place=None):
    return Facts(dict(car), THRESHOLDS, location, place, PLACES, pois, 20, time.localtime())


class LanguageTest(unittest.TestCase):
    def test_english_and_german_are_told_apart(self):
        for text, lang in [("How warm is the oil?", "en"), ("Wie warm ist das Öl?", "de"),
                           ("Wo ist die nächste Tankstelle?", "de"), ("Where are we?", "en"),
                           ("Gibt es hier einen See?", "de"), ("Is there a lake here?", "en")]:
            self.assertEqual(detect_language(text), lang, text)

    def test_unsure_means_the_first_language(self):
        self.assertEqual(detect_language("Kastelruth?", ["de", "en"]), "de")
        self.assertEqual(detect_language("Where are we?", ["de"]), "de")


class DirectAnswerTest(unittest.TestCase):
    def ask(self, question, f=None):
        return direct_answer(question, detect_language(question), f or facts())

    def test_car_questions(self):
        self.assertEqual(self.ask("How warm is the oil?"),
                         "The oil is at 45 °C, still cold (warm from 80 °C). Take it easy.")
        self.assertEqual(self.ask("Wie warm ist das Öl?"),
                         "Das Öl hat 45 °C, noch kalt (warm ab 80 °C). Lass es ruhig angehen.")
        self.assertEqual(self.ask("Is the engine warm yet?"), "Not yet: the oil is at 45 °C, it's warm from 80 °C.")
        hot = facts(car={**CAR, "oil_c": 95, "coolant_c": 108})
        self.assertEqual(self.ask("Ist der Motor warm?", hot), "Ja, der Motor ist warm: Öl 95 °C, Kühlwasser 108 °C.")
        self.assertEqual(self.ask("coolant temperature?", hot), "The coolant is at 108 °C. That's too hot!")
        self.assertEqual(self.ask("Wie hoch ist die Drehzahl?"), "Der Motor dreht mit 2400 U/min.")
        self.assertEqual(self.ask("How fast are we going?"), "We're doing 62 km/h.")
        parked = facts(car={**CAR, "ignition": False, "speed_kmh": 0, "rpm": 0})
        self.assertEqual(self.ask("Wie schnell fahren wir?", parked), "Wir stehen.")
        self.assertEqual(self.ask("What are the revs?", parked), "The engine is off.")

    def test_where_you_are(self):
        self.assertEqual(self.ask("Wo bin ich?"), "Wir sind in Seis am Schlern.")  # 600 m from the village
        away = facts(location={"lat": 46.525, "lon": 11.567})
        self.assertEqual(self.ask("Where are we?", away), "We're 2.2 km south of Seis am Schlern.")
        self.assertEqual(self.ask("Wo sind wir?", facts(place=PLACES[0])), "Wir sind in Kastelruth / Castelrotto.")
        self.assertEqual(self.ask("Where am I?", facts(location=None)), assistant.NOT_LOCATED["en"])
        nowhere = facts(location={"lat": 47.0, "lon": 12.5}, pois=[])
        self.assertEqual(self.ask("Wo bin ich?", nowhere), "Wir sind bei 47,0000, 12,5000.")

    def test_fuel_and_peaks_come_from_the_map(self):
        self.assertEqual(self.ask("Where is the nearest gas station?"),
                         "The nearest fuel station is Eni, 1.4 km north-west.")
        self.assertEqual(self.ask("Wo kann ich tanken?"), "Die nächste Tankstelle ist Eni, 1,4 km nordwestlich.")
        self.assertEqual(self.ask("Which mountain is that?"),  # the big one, not the hill next to you
                         "Peaks nearby: Santner 2414 m, 3.4 km south; Katzenlochbühel 1162 m, 1.5 km west.")
        self.assertEqual(self.ask("Tankstelle?", facts(pois=[])), assistant.NO_MAP["de"])

    def test_height_and_distance_of_places_on_the_map(self):
        self.assertEqual(self.ask("How high is the Santner?"), "Santner is 2414 m high, 3.4 km south of here.")
        self.assertEqual(self.ask("Wie weit ist es nach Bozen?"), "Bozen ist 17 km westlich von hier.")
        self.assertEqual(self.ask("Wie hoch liegt Bozen?"), "Ich weiß nicht, wie hoch Bozen liegt.")
        self.assertEqual(self.ask("How far is the nearest fuel station?"),  # names no place: the fuel answer
                         "The nearest fuel station is Eni, 1.4 km north-west.")

    def test_other_questions_are_for_the_ai_model(self):
        for question in ("Tell me about Kastelruth", "What is the speed limit?", "How high is Mount Everest?"):
            self.assertIsNone(self.ask(question), question)


class NavigationTest(unittest.TestCase):
    def nav(self, question):
        return assistant.navigation(question, detect_language(question), facts())

    def test_places_he_knows_go_by_their_coordinates(self):
        dest, answer = self.nav("Navigate to Bozen")
        self.assertEqual((dest["name"], dest["lat"], dest["lon"], answer),
                         ("Bozen", 46.498, 11.354, "Starting navigation to Bozen on your phone."))
        self.assertIn("destination=46.498%2C11.354&travelmode=driving&dir_action=navigate", dest["url"])
        dest, answer = self.nav("Fahr mich zur nächsten Tankstelle")
        self.assertEqual((dest["name"], answer), ("Eni", "Ich starte die Navigation auf deinem Handy: Eni."))

    def test_other_places_go_to_google_maps_by_name(self):
        dest, answer = self.nav("Take me to Munich airport please")
        self.assertEqual((dest, answer), ({"name": "Munich airport", "query": "Munich airport",
                                           "url": "https://www.google.com/maps/dir/?api=1&destination=Munich+airport"
                                                  "&travelmode=driving&dir_action=navigate"},
                                          "Starting navigation to Munich airport on your phone."))
        self.assertEqual(self.nav("Bring mich nach Hause")[0]["query"], "Home")  # as saved in Google Maps
        self.assertEqual(self.nav("Take me home")[1], "Starting navigation home on your phone.")

    def test_other_questions_are_not_navigation(self):
        for question in ("How far is Bozen?", "What is the speed limit?", "Where are we?"):
            self.assertIsNone(self.nav(question), question)


class FactsTest(unittest.TestCase):
    def test_the_model_hears_only_what_the_question_is_about(self):
        self.assertEqual(facts_text(facts(), "de", "Wie weit ist es nach Bozen?"),
                         "Wir sind in Seis am Schlern.\nOrte: Bozen: Stadt, 17 km westlich.")
        self.assertEqual(facts_text(facts(), "en", "How high is the Santner?"),
                         "We are in Seis am Schlern.\nPlaces: Santner: peak, 2414 m high, 3.4 km south.")
        self.assertIn("Places: Eni: fuel station, 1.4 km north-west.", facts_text(facts(), "en", "Cheap petrol here?"))
        self.assertIn("Car: 62 km/h, 2400 rpm, oil 45 °C (still cold), coolant 88 °C.",
                      facts_text(facts(), "en", "Is the car ok?"))
        anything = facts_text(facts(), "en", "Tell me something nice")  # a little of everything around
        self.assertIn("Seis am Schlern: village, 600 m north", anything)
        self.assertIn("Kastelruth / Castelrotto: one of your places", facts_text(facts(location={"lat": 46.560,
                                                                                               "lon": 11.567}), "en"))
        self.assertIn("No map data", facts_text(facts(pois=[]), "en"))

    def test_the_chat_has_instructions_facts_and_the_question(self):
        chat = messages("Is the Santner hard to climb?", "en", facts())
        self.assertEqual([m["role"] for m in chat], ["system", "user"])
        self.assertEqual(chat[0]["content"], assistant.SYSTEM["en"])  # the same every time
        self.assertEqual(chat[1]["content"], "Facts:\nWe are in Seis am Schlern.\n"
                                             "Places: Santner: peak, 2414 m high, 3.4 km south.\n\n"
                                             "Question: Is the Santner hard to climb?")

    def test_the_time_is_answered_from_the_clock(self):
        self.assertRegex(direct_answer("What time is it?", "en", facts()), r"^It's \d+:\d\d\.$")
        unset = facts()
        unset.local_time = time.gmtime(0)  # 1970: the board's clock was never set
        self.assertEqual(direct_answer("Wie spät ist es?", "de", unset), "Ich weiß die Uhrzeit nicht.")


class LlmTest(unittest.TestCase):
    def test_answers_are_cleaned_up(self):
        self.assertEqual(clean("<think>hmm, the oil...</think>\n**It is warm.**"), "It is warm.")
        self.assertEqual(clean("<think>still thinking when the tokens ran out"), "")
        long = "One sentence here. " * 40
        self.assertTrue(clean(long).endswith("here.") and len(clean(long)) <= 400)

    def test_client_talks_to_an_openai_compatible_server(self):
        seen = []

        class Server(BaseHTTPRequestHandler):
            def do_GET(self):
                self.reply({"data": [{"id": "qwen-test"}]})

            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.reply({"choices": [{"message": {"content": "<think></think> Es ist **warm**."}}]})

            def reply(self, data):
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = LlmClient(f"http://127.0.0.1:{server.server_port}/v1")
            answer = client.chat([{"role": "user", "content": "Ist es warm?"}], max_tokens=50, timeout=5)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(answer, "Es ist warm.")
        self.assertEqual((seen[0]["model"], seen[0]["max_tokens"], seen[0]["chat_template_kwargs"], seen[0]["id_slot"]),
                         ("qwen-test", 50, {"enable_thinking": False}, 0))

    def test_no_server_is_a_clear_error(self):
        with self.assertRaisesRegex(ConnectionError, "no AI model at http://127.0.0.1:9/v1"):
            LlmClient("http://127.0.0.1:9/v1").chat([], timeout=2)


class PoiTest(unittest.TestCase):
    def test_points_are_read_checked_and_read_again_when_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "poi.json"
            pois = Pois(path)
            self.assertEqual(pois.all(), [])  # no file: nothing known, no error
            path.write_text(json.dumps({"pois": POIS + [{"name": "x", "kind": "spaceport", "lat": 1, "lon": 2}]}))
            self.assertEqual([p["name"] for p in pois.all()], [p["name"] for p in POIS])
            path.write_text("{ broken")
            os.utime(path, ns=(1, 1))
            self.assertEqual((pois.all(), pois.error[:9]), ([], "poi.json:"))


class PagesTest(unittest.TestCase):
    def test_a_long_answer_is_split_into_bubbles(self):
        text = "The nearest fuel station is Eni, 1.2 km west. The Santner is 3.6 km south-east, at 2414 m."
        pages = speech.pages(text)
        self.assertEqual(len(pages), 2)
        self.assertEqual(" ".join(pages), text)
        self.assertTrue(all(len(speech.wrap(page)) <= speech.MAX_LINES and "..." not in page for page in pages))


if __name__ == "__main__":
    unittest.main()
