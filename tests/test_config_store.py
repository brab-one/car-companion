import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from companion.config_store import NAMES, ConfigStore
from companion.jsonfile import dumps_compact, write_text_atomic
from companion.validate import check, cross_check
from tests import ROOT

CONFIG = ROOT / "config"
IMAGES = sorted(p.name for p in (ROOT / "assets" / "images").glob("*.png"))


class ConfigStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name in NAMES:
            shutil.copy(CONFIG / f"{name}.json", self.dir)
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def store(self):
        s = ConfigStore(self.dir, log=lambda *entry: self.logs.append(entry))
        s.load_all()
        return s

    def write(self, name, text):
        """Change a file and make sure its timestamp changes too, as a real edit would."""
        path = self.dir / name
        old = path.stat().st_mtime_ns
        path.write_text(text)
        os.utime(path, ns=(old + 10**9, old + 10**9))

    def test_shipped_config_files_are_valid_and_fit_together(self):
        data = {}
        for name in NAMES:
            data[name], errors = check(name, json.loads((CONFIG / f"{name}.json").read_text()))
            self.assertEqual(errors, [], name)
        self.assertEqual(cross_check(data, IMAGES), [])

    def test_good_file_is_used_and_kept(self):
        s = self.store()
        self.assertEqual(set(s.source.values()), {"file"})
        self.assertTrue((self.dir / ".good" / "faces.json").exists())

    def test_save_checks_then_writes_readable_json(self):
        s = self.store()
        places = json.loads((CONFIG / "places.json").read_text())
        places["places"][0]["radius_m"] = 500
        self.assertEqual(s.save("places", places), [])
        text = (self.dir / "places.json").read_text()
        self.assertEqual((json.loads(text), s.data["places"]), (places, places))
        self.assertLess(len(text.splitlines()), 10)  # one line per place, not one per value
        self.assertEqual(s.poll(), [])  # what was just saved is not reloaded
        errors = s.save("places", {"places": "none"})
        self.assertEqual(errors, ["places.json: places: expected a list"])
        self.assertEqual(json.loads((self.dir / "places.json").read_text()), places)

    def test_compact_json_round_trips(self):
        data = {"a": [1, 2], "b": {"c": "x" * 120, "d": None}, "e": []}
        self.assertEqual(json.loads(dumps_compact(data)), data)

    def test_broken_file_falls_back_to_last_good_copy(self):
        self.store()  # saves the good copies
        self.write("faces.json", '{"moods": ')
        s = self.store()
        self.assertEqual(s.source["faces"], "last_good")
        self.assertIn("invalid JSON at line 1, column", s.errors["faces"][0])
        self.assertIn("happy", s.data["faces"]["moods"])

    def test_broken_file_without_good_copy_uses_defaults(self):
        self.write("faces.json", "[]")
        s = self.store()
        self.assertEqual(s.source["faces"], "defaults")
        self.assertEqual(s.errors["faces"], ["faces.json: file: expected an object {...}, got []"])
        self.assertEqual(list(s.data["faces"]["moods"]), ["neutral"])

    def test_poll_reloads_changes_and_keeps_running_version_on_errors(self):
        s = self.store()
        self.assertEqual(s.poll(), [])
        self.write("faces.json", '{"oops": 1}')
        self.assertEqual(s.poll(), ["faces"])
        self.assertEqual(s.source["faces"], "last_good")
        self.assertIn("happy", s.data["faces"]["moods"])
        good = (CONFIG / "faces.json").read_text().replace("#7CFF6B", "#123456")
        self.write("faces.json", good)
        self.assertEqual(s.poll(), ["faces"])
        self.assertEqual((s.source["faces"], s.errors["faces"]), ("file", []))
        self.assertEqual(s.data["faces"]["moods"]["happy"]["color"], "#123456")

    def test_errors_point_at_the_problem(self):
        faces = json.loads((CONFIG / "faces.json").read_text())
        faces["moods"]["happy"].update(heigth=30, color="green", w="wide")
        faces["default"] = "grumpy"
        _, errors = check("faces", faces)
        text = "\n".join(errors)
        self.assertIn("faces.json: moods.happy.heigth: unknown field", text)
        self.assertIn('faces.json: moods.happy.color: expected a colour like "#00E5FF", got "green"', text)
        self.assertIn('faces.json: moods.happy.w: expected a number, got "wide"', text)
        self.assertIn('faces.json: default: "grumpy" is not one of the moods', text)

    def test_settings_only_need_what_they_change(self):
        self.write("settings.json", '{"fps": 20}')
        s = self.store()
        self.assertEqual((s.data["settings"]["fps"], s.data["settings"]["displays"]), (20, 1))
        _, errors = check("settings", {"displays": True, "brightness": {"mode": "dim"}})
        self.assertEqual(len(errors), 2)

    def test_atomic_write_leaves_no_temp_file(self):
        write_text_atomic(self.dir / "x.json", "{}")
        self.assertEqual((self.dir / "x.json").read_text(), "{}")
        self.assertEqual([p.name for p in self.dir.glob("*.tmp")], [])


if __name__ == "__main__":
    unittest.main()
