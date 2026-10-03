import unittest

from companion import faces

FACES = {"version": 1, "default": "neutral", "moods": {
    "neutral": {"w": 36, "h": 44, "r": 10, "color": "#00E5FF", "slant": 0, "cut": 0,
                "gap": 14, "blink_s": [3, 7]},
    "happy": {"h": 30, "cut": 12},
    "suspicious": {"left": {"h": 18}, "right": {"h": 40}},
    "sleepy": {"blink_s": None},
}}


class FacesTest(unittest.TestCase):
    def test_mood_inherits_from_default(self):
        pair = faces.resolve(FACES, "happy")
        self.assertEqual(pair["left"], {"w": 36, "h": 30, "r": 10, "color": "#00E5FF",
                                        "slant": 0, "cut": 12})
        self.assertEqual(pair["left"], pair["right"])
        self.assertEqual(pair["gap"], 14)

    def test_left_and_right_override_one_eye(self):
        pair = faces.resolve(FACES, "suspicious")
        self.assertEqual((pair["left"]["h"], pair["right"]["h"]), (18, 40))
        self.assertEqual(pair["left"]["w"], 36)

    def test_unknown_mood_gives_default(self):
        self.assertEqual(faces.resolve(FACES, "no_such_mood"), faces.resolve(FACES, "neutral"))

    def test_visor_is_up_unless_a_mood_puts_it_down(self):
        self.assertEqual(faces.resolve(FACES, "happy")["visor"], 0)
        racing = {**FACES, "moods": {**FACES["moods"], "racing": {"visor": 1}}}
        self.assertEqual(faces.resolve(racing, "racing")["visor"], 1)

    def test_blink_can_be_switched_off(self):
        self.assertIsNone(faces.resolve(FACES, "sleepy")["blink_s"])
        self.assertEqual(faces.resolve(FACES, "happy")["blink_s"], [3, 7])


if __name__ == "__main__":
    unittest.main()
