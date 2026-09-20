"""Service-level tests: database, test mode, disconnect/reconnect, commands."""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from database import Database  # noqa: E402
from monitoring_service import MonitoringService  # noqa: E402
from serial_reader import SerialReader, list_serial_ports  # noqa: E402
from virtual_device import VirtualDevice  # noqa: E402

GOOD = ('{"hr":78,"spo2":98,"body_temp":36.7,"ambient_temp":29.4,'
        '"humidity":58,"pressure":1008}')


def temp_db():
    path = os.path.join(tempfile.mkdtemp(prefix="biomon-test-"), "test.db")
    return Database(path)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = temp_db()

    def tearDown(self):
        self.db.close()

    def _result(self, ts=None, level="NORMAL"):
        return {
            "timestamp": ts or time.time(),
            "readings": {"hr": 72, "spo2": 98, "body_temp": 36.8,
                         "ambient_temp": 29, "humidity": 55, "pressure": 1008},
            "z_scores": {"hr": 0.1, "spo2": -0.2},
            "risk_level": level, "risk_score": 12.0, "reason": "all clear",
            "confidence": 0.8, "emergency_mode": False,
            "addon_active": False, "addon_sensors": [],
        }

    def test_insert_and_read_back(self):
        rid = self.db.insert_reading(self._result())
        self.assertGreater(rid, 0)
        rows = self.db.recent_readings(limit=10, source="hardware")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hr"], 72)
        self.assertEqual(rows[0]["z_scores"]["hr"], 0.1)
        self.assertEqual(rows[0]["risk_level"], "NORMAL")

    def test_sources_are_separated(self):
        self.db.insert_reading(self._result(), source="hardware")
        self.db.insert_reading(self._result(), source="test")
        self.assertEqual(len(self.db.recent_readings(source="hardware")), 1)
        self.assertEqual(len(self.db.recent_readings(source="test")), 1)
        self.assertEqual(len(self.db.recent_readings()), 2)
        counts = self.db.counts()
        self.assertEqual(counts["hardware_readings"], 1)
        self.assertEqual(counts["test_readings"], 1)

    def test_alerts(self):
        self.db.insert_alert("EMERGENCY", self._result(level="EMERGENCY"),
                             detail="entered")
        alerts = self.db.recent_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["kind"], "EMERGENCY")

    def test_baseline_roundtrip(self):
        snap = {"signals": {"hr": {"samples": 10, "mean": 70.0, "std": 3.0}}}
        self.db.save_baseline(snap)
        self.db.save_baseline(snap)      # upsert, not duplicate
        stored = self.db.load_baseline()
        self.assertEqual(stored["hr"]["samples"], 10)
        self.assertAlmostEqual(stored["hr"]["mean"], 70.0)

    def test_history_is_chronological(self):
        now = time.time()
        for i in range(5):
            self.db.insert_reading(self._result(ts=now + i))
        rows = self.db.recent_readings(limit=5)
        self.assertEqual(rows, sorted(rows, key=lambda r: r["ts"]))


class TestVirtualDevice(unittest.TestCase):
    def test_scenarios_produce_parseable_packets(self):
        lines = []
        dev = VirtualDevice(on_line=lines.append)
        for name in ("normal", "exercise", "abnormal", "emergency", "recovery"):
            dev.set_scenario(name)
            line = dev.next_line()
            self.assertTrue(line.startswith("{"), name)

    def test_garbage_scenario_mostly_junk(self):
        from packet_parser import PacketParser
        dev = VirtualDevice(on_line=lambda s: None, scenario="garbage")
        p = PacketParser()
        for _ in range(20):
            p.parse(dev.next_line())
        self.assertGreater(p.rejected, 0)
        self.assertGreater(p.accepted, 0)   # the engine recovers after junk

    def test_addon_command_gates_addon_fields(self):
        dev = VirtualDevice(on_line=lambda s: None, scenario="emergency")
        self.assertNotIn("ecg", dev.next_line())
        dev.apply_command({"cmd": "set_addon", "enable": True,
                           "sensors": ["ecg", "accel"]})
        line = dev.next_line()
        self.assertIn("ecg", line)
        self.assertNotIn("pm25", line)


class TestSerialReader(unittest.TestCase):
    def test_port_listing_includes_virtual(self):
        ports = list_serial_ports()
        self.assertTrue(any(p["device"] == config.VIRTUAL_PORT_NAME for p in ports))

    def test_bad_port_fails_cleanly(self):
        r = SerialReader(on_line=lambda s: None)
        res = r.connect("COM_DOES_NOT_EXIST")
        self.assertFalse(res["ok"])
        self.assertIsNotNone(r.last_error)
        r.disconnect()
        self.assertFalse(r.connected)

    def test_command_without_link_is_refused(self):
        r = SerialReader(on_line=lambda s: None)
        self.assertFalse(r.send_command({"cmd": "set_addon", "enable": True}))
        self.assertIn("not connected", (r.last_error or ""))


