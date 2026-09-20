"""
Serial link to the STM32 board.

Runs a background thread that reads JSON lines, hands each raw line to a
callback, and reconnects on its own if the cable is pulled. pyserial is
imported lazily so the rest of the system (engine, parser, database, test
mode) still works on a machine without it.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import config

try:  # pragma: no cover - environment dependent
    import serial  # type: ignore
    from serial.tools import list_ports  # type: ignore
    PYSERIAL_AVAILABLE = True
    PYSERIAL_ERROR = ""
except Exception as _exc:  # pragma: no cover
    serial = None  # type: ignore
    list_ports = None  # type: ignore
    PYSERIAL_AVAILABLE = False
    PYSERIAL_ERROR = str(_exc)


def list_serial_ports() -> List[Dict[str, str]]:
    """Every COM port the OS can see, plus the built-in virtual port."""
    ports: List[Dict[str, str]] = []
    if PYSERIAL_AVAILABLE and list_ports is not None:
        try:
            for p in list_ports.comports():
                ports.append({
                    "device": p.device,
                    "description": p.description or "serial port",
                    "hwid": getattr(p, "hwid", "") or "",
                    "kind": "hardware",
                })
        except Exception as exc:  # pragma: no cover
            ports.append({"device": "", "description": f"port scan failed: {exc}",
                          "hwid": "", "kind": "error"})
    ports.append({
        "device": config.VIRTUAL_PORT_NAME,
        "description": "Test mode - simulated device, no hardware needed",
        "hwid": "virtual",
        "kind": "virtual",
    })
    return ports


class SerialReader:
    """
    Background reader.

    on_line(str)              called for every raw line received
    on_state(dict)            called whenever the link state changes
    """

    def __init__(self,
                 on_line: Callable[[str], None],
                 on_state: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.on_line = on_line
        self.on_state = on_state or (lambda s: None)

        self.port: Optional[str] = None
        self.baudrate: int = config.SERIAL_BAUDRATE
        self.connected = False
        self.enabled = False
        self.last_error: Optional[str] = None
        self.last_rx: Optional[float] = None
        self.lines_read = 0
        self.reconnects = 0
        self.connected_at: Optional[float] = None

        self._serial: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    # ------------------------------------------------------------- status
    def status(self) -> Dict[str, Any]:
        stale = (self.connected and self.last_rx is not None
                 and (time.time() - self.last_rx) > config.STALE_AFTER)
        return {
            "connected": self.connected,
            "enabled": self.enabled,
            "port": self.port,
            "baudrate": self.baudrate,
            "last_error": self.last_error,
            "last_rx": self.last_rx,
            "lines_read": self.lines_read,
            "reconnects": self.reconnects,
            "stale": stale,
            "pyserial_available": PYSERIAL_AVAILABLE,
            "uptime": (time.time() - self.connected_at) if self.connected_at else 0.0,
        }

    def _emit_state(self) -> None:
        try:
            self.on_state(self.status())
        except Exception:
            pass

    # -------------------------------------------------------- connect/stop
    def connect(self, port: str, baudrate: Optional[int] = None) -> Dict[str, Any]:
        if not PYSERIAL_AVAILABLE:
            self.last_error = ("pyserial is not installed - run "
                               "pip install -r requirements.txt")
            self._emit_state()
            return {"ok": False, "error": self.last_error}

        self.disconnect()
        self.port = port
        self.baudrate = int(baudrate or config.SERIAL_BAUDRATE)
        self.enabled = True
        self._stop.clear()
        self.last_error = None

        opened = self._open()
        self._thread = threading.Thread(target=self._loop, name="serial-reader",
                                        daemon=True)
        self._thread.start()
        return {"ok": opened, "error": self.last_error, "status": self.status()}

    def disconnect(self) -> Dict[str, Any]:
        self.enabled = False
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._thread = None
        self._close()
        self._emit_state()
        return {"ok": True, "status": self.status()}

    # ------------------------------------------------------------ plumbing
    def _open(self) -> bool:
        with self._lock:
            try:
                self._serial = serial.Serial(          # type: ignore[union-attr]
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=config.SERIAL_TIMEOUT,
                    write_timeout=config.SERIAL_WRITE_TIMEOUT,
                )
                try:
                    self._serial.reset_input_buffer()
                except Exception:
                    pass
                self.connected = True
                self.connected_at = time.time()
                self.last_error = None
                self._emit_state()
                return True
            except Exception as exc:
                self._serial = None
                self.connected = False
                self.last_error = str(exc)
                self._emit_state()
                return False

    def _close(self) -> None:
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
            if self.connected:
                self.connected = False
                self.connected_at = None

    def _loop(self) -> None:
        buffer = b""
        while not self._stop.is_set() and self.enabled:
            if not self.connected:
                time.sleep(config.RECONNECT_DELAY)
                if self._stop.is_set() or not self.enabled:
                    break
                if self._open():
                    self.reconnects += 1
                continue
            try:
                chunk = self._serial.read(256)        # type: ignore[union-attr]
                if chunk:
                    buffer += chunk
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        text = raw.decode("utf-8", errors="replace").strip("\r\n\t ")
                        if not text:
                            continue
                        self.lines_read += 1
                        self.last_rx = time.time()
                        try:
                            self.on_line(text)
                        except Exception as exc:       # never kill the reader
                            self.last_error = f"handler error: {exc}"
                    if len(buffer) > 8192:             # runaway line, drop it
                        buffer = b""
                else:
                    time.sleep(0.01)
            except Exception as exc:
                self.last_error = f"link lost: {exc}"
                self._close()
                self._emit_state()
                time.sleep(config.RECONNECT_DELAY)
        self._close()
        self._emit_state()

    # ------------------------------------------------------------- writing
    def send_command(self, command: Dict[str, Any]) -> bool:
        """Send one JSON-line command to the board."""
        payload = (json.dumps(command, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            if not self.connected or self._serial is None:
                self.last_error = "cannot send command: not connected"
                return False
            try:
                self._serial.write(payload)
                try:
                    self._serial.flush()
                except Exception:
                    pass
                return True
            except Exception as exc:
                self.last_error = f"command failed: {exc}"
                self._close()
                self._emit_state()
                return False
