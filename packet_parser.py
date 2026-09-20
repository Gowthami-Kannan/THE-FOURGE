"""
JSON-Lines packet parser for the STM32 link.

One line of serial input = one sensor packet. The parser is deliberately
forgiving about what the firmware sends and strict about what it passes on:
a malformed, partial or nonsense line is reported as rejected and never
reaches the decision engine.
"""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import config

# Names the firmware might use for the same signal.
ALIASES = {
    "hr": "hr", "heart_rate": "hr", "heartrate": "hr", "bpm": "hr", "pulse": "hr",
    "spo2": "spo2", "sp_o2": "spo2", "oxygen": "spo2", "sat": "spo2", "spo": "spo2",
    "body_temp": "body_temp", "bodytemp": "body_temp", "temp_body": "body_temp",
    "btemp": "body_temp", "skin_temp": "body_temp",
    "ambient_temp": "ambient_temp", "amb_temp": "ambient_temp",
    "temperature": "ambient_temp", "temp": "ambient_temp", "atemp": "ambient_temp",
    "humidity": "humidity", "hum": "humidity", "rh": "humidity",
    "pressure": "pressure", "press": "pressure", "hpa": "pressure",
    "pm25": "pm25", "pm2_5": "pm25", "pm2.5": "pm25", "pm": "pm25",
    "ecg": "ecg", "ecg_mv": "ecg", "ekg": "ecg",
    "accel": "accel", "acc": "accel", "accel_mag": "accel", "motion": "accel",
}

_NUM = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


class ParseResult:
    """Outcome of parsing one line."""

    __slots__ = ("ok", "data", "error", "raw", "warnings")

    def __init__(self, ok: bool, data: Optional[Dict[str, float]] = None,
                 error: Optional[str] = None, raw: str = "",
                 warnings: Optional[List[str]] = None) -> None:
        self.ok = ok
        self.data = data or {}
        self.error = error
        self.raw = raw
        self.warnings = warnings or []

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ParseResult ok={self.ok} data={self.data} error={self.error!r}>"


class PacketParser:
    """Stateful so it can keep simple counters for the dashboard."""

    def __init__(self) -> None:
        self.total = 0
        self.accepted = 0
        self.rejected = 0
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[float] = None

    # ------------------------------------------------------------------
    def parse(self, line: Any) -> ParseResult:
        self.total += 1
        result = self._parse(line)
        if result.ok:
            self.accepted += 1
        else:
            self.rejected += 1
            self.last_error = result.error
            self.last_error_at = time.time()
        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
        }

    def reset(self) -> None:
        self.__init__()

    # ------------------------------------------------------------------
    def _parse(self, line: Any) -> ParseResult:
        if line is None:
            return ParseResult(False, error="empty line")

        if isinstance(line, (bytes, bytearray)):
            try:
                line = line.decode("utf-8", errors="replace")
            except Exception:
                return ParseResult(False, error="undecodable bytes")

        if isinstance(line, dict):
            return self._normalize(line, raw=json.dumps(line))

        if not isinstance(line, str):
            return ParseResult(False, error=f"unsupported line type {type(line).__name__}")

        text = line.strip().strip("\x00").strip()
        if not text:
            return ParseResult(False, error="empty line")

        # Firmware boot banners / log lines are ignored quietly.
        if not text.startswith("{"):
            start = text.find("{")
            if start == -1:
                return ParseResult(False, error="not a JSON object", raw=text[:120])
            text = text[start:]

        end = text.rfind("}")
        if end == -1:
            return ParseResult(False, error="truncated packet", raw=text[:120])
        text = text[:end + 1]

        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            return ParseResult(False, error=f"invalid JSON: {exc.args[0][:60]}",
                               raw=text[:120])

        if not isinstance(obj, dict):
            return ParseResult(False, error="packet is not a JSON object", raw=text[:120])

        return self._normalize(obj, raw=text[:200])

    # ------------------------------------------------------------------
    def _normalize(self, obj: Dict[str, Any], raw: str = "") -> ParseResult:
        data: Dict[str, float] = {}
        warnings: List[str] = []

        for key, value in obj.items():
            if not isinstance(key, str):
                continue
            name = ALIASES.get(key.strip().lower())
            if name is None:
                continue
            number = self._to_float(value)
            if number is None:
                warnings.append(f"{key}: not a number")
                continue
            lo, hi = config.PLAUSIBLE_RANGE.get(name, (-1e9, 1e9))
            if number < lo or number > hi:
                warnings.append(f"{name}: {number:g} out of plausible range")
                continue
            data[name] = number

        if not data:
            return ParseResult(False, error="no usable sensor fields", raw=raw,
                               warnings=warnings)

        # A packet is only useful if at least one vital sign is present.
        if not any(k in data for k in ("hr", "spo2", "body_temp")):
            if not any(k in data for k in config.ADDON_SIGNALS):
                return ParseResult(False, error="no vital signs in packet",
                                   raw=raw, warnings=warnings)

        # Pass through a firmware timestamp / sequence number if present.
        for extra in ("seq", "ts", "uptime"):
            if extra in obj and isinstance(obj[extra], (int, float)):
                data["_" + extra] = float(obj[extra])

        return ParseResult(True, data=data, raw=raw, warnings=warnings)

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            f = float(value)
        elif isinstance(value, str):
            s = value.strip()
            if not _NUM.match(s):
                return None
            try:
                f = float(s)
            except ValueError:
                return None
        else:
            return None
        if math.isnan(f) or math.isinf(f):
            return None
        return f


def split_readings(data: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Separate continuous readings from add-on readings."""
    cont = {k: v for k, v in data.items() if k in config.CONTINUOUS_SIGNALS}
    addon = {k: v for k, v in data.items() if k in config.ADDON_SIGNALS}
    return cont, addon
