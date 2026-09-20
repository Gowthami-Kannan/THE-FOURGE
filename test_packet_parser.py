"""Packet parser tests: valid JSON lines, junk, partial data, aliases."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packet_parser import PacketParser, split_readings  # noqa: E402

GOOD = ('{"hr":78,"spo2":98,"body_temp":36.7,"ambient_temp":29.4,'
        '"humidity":58,"pressure":1008,"pm25":12,"ecg":0.12,"accel":0.03}')


class TestParser(unittest.TestCase):
    def setUp(self):
        self.p = PacketParser()

    def test_reference_packet(self):
        r = self.p.parse(GOOD)
        self.assertTrue(r.ok)
        self.assertEqual(r.data["hr"], 78.0)
        self.assertEqual(r.data["spo2"], 98.0)
        self.assertAlmostEqual(r.data["ecg"], 0.12)
        self.assertEqual(self.p.accepted, 1)

    def test_bytes_input(self):
        self.assertTrue(self.p.parse(GOOD.encode()).ok)

    def test_trailing_noise_is_tolerated(self):
        self.assertTrue(self.p.parse("garbage " + GOOD + " \r\n").ok)

    def test_aliases(self):
        r = self.p.parse('{"heart_rate":80,"SpO2":97,"temp":30,"rh":50,'
                         '"press":1010,"skin_temp":36.9}')
        self.assertTrue(r.ok)
        self.assertEqual(r.data["hr"], 80.0)
        self.assertEqual(r.data["ambient_temp"], 30.0)
        self.assertEqual(r.data["body_temp"], 36.9)

    def test_numeric_strings(self):
        r = self.p.parse('{"hr":"78","spo2":"97.5"}')
        self.assertTrue(r.ok)
        self.assertEqual(r.data["hr"], 78.0)

    def test_partial_packet_rejected(self):
        r = self.p.parse('{"hr":78,"spo2":')
        self.assertFalse(r.ok)
        self.assertIsNotNone(r.error)

    def test_junk_rejected(self):
        for junk in ["", "   ", "hello world", "[1,2,3]", "{}", "null",
                     '{"hr": }', "\x00\x01garbled", None, 12345]:
            r = self.p.parse(junk)
            self.assertFalse(r.ok, f"{junk!r} should have been rejected")
        self.assertEqual(self.p.accepted, 0)
        self.assertEqual(self.p.rejected, 10)

    def test_out_of_range_dropped_not_crashed(self):
        r = self.p.parse('{"hr":9999,"spo2":400,"body_temp":36.8}')
        self.assertTrue(r.ok)
        self.assertNotIn("hr", r.data)
        self.assertNotIn("spo2", r.data)
        self.assertEqual(r.data["body_temp"], 36.8)
        self.assertTrue(r.warnings)

    def test_nan_and_booleans_rejected(self):
        r = self.p.parse({"hr": True, "spo2": float("nan"), "body_temp": 36.9})
        self.assertTrue(r.ok)
        self.assertEqual(set(r.data), {"body_temp"})

    def test_missing_vitals_rejected(self):
        r = self.p.parse('{"humidity":50,"pressure":1010}')
        self.assertFalse(r.ok)

    def test_addon_only_packet_accepted(self):
        r = self.p.parse('{"ecg":0.2,"accel":0.1}')
        self.assertTrue(r.ok)

    def test_unknown_fields_ignored(self):
        r = self.p.parse('{"hr":70,"battery":88,"fw":"1.0"}')
        self.assertTrue(r.ok)
        self.assertEqual(set(k for k in r.data if not k.startswith("_")), {"hr"})

    def test_sequence_number_passed_through(self):
        r = self.p.parse('{"hr":70,"seq":42}')
        self.assertEqual(r.data["_seq"], 42.0)

    def test_stats_and_reset(self):
        self.p.parse(GOOD)
        self.p.parse("junk")
        s = self.p.stats()
        self.assertEqual((s["total"], s["accepted"], s["rejected"]), (2, 1, 1))
        self.p.reset()
        self.assertEqual(self.p.total, 0)

    def test_split_readings(self):
        r = self.p.parse(GOOD)
        cont, addon = split_readings(r.data)
        self.assertIn("hr", cont)
        self.assertIn("ecg", addon)
        self.assertNotIn("ecg", cont)


if __name__ == "__main__":
    unittest.main()