class TestMonitoringService(unittest.TestCase):
    def setUp(self):
        self.svc = MonitoringService(db=temp_db())

    def tearDown(self):
        self.svc.shutdown()

    def test_idle_reports_disconnected(self):
        st = self.svc.status()
        self.assertFalse(st["connected"])
        self.assertEqual(st["device_message"], "DEVICE NOT CONNECTED")
        self.assertIsNone(self.svc.last_result)

    def test_ingest_stores_and_emits(self):
        result = self.svc.ingest_line(GOOD)
        self.assertIsNotNone(result)
        self.assertIn(result["risk_level"], config.RISK_LEVELS)
        self.assertEqual(len(self.svc.history(limit=10, source="hardware")), 1)
        self.assertFalse(self.svc.events.empty())

    def test_bad_line_does_not_crash_and_is_recorded(self):
        self.assertIsNone(self.svc.ingest_line("{oops"))
        self.assertEqual(self.svc.parser.rejected, 1)
        self.assertTrue(self.svc.rejects)
        self.assertIsNotNone(self.svc.ingest_line(GOOD))   # recovers

    def test_test_mode_lifecycle(self):
        res = self.svc.connect(config.VIRTUAL_PORT_NAME, scenario="normal")
        self.assertTrue(res["ok"])
        st = self.svc.status()
        self.assertTrue(st["connected"])
        self.assertTrue(st["test_mode"])
        self.assertEqual(st["device_message"], "TEST MODE")
        # drive some packets deterministically instead of waiting on the timer
        for _ in range(5):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.assertIsNotNone(self.svc.last_result)
        self.assertEqual(self.svc.db.counts()["test_readings"], 5)
        self.assertEqual(self.svc.db.counts()["hardware_readings"], 0)
        self.assertTrue(self.svc.set_scenario("emergency")["ok"])
        self.assertFalse(self.svc.set_scenario("nope")["ok"])
        self.svc.disconnect()
        self.assertFalse(self.svc.status()["connected"])

    def test_emergency_triggers_addon_command(self):
        self.svc.connect(config.VIRTUAL_PORT_NAME, scenario="normal")
        for _ in range(40):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.svc.set_scenario("emergency")
        for _ in range(12):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.assertTrue(self.svc.last_result["emergency_mode"])
        self.assertTrue(self.svc.commands_sent > 0, "no add-on command was sent")
        self.assertTrue(self.svc.virtual.addon_enabled)
        alerts = self.svc.db.recent_alerts(source="test")
        self.assertTrue(any(a["kind"] == "EMERGENCY" for a in alerts))

    def test_recovery_returns_to_normal(self):
        self.svc.connect(config.VIRTUAL_PORT_NAME, scenario="normal")
        for _ in range(40):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.svc.set_scenario("emergency")
        for _ in range(10):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.svc.set_scenario("recovery")
        for _ in range(80):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.assertIn(self.svc.last_result["risk_level"], ("NORMAL", "ATTENTION"))
        self.assertFalse(self.svc.last_result["emergency_mode"])

    def test_garbage_scenario_never_crashes(self):
        self.svc.connect(config.VIRTUAL_PORT_NAME, scenario="garbage")
        for _ in range(30):
            self.svc.ingest_line(self.svc.virtual.next_line())
        self.assertTrue(self.svc.parser.rejected > 0)
        self.assertTrue(self.svc.status()["connected"])

    def test_manual_command_requires_a_device(self):
        res = self.svc.send_emergency_command(["ecg"], True)
        self.assertFalse(res["ok"])
        self.svc.connect(config.VIRTUAL_PORT_NAME)
        res = self.svc.send_emergency_command(["ecg"], True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["command"]["sensors"], ["ecg"])

    def test_disconnect_then_reconnect(self):
        self.svc.connect(config.VIRTUAL_PORT_NAME)
        self.svc.ingest_line(self.svc.virtual.next_line())
        self.svc.disconnect()
        self.assertFalse(self.svc.status()["connected"])
        self.assertIsNone(self.svc.last_result)
        self.assertTrue(self.svc.connect(config.VIRTUAL_PORT_NAME)["ok"])
        self.assertTrue(self.svc.status()["connected"])

    def test_hardware_connect_failure_is_reported(self):
        res = self.svc.connect("COM_NOT_REAL")
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"])
        self.assertEqual(self.svc.status()["mode"], "idle")

    def test_snapshot_shape(self):
        snap = self.svc.snapshot()
        for key in ("status", "latest", "baseline", "alerts", "rejects"):
            self.assertIn(key, snap)


if __name__ == "__main__":
    unittest.main()
