"""Simulated car, Modulino motion and geofences."""

import unittest

from companion.car_sim import CarSim
from companion.geofence import Geofences, distance_m
from companion.motion import Motion


class CarSimTest(unittest.TestCase):
    def test_set_clamps_and_rejects_unknown_fields(self):
        car = CarSim()
        car.set({"speed_kmh": 999, "ignition": 0})
        self.assertEqual((car.state["speed_kmh"], car.state["ignition"]), (260, False))
        with self.assertRaises(ValueError):
            car.set({"warp": 9})

    def test_scenario_ramps_and_ends(self):
        car = CarSim()
        car.start("launch", 0)
        car.tick(3.2)
        self.assertTrue(0 < car.state["speed_kmh"] < 125)
        car.tick(10)
        self.assertEqual((car.state["speed_kmh"], car.scenario), (125, None))

    def test_moving_a_slider_stops_the_scenario(self):
        car = CarSim()
        car.start("park", 0)
        car.set({"speed_kmh": 40})
        car.tick(20)
        self.assertEqual((car.state["speed_kmh"], car.state["ignition"]), (40, True))


class MotionTest(unittest.TestCase):
    def feed(self, motion, samples, t=0.0):
        for i, sample in enumerate(samples):
            motion.add(*sample, t + i * 0.05)
        return t + len(samples) * 0.05

    def test_still_is_small_and_shaking_is_big(self):
        motion = Motion()
        t = self.feed(motion, [(0, 0, 1)] * 40)
        self.assertLess(motion.value(t), 0.02)
        t = self.feed(motion, [(1.5, 0, 1), (-1.5, 0, 1)] * 10, t)
        self.assertGreater(motion.value(t), 0.35)

    def test_tilting_slowly_does_not_count(self):
        motion = Motion()
        samples = [(i / 400, 0, 1) for i in range(400)]  # 1 g turning sideways over 20 s
        t = self.feed(motion, samples)
        self.assertLess(motion.value(t), 0.1)

    def test_no_sensor_means_none_and_shake_button_overrides(self):
        motion = Motion()
        self.assertIsNone(motion.value(0))
        t = self.feed(motion, [(0, 0, 1)] * 5)
        self.assertIsNone(motion.value(t + 3))  # stale
        motion.simulate(1.0, 2, t)
        self.assertEqual(motion.value(t + 1), 1.0)


class GeofenceTest(unittest.TestCase):
    PLACE = {"id": "kastelruth", "lat": 46.567, "lon": 11.567, "radius_m": 2000, "cooldown_min": 60}

    def test_distance(self):
        self.assertAlmostEqual(distance_m(46, 11, 47, 11) / 1000, 111.2, delta=0.1)

    def test_enter_once_despite_jitter_at_the_edge(self):
        geo = Geofences()
        north = lambda m: (self.PLACE["lat"] + m / 111195, self.PLACE["lon"])  # noqa: E731
        events = []
        for t, m in enumerate([3000, 1990, 2100, 1990, 2300, 1950]):  # jitter around 2 km
            events += [wait for _, wait in geo.update([self.PLACE], *north(m), 0.2, t)]
        self.assertEqual(events, [0])  # entered once, never left (2.4 km needed)
        self.assertEqual(geo.current, "kastelruth")

    def test_cooldown_after_leaving_and_coming_back(self):
        geo = Geofences()
        here = (self.PLACE["lat"], self.PLACE["lon"])
        far = (self.PLACE["lat"] + 0.1, self.PLACE["lon"])
        self.assertEqual(geo.update([self.PLACE], *here, 0.2, 0)[0][1], 0)
        geo.update([self.PLACE], *far, 0.2, 60)
        self.assertEqual(geo.update([self.PLACE], *here, 0.2, 600)[0][1], 50)  # 50 min to go
        geo.update([self.PLACE], *far, 0.2, 700)
        self.assertEqual(geo.update([self.PLACE], *here, 0.2, 3700)[0][1], 0)


if __name__ == "__main__":
    unittest.main()
