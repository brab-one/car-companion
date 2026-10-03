import unittest

from companion.rules import Rules, parse_condition

THRESHOLDS = {"fast_kmh": 100}


def rules(*specs):
    return Rules({"rules": list(specs)}, THRESHOLDS)


class ConditionTest(unittest.TestCase):
    def test_reads_numbers_thresholds_and_words(self):
        self.assertEqual(parse_condition("speed_kmh > 100"), ("speed_kmh", ">", 100))
        self.assertEqual(parse_condition("speed_kmh>$fast_kmh", THRESHOLDS), ("speed_kmh", ">", 100))
        self.assertEqual(parse_condition("ignition == false"), ("ignition", "==", False))
        self.assertEqual(parse_condition("place == kastelruth"), ("place", "==", "kastelruth"))

    def test_clear_errors(self):
        with self.assertRaisesRegex(ValueError, 'unknown signal "sped_kmh"'):
            parse_condition("sped_kmh > 100")
        with self.assertRaisesRegex(ValueError, "is not a condition"):
            parse_condition("speed_kmh is fast")
        with self.assertRaisesRegex(ValueError, 'unknown threshold "\\$slow_kmh"'):
            parse_condition("speed_kmh < $slow_kmh", THRESHOLDS)


class RulesTest(unittest.TestCase):
    def test_active_while_true_and_hold_s_longer(self):
        r = rules({"id": "fast", "when": ["speed_kmh > $fast_kmh"], "mood": "angry", "hold_s": 2})
        self.assertEqual(r.update({"speed_kmh": 50}, 0), [])
        self.assertEqual([x.id for x, _ in r.update({"speed_kmh": 150}, 1)], ["fast"])
        self.assertEqual(len(r.update({"speed_kmh": 50}, 2.5)), 1)  # held
        self.assertEqual(r.update({"speed_kmh": 50}, 3.5), [])

    def test_fires_once_per_cooldown(self):
        r = rules({"id": "brake", "when": ["g_long < -0.7"], "say": "Whoa!", "cooldown_s": 20})
        fired = []
        for t, g in [(0, -0.9), (1, -0.9), (2, 0), (5, -0.9), (6, 0), (30, -0.9)]:
            fired += [t for _, f in r.update({"g_long": g}, t) if f]
        self.assertEqual(fired, [0, 30])

    def test_missing_signal_makes_condition_false(self):
        r = rules({"id": "shaken", "when": ["motion_g > 0.3"], "mood": "angry"})
        self.assertEqual(r.update({"motion_g": None}, 0), [])

    def test_order_is_kept_and_state_survives_a_reload(self):
        specs = [{"id": "a", "when": ["rpm > 1"], "mood": "x"}, {"id": "b", "when": ["rpm > 0"], "mood": "y"}]
        r = rules(*specs)
        self.assertEqual([x.id for x, _ in r.update({"rpm": 5}, 0)], ["a", "b"])
        reloaded = Rules({"rules": specs}, THRESHOLDS, previous=r)
        self.assertEqual([f for _, f in reloaded.update({"rpm": 5}, 1)], [False, False])  # no re-firing

    def test_unreadable_rules_are_skipped(self):
        r = rules({"id": "bad", "when": ["speed_kmh > $nope"], "mood": "angry"})
        self.assertEqual(r.rules, [])


if __name__ == "__main__":
    unittest.main()
