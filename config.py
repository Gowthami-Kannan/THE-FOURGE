"""
Central configuration for the Personalized Environment-Aware Biomedical
Monitoring System.

Everything that depends on the hardware build (serial settings, plausible
sensor ranges, safety thresholds) lives here so the firmware side can change
without touching the decision logic.
"""

import os

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.environ.get("BIOMON_DB", os.path.join(DATA_DIR, "monitoring.db"))

# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------
HOST = os.environ.get("BIOMON_HOST", "127.0.0.1")
PORT = int(os.environ.get("BIOMON_PORT", "8000"))

# --------------------------------------------------------------------------
# Serial / STM32 link  (configurable: no specific sensor model is assumed)
# --------------------------------------------------------------------------
SERIAL_BAUDRATE = int(os.environ.get("BIOMON_BAUD", "115200"))
SERIAL_TIMEOUT = 1.0           # seconds, read timeout
SERIAL_WRITE_TIMEOUT = 1.0
RECONNECT_DELAY = 2.0          # seconds between reconnect attempts
MAX_RECONNECT_ATTEMPTS = 0     # 0 = keep trying forever while "enabled"
STALE_AFTER = 8.0              # seconds without a packet -> link considered stale

# Command sent to the STM32 to enable / disable the add-on sensors.
# One JSON line, terminated with \n.  Firmware is free to ignore unknown keys.
EMERGENCY_CMD_TEMPLATE = {"cmd": "set_addon"}

# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------
# Continuous signals are always streamed by the board.
CONTINUOUS_SIGNALS = ["hr", "spo2", "body_temp", "ambient_temp", "humidity", "pressure"]
# Add-on signals are only meaningful once the board has been asked for them.
ADDON_SIGNALS = ["ecg", "pm25", "accel"]
ALL_SIGNALS = CONTINUOUS_SIGNALS + ADDON_SIGNALS

SIGNAL_META = {
    "hr":           {"label": "Heart rate",         "unit": "bpm"},
    "spo2":         {"label": "SpO\u2082",          "unit": "%"},
    "body_temp":    {"label": "Body temperature",   "unit": "\u00b0C"},
    "ambient_temp": {"label": "Ambient temperature", "unit": "\u00b0C"},
    "humidity":     {"label": "Humidity",           "unit": "%"},
    "pressure":     {"label": "Pressure",           "unit": "hPa"},
    "ecg":          {"label": "ECG amplitude",      "unit": "mV"},
    "pm25":         {"label": "PM2.5",              "unit": "\u00b5g/m\u00b3"},
    "accel":        {"label": "Motion",             "unit": "g"},
}

# Physically plausible range.  Anything outside this is treated as a bad
# reading: it is dropped, it never reaches the baseline, and it never
# raises an alarm on its own.
PLAUSIBLE_RANGE = {
    "hr":           (20.0, 250.0),
    "spo2":         (50.0, 100.0),
    "body_temp":    (28.0, 45.0),
    "ambient_temp": (-40.0, 85.0),
    "humidity":     (0.0, 100.0),
    "pressure":     (800.0, 1100.0),
    "ecg":          (-10.0, 10.0),
    "pm25":         (0.0, 1000.0),
    "accel":        (0.0, 16.0),
}

# Minimum standard deviation used in the personalized z-score, so an
# unusually quiet baseline cannot produce an exploding score.
STD_FLOOR = {
    "hr": 2.5, "spo2": 0.6, "body_temp": 0.12,
    "ambient_temp": 0.5, "humidity": 1.5, "pressure": 0.8,
    "ecg": 0.03, "pm25": 2.0, "accel": 0.02,
}

# Relative floor: the spread never counts as tighter than this fraction of
# the personal mean. Without it a very steady baseline turns an ordinary
# fluctuation into a huge z-score.
RELATIVE_STD_FLOOR = {
    "hr": 0.08, "spo2": 0.010, "body_temp": 0.005,
    "ambient_temp": 0.03, "humidity": 0.05, "pressure": 0.002,
}

# Above this motion level the person is considered active, so a raised heart
# rate is expected rather than alarming.
EXERTION_ACCEL = 0.8
EXERTION_HR_DAMPING = 0.25     # scale applied to the heart-rate deviation
EXERTION_HR_CEILING = 175      # above this a high heart rate still counts

