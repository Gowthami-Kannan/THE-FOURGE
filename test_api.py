"""
HTTP API and WebSocket tests.

These need FastAPI + httpx installed (pip install -r requirements.txt).
They are skipped, not failed, when the web stack is missing, so the core
engine tests still run anywhere.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BIOMON_DB",
                      os.path.join(tempfile.mkdtemp(prefix="biomon-api-"), "api.db"))

try:
    from fastapi.testclient import TestClient
    import app as app_module
    WEB_STACK = True
    SKIP_REASON = ""
except Exception as exc:                      # pragma: no cover
    WEB_STACK = False
    SKIP_REASON = f"web stack unavailable: {exc}"

import config  # noqa: E402

GOOD = ('{"hr":78,"spo2":98,"body_temp":36.7,"ambient_temp":29.4,'
        '"humidity":58,"pressure":1008}')


@unittest.skipUnless(WEB_STACK, SKIP_REASON)
class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # entering the client starts the app lifespan, which starts the
        # background pump that feeds the WebSocket
        cls._client_ctx = TestClient(app_module.app)
        cls.client = cls._client_ctx.__enter__()
        cls.service = app_module.service

    @classmethod
    def tearDownClass(cls):
        cls._client_ctx.__exit__(None, None, None)

    def tearDown(self):
        self.service.disconnect()

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_status_when_idle(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["connected"])
        self.assertEqual(body["device_message"], "DEVICE NOT CONNECTED")

    def test_latest_without_device(self):
        r = self.client.get("/api/latest")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["message"], "DEVICE NOT CONNECTED")

    def test_ports_lists_virtual(self):
        r = self.client.get("/api/ports")
        self.assertEqual(r.status_code, 200)
        devices = [p["device"] for p in r.json()["ports"]]
        self.assertIn(config.VIRTUAL_PORT_NAME, devices)

    def test_baseline_endpoint(self):
        r = self.client.get("/api/baseline")
        self.assertEqual(r.status_code, 200)
        self.assertIn("baseline", r.json())

    def test_connect_bad_port_returns_400(self):
        r = self.client.post("/api/connect", json={"port": "COM_NOT_REAL"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])

    def test_connect_virtual_and_disconnect(self):
        r = self.client.post("/api/connect",
                             json={"port": config.VIRTUAL_PORT_NAME,
                                   "scenario": "normal"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

        status = self.client.get("/api/status").json()
        self.assertTrue(status["connected"])
        self.assertTrue(status["test_mode"])
        self.assertEqual(status["device_message"], "TEST MODE")

        r = self.client.post("/api/disconnect")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.client.get("/api/status").json()["connected"])

    def test_scenario_switching(self):
        self.client.post("/api/connect",
                         json={"port": config.VIRTUAL_PORT_NAME})
        ok = self.client.post("/api/scenario", json={"scenario": "emergency"})
        self.assertEqual(ok.status_code, 200)
        bad = self.client.post("/api/scenario", json={"scenario": "nonsense"})
        self.assertEqual(bad.status_code, 400)

    def test_history_after_ingest(self):
        self.client.post("/api/connect", json={"port": config.VIRTUAL_PORT_NAME})
        for _ in range(3):
            self.service.ingest_line(GOOD)
        r = self.client.get("/api/history?limit=10&source=test")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreaterEqual(body["count"], 3)
        self.assertEqual(body["source"], "test")
        self.assertIn("risk_level", body["items"][0])

    def test_command_requires_device(self):
        r = self.client.post("/api/command", json={"enable": True})
        self.assertEqual(r.status_code, 409)
        self.client.post("/api/connect", json={"port": config.VIRTUAL_PORT_NAME})
        r = self.client.post("/api/command", json={"enable": True,
                                                   "sensors": ["ecg"]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_dashboard_is_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Biomedical Monitoring", r.text)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/style.css").status_code, 200)

    def test_websocket_snapshot_and_live_update(self):
        with self.client.websocket_connect("/ws") as ws:
            first = ws.receive_json()
            self.assertEqual(first["type"], "snapshot")
            self.assertIn("status", first)

            ws.send_text("ping")
            self.assertEqual(ws.receive_json()["type"], "pong")

            # a packet arriving must reach the socket
            self.service.ingest_line(GOOD)
            seen = None
            for _ in range(10):
                msg = ws.receive_json()
                if msg["type"] == "reading":
                    seen = msg
                    break
            self.assertIsNotNone(seen, "no live reading arrived over the WebSocket")
            self.assertIn("latest", seen)
            self.assertIn(seen["latest"]["risk_level"], config.RISK_LEVELS)

    def test_websocket_reports_rejected_packets(self):
        with self.client.websocket_connect("/ws") as ws:
            ws.receive_json()          # snapshot
            self.service.ingest_line("{broken")
            kinds = []
            for _ in range(10):
                kinds.append(ws.receive_json()["type"])
                if "reject" in kinds:
                    break
            self.assertIn("reject", kinds)


if __name__ == "__main__":
    unittest.main()
