import base64
import struct
import tempfile
import unittest
from pathlib import Path

from companion.clips import ClipFiles, ClipPlayer
from tests import ROOT

WHEEL = (ROOT / "assets" / "clips" / "wheel.png").read_bytes()
CLIP = {"id": "wheel", "name": "Wheel", "file": "wheel.png", "frames": 16, "fps": 12,
        "show_s": 5, "every_min": 5, "enabled": True}


def b64(data):
    return base64.b64encode(data).decode()


class ClipFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.files = ClipFiles(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_upload_in_parts(self):
        parts = [WHEEL[:5000], WHEEL[5000:10000], WHEEL[10000:]]
        for i, part in enumerate(parts):
            done, error = self.files.add_part("mine.png", i, 3, b64(part))
            self.assertEqual((done, error), (i == 2, None))
        self.assertEqual(self.files.names(), ["mine.png"])
        self.assertEqual((self.dir / "mine.png").read_bytes(), WHEEL)

    def test_refuses_wrong_sizes_and_bad_data(self):
        wrong = WHEEL[:16] + struct.pack(">II", 100, 200) + WHEEL[24:]
        self.assertEqual(self.files.add_part("bad.png", 0, 1, b64(wrong)),
                         (True, "a clip must be 128 wide and 1 to 300 frames of 128 high, not 100 x 200"))
        self.assertEqual(self.files.add_part("x.png", 0, 1, "not base64!")[1], "the clip data is not valid base64")
        self.assertIn("bad file name", self.files.add_part("../x.png", 0, 1, "")[1])
        self.assertIn("bad part", self.files.add_part("x.png", 3, 2, "")[1])
        self.assertEqual(self.files.names(), [])


class ClipPlayerTest(unittest.TestCase):
    def player(self, **change):
        player = ClipPlayer()
        player.configure({"clips": [{**CLIP, **change}]}, {}, 0)
        return player

    def test_comes_every_few_minutes_for_a_few_seconds(self):
        p = self.player()
        p.update({}, 299, blocked=False)
        self.assertIsNone(p.current)
        p.update({}, 300, blocked=False)
        self.assertEqual(p.current[0]["id"], "wheel")
        self.assertEqual(p.frame(300.5), 6)  # 0.5 s at 12 frames a second
        p.update({}, 305, blocked=False)
        self.assertIsNone(p.current)  # shown for show_s
        p.update({}, 599, blocked=False)
        self.assertIsNone(p.current)
        p.update({}, 600, blocked=False)
        self.assertIsNotNone(p.current)

    def test_more_important_things_cut_it_and_it_waits_for_them(self):
        p = self.player()
        p.update({}, 300, blocked=True)
        self.assertIsNone(p.current)  # a place picture shows: the clip waits
        p.update({}, 302, blocked=False)
        self.assertIsNotNone(p.current)
        p.update({}, 303, blocked=True)
        self.assertIsNone(p.current)  # cut

    def test_only_while_its_conditions_hold(self):
        p = self.player(when=["speed_kmh > 20"])
        p.update({"speed_kmh": 0}, 301, blocked=False)
        self.assertIsNone(p.current)
        p.update({"speed_kmh": 50}, 302, blocked=False)
        self.assertIsNotNone(p.current)

    def test_play_now_also_for_disabled_clips(self):
        p = self.player(enabled=False)
        p.update({}, 1000, blocked=False)
        self.assertIsNone(p.current)
        self.assertTrue(p.play("wheel", 1000))
        self.assertIsNotNone(p.current)
        self.assertFalse(p.play("nope", 1000))

    def test_a_shorter_interval_applies_at_once(self):
        p = self.player()
        p.configure({"clips": [{**CLIP, "every_min": 1}]}, {}, 10)
        p.update({}, 70, blocked=False)
        self.assertIsNotNone(p.current)


if __name__ == "__main__":
    unittest.main()