# Reaching the emergency band without a hard threshold breach requires
# corroboration from more than one signal; otherwise the score is capped
# just below it.
NON_CRITICAL_SCORE_CAP = 74.0

# Population priors used until the personal baseline has enough samples.
POPULATION_PRIOR = {
    "hr":           (75.0, 9.0),
    "spo2":         (97.5, 1.2),
    "body_temp":    (36.8, 0.3),
    "ambient_temp": (28.0, 3.0),
    "humidity":     (55.0, 10.0),
    "pressure":     (1008.0, 4.0),
    "ecg":          (0.12, 0.05),
    "pm25":         (20.0, 12.0),
    "accel":        (0.05, 0.05),
}

# Signals whose baseline the system learns.  Add-on signals are episodic, so
# they are judged against absolute thresholds instead.
BASELINE_SIGNALS = CONTINUOUS_SIGNALS

BASELINE_MIN_SAMPLES = 12      # before this, priors dominate
BASELINE_MATURE_SAMPLES = 60   # personal statistics fully trusted from here
BASELINE_FREEZE_ABOVE = "ATTENTION"   # stop learning once state is worse than this

# --------------------------------------------------------------------------
# Safety thresholds (absolute, personalization-independent)
# --------------------------------------------------------------------------
# (warn_low, warn_high, crit_low, crit_high); None = no limit on that side.
SAFETY_LIMITS = {
    "hr":        {"warn": (50, 115),  "crit": (40, 145)},
    "spo2":      {"warn": (93, None), "crit": (88, None)},
    "body_temp": {"warn": (35.5, 37.9), "crit": (35.0, 39.0)},
    "pm25":      {"warn": (None, 55), "crit": (None, 150)},
    "accel":     {"warn": (None, 2.0), "crit": (None, 3.5)},
    "ecg":       {"warn": (None, 1.2), "crit": (None, 2.5)},
}

# Environmental stress (heat/humidity/air) contributes context, never an
# alarm on its own.
ENV_HEAT_INDEX_WARN = 32.0
ENV_HEAT_INDEX_HIGH = 39.0

# --------------------------------------------------------------------------
# Emergency / add-on activation
# --------------------------------------------------------------------------
ADDON_TRIGGER_SCORE = 45.0     # fuzzy score at which add-on sensors are asked for
ADDON_HOLD_SECONDS = 30.0      # keep add-ons on for at least this long
EMERGENCY_SCORE = 78.0

# Which add-on sensor answers which kind of question.
ADDON_ROUTING = {
    "cardiac":     ["ecg", "accel"],
    "respiratory": ["pm25", "ecg"],
    "thermal":     ["accel"],
    "motion":      ["accel", "ecg"],
}

# --------------------------------------------------------------------------
# Risk governor
# --------------------------------------------------------------------------
RISK_LEVELS = ["NORMAL", "ATTENTION", "HIGH RISK", "EMERGENCY"]
RISK_BANDS = [            # (upper_bound_exclusive, level)
    (30.0, "NORMAL"),
    (55.0, "ATTENTION"),
    (78.0, "HIGH RISK"),
    (1e9, "EMERGENCY"),
]
RISK_HYSTERESIS = 6.0          # score must fall this far below a band to step down
ESCALATE_CONFIRMATIONS = 1     # samples needed to move up (fast)
DEESCALATE_CONFIRMATIONS = 5   # samples needed to move down (slow, stable)
SCORE_SMOOTHING = 0.45         # EMA factor applied to the raw fuzzy score
CRITICAL_BYPASS = True         # a hard safety breach escalates immediately

# --------------------------------------------------------------------------
# Test mode
# --------------------------------------------------------------------------
VIRTUAL_PORT_NAME = "VIRTUAL"
VIRTUAL_SAMPLE_PERIOD = 1.0    # seconds between simulated packets
TEST_SCENARIOS = ["normal", "exercise", "abnormal", "emergency", "recovery", "garbage"]

# --------------------------------------------------------------------------
# History / retention
# --------------------------------------------------------------------------
HISTORY_DEFAULT_LIMIT = 200
HISTORY_MAX_LIMIT = 5000
LIVE_BUFFER_SIZE = 300
