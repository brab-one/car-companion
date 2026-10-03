import json
import math
import random
import unittest

from companion.animator import Animator, mix
from tests import ROOT

FACES = json.loads((ROOT / "config" / "faces.json").read_text())
ANIMATIONS = json.loads((ROOT / "config" / "animations.json").read_text())
IDLE = {"play": ["glance_left"], "every_s": [5, 12]}


class AnimatorTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.anim = Animator(FACES, ANIMATIONS, self.now, mood_ms=300, rng=random.Random(1))
        self.anim.set_base("neutral", IDLE, self.now)

    def run_for(self, seconds, dt=0.02):
        """Advance time; returns every (shape, look, blink) seen."""
        frames = []
        end = self.now + seconds
        while self.now < end:
            self.now = round(self.now + dt, 3)
            frames.append(self.anim.update(self.now))
        return frames

    def wake(self):
        self.anim.set_awake(True, self.now)
        self.run_for(4)  # wake_up takes about 2.5 s

    def test_mix_blends_numbers_pairs_and_colours(self):
        self.assertEqual(mix(0, 10, 0.5), 5)
        self.assertEqual(mix((0, 0), (1, -1), 0.5), (0.5, -0.5))
        self.assertEqual(mix("#000000", "#FF8000", 0.5), "#804000")

    def test_wakes_up_and_rests_open_in_the_middle(self):
        self.assertEqual(self.anim.update(self.now)[2], 1.0)  # starts asleep, eyes closed
        self.wake()
        self.anim.blinker = None  # ignore a blink that may just be running
        shape, look, blink = self.anim.update(self.now)
        self.assertEqual((look, self.anim.blink.b), ((0.0, 0.0), 0.0))
        self.assertEqual(shape["left"]["h"], 44)

    def test_blinks_every_few_seconds_while_awake(self):
        self.wake()
        closed = [f for f in self.run_for(30) if f[2] > 0.9]
        self.assertTrue(closed, "no blink in 30 s")

    def test_no_blinks_or_idle_while_asleep(self):
        self.wake()
        self.anim.set_awake(False, self.now)
        frames = self.run_for(30)
        self.assertTrue(all(f[2] == 1.0 for f in frames[-200:]))  # closed and staying closed
        self.assertIsNone(self.anim.playing)

    def test_glance_returns_to_the_middle(self):
        self.wake()
        self.anim.play("glance_left", self.now)
        looks = [f[1][0] for f in self.run_for(2)]
        self.assertLess(min(looks), -0.7)
        self.assertEqual(self.anim.look.value(self.now), (0.0, 0.0))

    def test_look_around_reaches_the_corners_and_ends_in_the_middle(self):
        targets = [self.anim._random_look() for _ in range(300)]
        self.assertTrue(all(-1 <= x <= 1 and -1 <= y <= 1 for x, y in targets))
        corners = {(x > 0, y > 0) for x, y in targets if abs(x) > 0.9 and abs(y) > 0.9}
        self.assertEqual(len(corners), 4)
        self.wake()
        self.anim.play("look_around", self.now)
        self.run_for(12)
        self.assertIsNot(self.anim.playing, "look_around")
        self.assertEqual(self.anim.look.value(self.now), (0.0, 0.0))

    def test_new_base_mood_shows_after_mood_ms(self):
        self.wake()
        self.anim.set_base("angry", IDLE, self.now)
        self.run_for(0.4)
        shape, _, _ = self.anim.update(self.now)
        self.assertEqual((shape["left"]["color"], shape["left"]["slant"]), ("#FF4D3A", 12))

    def test_animation_mood_returns_to_base_unless_keep(self):
        self.wake()
        self.anim.play("surprised", self.now)
        self.run_for(0.3)
        self.assertEqual(self.anim.update(self.now)[0]["left"]["w"], 42)
        self.run_for(2)
        self.assertEqual(self.anim.update(self.now)[0]["left"]["w"], 36)
        self.anim.set_awake(False, self.now)  # "sleep" has keep: true
        self.run_for(3)
        shape, _, blink = self.anim.update(self.now)
        self.assertEqual((shape["left"]["h"], blink), (10, 1.0))

    def test_repeat_and_nested_animations_expand(self):
        steps = self.anim._expand({"steps": [{"anim": "double_blink"}, {"hold_ms": 10, "repeat": 3}]}, 0)
        self.assertEqual(len(steps), 4 + 3)

    def test_unknown_animation_is_refused(self):
        self.assertFalse(self.anim.play("no_such_animation", self.now))
        self.assertFalse(self.anim.play(None, self.now))
        self.assertTrue(math.isinf(Animator(FACES, ANIMATIONS, 0).next_blink))


if __name__ == "__main__":
    unittest.main()
