import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from companion.config_store import NAMES
from companion.core import CONFIG_POLL_S, Companion
from tests import ROOT


class CompanionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name in NAMES:
            shutil.copy(ROOT / "config" / f"{name}.json", self.dir)
        self.sent = []
        self.now = 0.0
        self.brain = Companion(self.dir, lambda msg, to: self.sent.append((msg, to)),
                               clock=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def sent_of(self, kind):
        return [(msg, to) for msg, to in self.sent if msg["type"] == kind]

    def test_hello_gets_state_with_config_and_scene(self):
        self.brain.tick()
        self.brain.receive({"type": "hello", "client": "test"}, "tab1")
        self.brain.tick()
        ((state, to),) = self.sent_of("state")
        self.assertEqual(to, "tab1")
        self.assertEqual(state["scene"]["kind"], "eyes")
        self.assertEqual(set(state["config"]), set(NAMES))
        self.assertEqual(state["config_errors"], {})

    def test_play_with_a_mood_changes_scene_and_status(self):
        self.brain.tick()
        before = self.brain.scene
        self.brain.receive({"type": "play", "steps": [{"mood": "happy"}]})
        self.brain.tick()
        self.assertNotEqual(self.brain.scene, before)
        self.assertEqual(self.sent_of("scene")[-1][0]["scene"], self.brain.scene)
        self.assertEqual(self.sent_of("status")[-1][0]["mood"], "happy")

    def test_scene_is_only_sent_when_it_changes(self):
        for _ in range(5):
            self.brain.tick()
        self.assertEqual(len(self.sent_of("scene")), 1)

    def test_bad_messages_are_logged_not_fatal(self):
        for bad in ("nonsense", {"type": "no_such_type"}, {"type": "play", "steps": 5}):
            self.brain.receive(bad)
        self.brain.tick()
        levels = [msg["level"] for msg, _ in self.sent_of("log")]
        self.assertEqual(levels, ["warn", "warn", "error"])

    def test_config_edit_on_disk_applies_live(self):
        self.brain.tick()
        path = self.dir / "faces.json"
        faces = json.loads(path.read_text())
        faces["moods"]["neutral"]["color"] = "#FF0000"
        path.write_text(json.dumps(faces))
        os.utime(path, ns=(1, 1))  # a different timestamp, however fast the test runs
        self.now += CONFIG_POLL_S
        self.brain.tick()
        colors = {eye["color"] for eye in self.brain.scene["displays"][0]["shapes"]}
        self.assertEqual(colors, {"#FF0000"})
        self.assertEqual(self.sent_of("config")[-1][0]["name"], "faces")

    def test_broken_config_is_reported_and_face_stays(self):
        self.brain.tick()
        scene = self.brain.scene
        path = self.dir / "faces.json"
        path.write_text("{ broken")
        os.utime(path, ns=(1, 1))
        self.now += CONFIG_POLL_S
        self.brain.tick()
        ((err, _),) = self.sent_of("config_error")
        self.assertEqual((err["name"], err["source"]), ("faces", "last_good"))
        self.assertEqual(self.brain.scene, scene)


if __name__ == "__main__":
    unittest.main()
