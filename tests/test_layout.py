import copy
import unittest

from companion import defaults, faces, layout
from companion.defaults import VISOR
from tests.test_faces import FACES

NEUTRAL = faces.resolve(FACES, "neutral")


def shapes(scene, display=0):
    return scene["displays"][display]["shapes"]


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.settings = copy.deepcopy(defaults.SETTINGS)

    def test_one_display_is_symmetric(self):
        left, right = shapes(layout.eyes_scene(NEUTRAL, self.settings))
        self.assertEqual(left["x"] + right["x"], layout.SIZE)
        self.assertEqual(right["x"] - left["x"], 14 + 36)  # gap + one eye width
        self.assertEqual((left["inner"], right["inner"]), ("right", "left"))

    def test_look_moves_both_eyes(self):
        base = shapes(layout.eyes_scene(NEUTRAL, self.settings))
        moved = shapes(layout.eyes_scene(NEUTRAL, self.settings, look=(1, -1)))
        for a, b in zip(base, moved):
            self.assertEqual(b["x"] - a["x"], 18)
            self.assertEqual(b["y"] - a["y"], -12)

    def test_blink_closes_to_a_line(self):
        pair = faces.resolve(FACES, "happy")
        for eye in shapes(layout.eyes_scene(pair, self.settings, blink=1)):
            self.assertEqual((eye["h"], eye["cut"], eye["slant"], eye["r"]), (layout.MIN_H, 0, 0, 1))

    def test_corner_radius_fits_the_eye(self):
        pair = copy.deepcopy(NEUTRAL)
        pair["left"].update(r=30, h=20)
        left, _ = shapes(layout.eyes_scene(pair, self.settings))
        self.assertEqual(left["r"], 10)

    def test_two_displays_get_one_big_eye_each(self):
        self.settings["displays"] = 2
        scene = layout.eyes_scene(NEUTRAL, self.settings, brightness=0.5)
        self.assertEqual(len(scene["displays"]), 2)
        for i in range(2):
            (eye,) = shapes(scene, i)
            self.assertEqual((eye["x"], eye["y"], eye["w"]), (64, 64, 72))
        self.assertEqual(scene["brightness"], 0.5)

    def test_visor_slides_down_from_above(self):
        pair = dict(NEUTRAL)
        self.assertNotIn("visor", layout.eyes_scene(pair, self.settings, visor=VISOR)["displays"][0])
        heights = []
        for down in (0.1, 0.5, 1.0):
            pair["visor"] = down
            visor = layout.eyes_scene(pair, self.settings, visor=VISOR)["displays"][0]["visor"]
            heights.append(visor["y"])
            self.assertEqual((visor["x"], visor["w"], visor["h"]), (64, VISOR["w"], VISOR["h"]))
        self.assertEqual(heights, sorted(heights))
        self.assertEqual(heights[-1], VISOR["y"])
        self.assertLess(heights[0] + VISOR["h"] / 2, 10)  # mostly above the display

    def test_visor_moves_with_the_eyes(self):
        pair = dict(NEUTRAL, visor=1)
        scene = layout.eyes_scene(pair, self.settings, look=(1, -1), visor=VISOR)
        visor, eye = scene["displays"][0]["visor"], shapes(scene)[0]
        self.assertEqual((visor["x"], visor["y"]), (64 + 18, VISOR["y"] - 12))
        self.assertEqual(eye["y"], 64 - 12)


if __name__ == "__main__":
    unittest.main()
