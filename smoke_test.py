"""
End-to-end smoke test of the live path, without a web server or hardware.

    python tools/smoke_test.py

It drives the same code the server uses: virtual packets -> parser ->
decision engine -> SQLite -> event queue, and prints what the dashboard
would show at each stage.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config                                  # noqa: E402
from database import Database                  # noqa: E402
from monitoring_service import MonitoringService  # noqa: E402


def run() -> int:
    db_path = os.path.join(tempfile.mkdtemp(prefix="biomon-smoke-"), "smoke.db")
    svc = MonitoringService(db=Database(db_path))
    failures = []

    print("1. idle state")
    st = svc.status()
    print(f"   connected={st['connected']}  message={st['device_message']}")
    if st["device_message"] != "DEVICE NOT CONNECTED":
        failures.append("idle state should report DEVICE NOT CONNECTED")

    print("2. starting test mode")
    res = svc.connect(config.VIRTUAL_PORT_NAME, scenario="normal")
    print(f"   ok={res['ok']}  mode={res.get('mode')}  "
          f"message={svc.status()['device_message']}")
    if not res["ok"]:
        failures.append("test mode did not start")
        return report(failures)

    plan = [("normal", 60), ("exercise", 20), ("abnormal", 20),
            ("emergency", 15), ("recovery", 80), ("garbage", 20)]

    for scenario, count in plan:
        svc.set_scenario(scenario)
        for _ in range(count):
            svc.ingest_line(svc.virtual.next_line())
        r = svc.last_result
        print(f"3. {scenario:<10} -> {r['risk_level']:<10} "
              f"score {r['risk_score']:>5.1f}  conf {r['confidence']:.2f}  "
              f"emergency {str(r['emergency_mode']):<5} "
              f"addons {r['addon_sensors'] or '-'}")
        print(f"   reason: {r['reason'][:96]}")

        if scenario == "normal" and r["risk_level"] != "NORMAL":
            failures.append("normal scenario did not settle at NORMAL")
        if scenario == "exercise" and r["emergency_mode"]:
            failures.append("exercise was treated as an emergency")
        if scenario == "emergency" and r["risk_level"] != "EMERGENCY":
            failures.append("emergency scenario did not reach EMERGENCY")
        if scenario == "emergency" and not r["addon_sensors"]:
            failures.append("emergency did not request add-on sensors")
        if scenario == "recovery" and r["risk_level"] not in ("NORMAL", "ATTENTION"):
            failures.append("recovery did not step back down")

    print("4. add-on command traffic")
    print(f"   commands sent={svc.commands_sent}  last={svc.last_command}")
    if svc.commands_sent == 0:
        failures.append("no add-on activation command was produced")

    print("5. parser robustness")
    p = svc.parser.stats()
    print(f"   total={p['total']} accepted={p['accepted']} rejected={p['rejected']}"
          f"  last_error={p['last_error']}")
    if p["rejected"] == 0:
        failures.append("garbage scenario produced no rejects")

    print("6. database")
    counts = svc.db.counts()
    print(f"   {counts}")
    if counts["test_readings"] == 0:
        failures.append("nothing was written to SQLite")
    if counts["hardware_readings"] != 0:
        failures.append("test data leaked into the hardware history")
    alerts = svc.db.recent_alerts(source="test", limit=200)
    kinds = sorted({a["kind"] for a in alerts})
    print(f"   alerts={len(alerts)} kinds={kinds}")
    if "EMERGENCY" not in kinds:
        failures.append("no emergency alert was stored")

    print("7. personal baseline")
    base = svc.engine.baseline_snapshot()
    print(f"   maturity={base['maturity']}")
    for name in ("hr", "spo2", "body_temp"):
        s = base["signals"][name]
        print(f"   {name:<10} mean={s['mean']:<8} std={s['std']:<7} "
              f"n={s['samples']:<4} ready={s['ready']}")
    if base["maturity"] <= 0.0:
        failures.append("the baseline never learned anything")

    print("8. websocket event queue")
    print(f"   queued events={svc.events.qsize()}")
    if svc.events.qsize() == 0:
        failures.append("no events were queued for the WebSocket")

    print("9. disconnect")
    svc.disconnect()
    st = svc.status()
    print(f"   connected={st['connected']}  message={st['device_message']}")
    if st["connected"]:
        failures.append("disconnect left the link open")

    svc.shutdown()
    return report(failures)


def report(failures) -> int:
    print()
    if failures:
        print("SMOKE TEST FAILED")
        for f in failures:
            print("  -", f)
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
