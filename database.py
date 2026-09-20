"""
SQLite persistence: sensor readings + decisions, alert events, and the
learned personal baseline.

Real-hardware records and test-mode records are tagged with a `source`
column and are never mixed when queried.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    iso           TEXT    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'hardware',
    hr            REAL,
    spo2          REAL,
    body_temp     REAL,
    ambient_temp  REAL,
    humidity      REAL,
    pressure      REAL,
    ecg           REAL,
    pm25          REAL,
    accel         REAL,
    z_scores      TEXT,
    risk_level    TEXT,
    risk_score    REAL,
    reason        TEXT,
    confidence    REAL,
    emergency     INTEGER DEFAULT 0,
    addon_active  INTEGER DEFAULT 0,
    addon_sensors TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts);
CREATE INDEX IF NOT EXISTS idx_readings_source ON readings(source);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    iso         TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'hardware',
    kind        TEXT NOT NULL,
    risk_level  TEXT,
    risk_score  REAL,
    reason      TEXT,
    confidence  REAL,
    detail      TEXT,
    acknowledged INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);

CREATE TABLE IF NOT EXISTS baseline (
    signal   TEXT PRIMARY KEY,
    samples  INTEGER NOT NULL,
    mean     REAL NOT NULL,
    std      REAL NOT NULL,
    updated  REAL NOT NULL
);
"""

_READING_COLUMNS = [
    "id", "ts", "iso", "source", "hr", "spo2", "body_temp", "ambient_temp",
    "humidity", "pressure", "ecg", "pm25", "accel", "z_scores", "risk_level",
    "risk_score", "reason", "confidence", "emergency", "addon_active",
    "addon_sensors",
]


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


class Database:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or config.DB_PATH
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass
            self._conn.commit()

    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    # ------------------------------------------------------------- writes
    def insert_reading(self, result: Dict[str, Any], source: str = "hardware") -> int:
        r = result.get("readings", {})
        ts = float(result.get("timestamp", time.time()))
        row = (
            ts, _iso(ts), source,
            r.get("hr"), r.get("spo2"), r.get("body_temp"),
            r.get("ambient_temp"), r.get("humidity"), r.get("pressure"),
            r.get("ecg"), r.get("pm25"), r.get("accel"),
            json.dumps(result.get("z_scores", {})),
            result.get("risk_level"), result.get("risk_score"),
            result.get("reason"), result.get("confidence"),
            1 if result.get("emergency_mode") else 0,
            1 if result.get("addon_active") else 0,
            json.dumps(result.get("addon_sensors", [])),
        )
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO readings (ts, iso, source, hr, spo2, body_temp,"
                " ambient_temp, humidity, pressure, ecg, pm25, accel, z_scores,"
                " risk_level, risk_score, reason, confidence, emergency,"
                " addon_active, addon_sensors)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            self._conn.commit()
            return int(cur.lastrowid)

    def insert_alert(self, kind: str, result: Dict[str, Any],
                     source: str = "hardware", detail: str = "") -> int:
        ts = float(result.get("timestamp", time.time()))
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO alerts (ts, iso, source, kind, risk_level, risk_score,"
                " reason, confidence, detail) VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, _iso(ts), source, kind, result.get("risk_level"),
                 result.get("risk_score"), result.get("reason"),
                 result.get("confidence"), detail))
            self._conn.commit()
            return int(cur.lastrowid)

    def save_baseline(self, snapshot: Dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            for signal, s in snapshot.get("signals", {}).items():
                self._conn.execute(
                    "INSERT INTO baseline (signal, samples, mean, std, updated)"
                    " VALUES (?,?,?,?,?) ON CONFLICT(signal) DO UPDATE SET"
                    " samples=excluded.samples, mean=excluded.mean,"
                    " std=excluded.std, updated=excluded.updated",
                    (signal, s.get("samples", 0), s.get("mean", 0.0),
                     s.get("std", 0.0), now))
            self._conn.commit()

    # -------------------------------------------------------------- reads
    def recent_readings(self, limit: int = config.HISTORY_DEFAULT_LIMIT,
                        source: Optional[str] = None,
                        since: Optional[float] = None) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), config.HISTORY_MAX_LIMIT))
        sql = "SELECT * FROM readings"
        clauses, params = [], []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(float(since))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out = [self._row_to_dict(r) for r in rows]
        out.reverse()          # chronological for charts
        return out

    def recent_alerts(self, limit: int = 50,
                      source: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM alerts"
        params: List[Any] = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def load_baseline(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM baseline").fetchall()
        return {r["signal"]: {"samples": r["samples"], "mean": r["mean"],
                              "std": r["std"]} for r in rows}

    def counts(self) -> Dict[str, int]:
        with self._lock:
            readings = self._conn.execute("SELECT COUNT(*) c FROM readings").fetchone()["c"]
            alerts = self._conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"]
            hw = self._conn.execute(
                "SELECT COUNT(*) c FROM readings WHERE source='hardware'").fetchone()["c"]
            test = self._conn.execute(
                "SELECT COUNT(*) c FROM readings WHERE source='test'").fetchone()["c"]
        return {"readings": readings, "alerts": alerts,
                "hardware_readings": hw, "test_readings": test}

    def clear(self, source: Optional[str] = None) -> int:
        with self._lock:
            if source:
                cur = self._conn.execute("DELETE FROM readings WHERE source=?", (source,))
                self._conn.execute("DELETE FROM alerts WHERE source=?", (source,))
            else:
                cur = self._conn.execute("DELETE FROM readings")
                self._conn.execute("DELETE FROM alerts")
            self._conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = {k: row[k] for k in row.keys()}
        for field in ("z_scores", "addon_sensors"):
            raw = d.get(field)
            if isinstance(raw, str):
                try:
                    d[field] = json.loads(raw)
                except (ValueError, TypeError):
                    d[field] = {} if field == "z_scores" else []
        d["emergency"] = bool(d.get("emergency"))
        d["addon_active"] = bool(d.get("addon_active"))
        return d
