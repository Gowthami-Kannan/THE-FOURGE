"""Decision engine tests: baseline, z-scores, safety, fuzzy, governor."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from decision_engine import (DecisionEngine, PersonalBaseline, RiskGovernor,  # noqa: E402
                             Welford, band_for_score, safety_check)


def packet(hr=74, spo2=98, body=36.8, amb=28.5, hum=58, pres=1008, **extra):
    d = {"hr": hr, "spo2": spo2, "body_temp": body, "ambient_temp": amb,
         "humidity": hum, "pressure": pres}
    d.update(extra)
    return d


def settle(engine, p, n=40):
    out = None
    for _ in range(n):
        out = engine.process(p)
    return out


class TestWelford(unittest.TestCase):
    def test_mean_and_std(self):
        w = Welford()
        data = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        for x in data:
            w.update(x)
        self.assertAlmostEqual(w.mean, 5.0, places=6)
        self.assertAlmostEqual(w.std, 2.13809, places=4)   # sample std
        self.assertEqual(w.count, 8)

    def test_single_sample_is_safe(self):
        w = Welford()
        w.update(10.0)
        self.assertEqual(w.variance, 0.0)
        self.assertEqual(w.std, 0.0)


class TestBaseline(unittest.TestCase):
    def test_personalization_grows(self):
        b = PersonalBaseline()
        self.assertEqual(b.maturity(), 0.0)
        for _ in range(config.BASELINE_MATURE_SAMPLES):
            b.update(packet(hr=60))
        self.assertAlmostEqual(b.maturity(), 1.0, places=3)
        mean, std, weight = b.estimate("hr")
        self.assertAlmostEqual(mean, 60.0, places=3)
        self.assertGreaterEqual(std, config.STD_FLOOR["hr"])
        self.assertAlmostEqual(weight, 1.0, places=3)

    def test_z_score_uses_personal_mean(self):
        b = PersonalBaseline()
        for _ in range(config.BASELINE_MATURE_SAMPLES):
            b.update(packet(hr=60))
        z = b.z_score("hr", 60.0)
        self.assertAlmostEqual(z, 0.0, places=2)
        self.assertGreater(b.z_score("hr", 90.0), 3.0)

    def test_missing_signal_gives_none(self):
        b = PersonalBaseline()
        self.assertIsNone(b.z_score("hr", None))


class TestSafety(unittest.TestCase):
    def test_critical_spo2(self):
        s = safety_check({"spo2": 80})
        self.assertTrue(s["critical"])
        self.assertEqual(s["severity"], 100.0)

    def test_warning_hr(self):
        s = safety_check({"hr": 120})
        self.assertTrue(s["warning"])
        self.assertFalse(s["critical"])

    def test_normal(self):
        s = safety_check(packet())
        self.assertEqual(s["severity"], 0.0)


class TestGovernor(unittest.TestCase):
    def test_escalates_fast_and_falls_slowly(self):
        g = RiskGovernor()
        for _ in range(4):
            g.update(95.0, critical=True)
        self.assertEqual(g.level, "EMERGENCY")
        steps = 0
        while g.level != "NORMAL" and steps < 200:
            g.update(2.0)
            steps += 1
        self.assertEqual(g.level, "NORMAL")
        self.assertGreater(steps, config.DEESCALATE_CONFIRMATIONS)

    def test_no_flicker_at_band_edge(self):
        g = RiskGovernor()
        for _ in range(10):
            g.update(31.0)
        level = g.level
        for _ in range(10):
            g.update(29.0)
            self.assertEqual(g.level, level, "risk level flickered at the band edge")

    def test_bands(self):
        self.assertEqual(band_for_score(0), "NORMAL")
        self.assertEqual(band_for_score(40), "ATTENTION")
        self.assertEqual(band_for_score(60), "HIGH RISK")
        self.assertEqual(band_for_score(99), "EMERGENCY")


class TestScenarios(unittest.TestCase):
    def test_normal_stays_normal(self):
        e = DecisionEngine()
        out = settle(e, packet(), 50)
        self.assertEqual(out["risk_level"], "NORMAL")
        self.assertFalse(out["emergency_mode"])
        self.assertGreater(out["confidence"], 0.4)
        self.assertLess(out["risk_score"], config.RISK_BANDS[0][0])

    def test_exercise_is_not_an_emergency(self):
        e = DecisionEngine()
        settle(e, packet(), 60)
        out = None
        for _ in range(12):
            out = e.process(packet(hr=142, spo2=96, body=37.5, amb=31, hum=66))
        self.assertIn(out["risk_level"], ("ATTENTION", "HIGH RISK"))
        self.assertFalse(out["emergency_mode"])

    def test_abnormal_physiology_raises_level(self):
        e = DecisionEngine()
        settle(e, packet(), 60)
        out = None
        for _ in range(10):
            out = e.process(packet(hr=121, spo2=92, body=38.3, amb=33, hum=72))
        self.assertIn(out["risk_level"], ("ATTENTION", "HIGH RISK", "EMERGENCY"))
        self.assertTrue(out["addon_active"], "add-on sensors should be requested")
        self.assertTrue(out["reason"])

    def test_exertion_relaxes_heart_rate_but_not_spo2(self):
        e = DecisionEngine()
        settle(e, packet(), 60)
        moving = None
        for _ in range(15):
            moving = e.process(packet(hr=150, spo2=97, body=37.4, accel=1.4))
        self.assertFalse(moving["emergency_mode"],
                         "a fast heart rate while moving is not an emergency")

        e2 = DecisionEngine()
        settle(e2, packet(), 60)
        still = None
        for _ in range(6):
            still = e2.process(packet(hr=150, spo2=86, body=37.4, accel=1.4))
        self.assertTrue(still["emergency_mode"],
                        "low SpO2 must still be critical while moving")

    def test_impact_motion_is_not_treated_as_exertion(self):
        e = DecisionEngine()
        settle(e, packet(), 60)
        out = None
        for _ in range(6):
            out = e.process(packet(hr=150, accel=4.2))
        self.assertIn(out["risk_level"], ("HIGH RISK", "EMERGENCY"))

    def test_relative_spread_floor_tames_a_very_steady_baseline(self):
        e = DecisionEngine()
        settle(e, packet(hr=72), 80)
        z = e.baseline.z_score("hr", 86.0)
        self.assertLess(abs(z), 3.0,
                        "an ordinary fluctuation should not look extreme")

    def test_emergency_and_recovery(self):
        e = DecisionEngine()
        settle(e, packet(), 60)
        out = None
        for _ in range(6):
            out = e.process(packet(hr=158, spo2=83, body=39.5, amb=37, hum=78,
                                   ecg=2.9, accel=3.9, pm25=180))
        self.assertEqual(out["risk_level"], "EMERGENCY")
        self.assertTrue(out["emergency_mode"])
        self.assertTrue(out["addon_sensors"])
        cmd = e.emergency_command()
        self.assertTrue(cmd["enable"])
        self.assertEqual(cmd["cmd"], "set_addon")

        # recovery
        for _ in range(60):
            out = e.process(packet())
        self.assertEqual(out["risk_level"], "NORMAL")
        self.assertFalse(out["emergency_mode"])

    def test_baseline_freezes_during_an_event(self):
        e = DecisionEngine()
        settle(e, packet(), 60)
        before = e.baseline.stats["hr"].count
        for _ in range(10):
            e.process(packet(hr=158, spo2=83, body=39.5))
        self.assertEqual(e.baseline.stats["hr"].count, before,
                         "baseline must not learn during an unsafe event")

    def test_garbage_values_are_ignored(self):
        e = DecisionEngine()
        out = e.process({"hr": 99999, "spo2": -12, "body_temp": "abc",
                         "ambient_temp": None, "humidity": float("nan")})
        self.assertEqual(out["readings"], {})
        self.assertEqual(out["risk_level"], "NORMAL")
        self.assertTrue(out["missing"])

    def test_missing_fields_lower_confidence(self):
        e = DecisionEngine()
        full = settle(e, packet(), 30)
        partial = e.process({"hr": 74, "spo2": 98})
        self.assertLess(partial["confidence"], full["confidence"])

    def test_environment_alone_is_not_an_emergency(self):
        e = DecisionEngine()
        settle(e, packet(), 40)
        out = None
        for _ in range(10):
            out = e.process(packet(amb=40, hum=85))
        self.assertNotEqual(out["risk_level"], "EMERGENCY")

    def test_output_contract(self):
        e = DecisionEngine()
        out = e.process(packet())
        for key in ("risk_level", "risk_score", "reason", "confidence",
                    "emergency_mode", "z_scores", "readings", "timestamp"):
            self.assertIn(key, out)
        self.assertIn(out["risk_level"], config.RISK_LEVELS)
        self.assertGreaterEqual(out["risk_score"], 0)
        self.assertLessEqual(out["risk_score"], 100)
        self.assertGreaterEqual(out["confidence"], 0.0)
        self.assertLessEqual(out["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
