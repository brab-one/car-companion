import base64
import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from companion.config_store import NAMES
from companion.core import CONFIG_POLL_S, Companion
from tests import ROOT

KASTELRUTH = {"lat": 46.567, "lon": 11.567}


class CompanionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "config").mkdir()
        for name in NAMES:
            shutil.copy(ROOT / "config" / f"{name}.json", self.dir / "config")
        shutil.copytree(ROOT / "assets" / "images", self.dir / "images")
        self.sent = []
        self.now = 0.0
        self.brain = Companion(self.dir / "config", lambda msg, to: self.sent.append((msg, to)),
                               images_dir=self.dir / "images", clock=lambda: self.now,
                               echo=lambda line: None)
        self.brain.tick()  # the simulated ignition starts on, so he wakes up

    def tearDown(self):
        self.tmp.cleanup()

    def run_for(self, seconds, dt=0.05):
        end = self.now + seconds
        while self.now < end:
            self.now = round(self.now + dt, 3)
            self.brain.tick()

    def send(self, **msg):
        self.brain.receive(msg, "tab1")
        self.run_for(0.05)

    def sent_of(self, kind):
        return [(msg, to) for msg, to in self.sent if msg["type"] == kind]

    def logs(self, level=None):
        return [m["text"] for m, _ in self.sent_of("log") if level in (None, m["level"])]

    def said(self):
        return [m["text"] for m, _ in self.sent_of("say")]

    def test_starts_without_problems(self):
        self.assertEqual(self.logs("warn") + self.logs("error"), [])
        self.assertIn("ignition on: waking up", self.logs())

    def test_hello_gets_the_whole_state(self):
        self.send(type="hello", client="test")
        ((state, to),) = self.sent_of("state")
        self.assertEqual(to, "tab1")
        self.assertEqual(set(state["config"]), set(NAMES))
        self.assertEqual(state["images"], ["geisler.png", "schlern.png"])
        self.assertIn("launch", state["scenarios"])

    def test_speed_picks_the_mood(self):
        for speed, mood in [(0, "happy"), (50, "neutral"), (95, "racing"), (3, "happy")]:
            self.send(type="sim_car", speed_kmh=speed)
            self.run_for(11)  # "fast" holds for 8 s, then the visor goes up
            self.assertEqual(self.brain.status["mood"], mood, f"at {speed} km/h")

    def test_visor_comes_down_from_90_kmh_and_up_8_s_after_slowing_down(self):
        self.run_for(3)  # finish waking up
        self.send(type="sim_car", speed_kmh=95)
        visors = []
        for _ in range(60):  # 3 s, watching the visor come down
            self.run_for(0.05)
            visors.append(self.brain.scene["displays"][0].get("visor"))
        down = [v["y"] for v in visors if v]
        self.assertGreater(max(down), 62)  # it bounces past its place ...
        self.assertEqual(down[-1], 62)     # ... and settles
        self.assertEqual(len({v["glint"] for v in visors if v}) > 5, True)  # the glint sweeps across
        self.assertEqual(self.brain.status["mood"], "racing")
        self.send(type="sim_car", speed_kmh=60)
        self.run_for(6)
        self.assertEqual((self.brain.status["mood"], self.brain.scene["displays"][0]["visor"]["y"]), ("racing", 62))
        self.run_for(5)  # 8 s hold, then "visor_up"
        self.assertNotIn("visor", self.brain.scene["displays"][0])
        self.assertEqual(self.brain.status["mood"], "neutral")
        animations = {m["animation"] for m, _ in self.sent_of("status")}
        self.assertTrue({"visor_down", "visor_up"} <= animations)

    def test_cold_oil_worries_him_while_driving(self):
        self.send(type="sim_car", oil_c=30, speed_kmh=50)
        self.run_for(1)
        self.assertEqual(self.brain.status["mood"], "worried")
        self.send(type="sim_car", speed_kmh=0)  # standing still comes first in rules.json
        self.run_for(1)
        self.assertEqual(self.brain.status["mood"], "happy")
        self.send(type="sim_car", coolant_c=110)  # warnings come before everything
        self.run_for(1)
        self.assertEqual((self.brain.status["mood"], self.brain.animator.idle["play"]), ("worried", ["nervous"]))

    def test_standing_still_means_looking_around(self):
        self.send(type="sim_car", speed_kmh=0)
        self.run_for(10)
        self.assertEqual(self.brain.animator.idle["play"], ["look_around"])
        self.assertIn("look_around", {m["animation"] for m, _ in self.sent_of("status")})

    def test_shaking_the_board_makes_him_angry(self):
        self.send(type="sim_car", speed_kmh=50)
        self.run_for(1)
        for i in range(20):  # samples as the sketch sends them
            self.brain.accel_sample(1.5 if i % 2 else -1.5, 0, 1)
        self.run_for(0.1)
        self.assertEqual(self.brain.status["mood"], "angry")
        self.assertIn("Modulino Movement: receiving data", self.logs())
        self.assertIn("Hey, stop shaking me!", self.said())
        self.run_for(5)  # no more samples: sensor gone, rule off after hold_s
        self.assertEqual(self.brain.status["mood"], "neutral")

    def test_shake_button_beats_standing_still(self):
        self.send(type="sim_car", speed_kmh=0)
        self.run_for(1)
        self.send(type="sim_motion", g=1.0, s=2)
        self.assertEqual((self.brain.status["mood"], self.brain.status["rules"]), ("angry", ["shaken", "stopped"]))
        self.run_for(5)
        self.assertEqual(self.brain.status["mood"], "happy")

    def test_ignition_off_sleeps_then_turns_the_display_off(self):
        self.send(type="sim_car", ignition=False)
        self.assertTrue(self.brain.status["asleep"])
        self.run_for(19)
        self.assertEqual(self.brain.scene["kind"], "eyes")
        self.run_for(2)
        self.assertEqual(self.brain.scene["kind"], "off")
        self.send(type="sim_car", ignition=True)
        self.assertEqual(self.brain.scene["kind"], "eyes")

    def test_entering_a_place_shows_its_picture_once_per_cooldown(self):
        self.send(type="location", **KASTELRUTH)
        self.assertEqual((self.brain.scene["kind"], self.brain.scene["image"]), ("image", "schlern.png"))
        self.assertIn("There's the Schlern.", self.said())
        self.run_for(8)
        self.assertEqual(self.brain.scene["kind"], "eyes")
        self.send(type="location", lat=46.7, lon=11.567)  # leave
        self.send(type="location", **KASTELRUTH)          # back, within cooldown_min
        self.assertEqual(self.brain.scene["kind"], "eyes")
        self.assertTrue(any("quiet for 60 more min" in t for t in self.logs()))

    def test_config_set_saves_and_applies(self):
        places = json.loads((ROOT / "config" / "places.json").read_text())
        places["places"][0]["radius_m"] = 500
        self.send(type="config_set", name="places", data=places)
        ((result, to),) = self.sent_of("config_result")
        self.assertEqual((result["ok"], result["errors"], to), (True, [], "tab1"))
        saved = json.loads((self.dir / "config" / "places.json").read_text())
        self.assertEqual(saved, places)
        self.assertEqual(self.sent_of("config")[-1][0]["name"], "places")

    def test_config_set_refuses_bad_data(self):
        before = (self.dir / "config" / "places.json").read_text()
        self.send(type="config_set", name="places", data={"places": [{"id": "x"}]})
        ((result, _),) = self.sent_of("config_result")
        self.assertFalse(result["ok"])
        self.assertIn("places.json: places.x.name: expected text, got null", result["errors"])
        self.assertEqual((self.dir / "config" / "places.json").read_text(), before)

    def test_image_put_checks_and_saves_pictures(self):
        png = (ROOT / "assets" / "images" / "schlern.png").read_bytes()
        self.send(type="image_put", name="mine.png", png_base64=base64.b64encode(png).decode())
        self.assertTrue(self.sent_of("image_result")[-1][0]["ok"])
        self.assertIn("mine.png", self.sent_of("images")[-1][0]["names"])
        small = png[:16] + struct.pack(">II", 64, 64) + png[24:]
        self.send(type="image_put", name="small.png", png_base64=base64.b64encode(small).decode())
        result = self.sent_of("image_result")[-1][0]
        self.assertEqual((result["ok"], result["error"]), (False, "the picture is 64 x 64, it must be 128 x 128"))

    def test_bad_messages_are_logged_not_fatal(self):
        self.sent.clear()
        for bad in ("nonsense", {"type": "no_such_type"}, {"type": "play", "steps": 5},
                    {"type": "location", "lat": "x"}):
            self.brain.receive(bad)
        self.run_for(0.05)
        self.assertEqual(len(self.logs("warn") + self.logs("error")), 4)

    def test_config_edit_on_disk_applies_live(self):
        self.send(type="sim_car", speed_kmh=50)
        self.run_for(4)
        path = self.dir / "config" / "faces.json"
        faces = json.loads(path.read_text())
        faces["moods"]["neutral"]["color"] = "#FF0000"
        path.write_text(json.dumps(faces))
        os.utime(path, ns=(1, 1))  # a different timestamp, however fast the test runs
        self.run_for(CONFIG_POLL_S + 0.5)
        colors = {eye["color"] for eye in self.brain.scene["displays"][0]["shapes"]}
        self.assertEqual(colors, {"#FF0000"})

    def test_broken_config_is_reported_and_face_stays(self):
        path = self.dir / "config" / "faces.json"
        path.write_text("{ broken")
        os.utime(path, ns=(1, 1))
        self.run_for(CONFIG_POLL_S + 0.1)
        ((err, _),) = self.sent_of("config_error")
        self.assertEqual((err["name"], err["source"]), ("faces", "last_good"))
        self.assertEqual(self.brain.scene["kind"], "eyes")

    def test_scene_is_only_sent_when_it_changes(self):
        self.run_for(5)
        scenes = [m["scene"] for m, _ in self.sent_of("scene")]
        self.assertTrue(all(a != b for a, b in zip(scenes, scenes[1:])))


if __name__ == "__main__":
    unittest.main()
