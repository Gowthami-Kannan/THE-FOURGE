# Personalized Environment-Aware Biomedical Monitoring System

A monitoring and decision-support prototype. An STM32F401CCU6 board streams
sensor readings over USB serial; a Python backend learns what is normal *for
this person*, judges every new packet against that personal baseline plus
absolute safety limits and the surrounding environment, and shows the result
live on a web dashboard.

> This is a prototype for monitoring and decision support. It does not
> diagnose anything and makes no claim of medical certainty. "Decision
> confidence" is the system's confidence in its own output, not a medical
> probability.

---

## Run it on Windows

1. Open the project folder.
2. Double-click **`run_dashboard.bat`**.
3. The browser opens at <http://127.0.0.1:8000>.

The batch file switches to its own folder first, so it works no matter where
Windows starts it from, and installs the dependencies on the first run.

### Or from a terminal

```bat
cd path\to\project
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`python app.py` does the same thing.

---

## Try it without hardware

1. Start the server.
2. In the port list, choose **VIRTUAL — Test mode**.
3. Click **Connect**.

The header turns purple and reads **TEST MODE**. A scenario selector appears:

| Scenario | What it does |
|---|---|
| Resting, normal | Calm vitals; the personal baseline is learned here |
| Exercise | High heart rate with sound SpO₂ — should *not* read as an emergency |
| Abnormal physiological event | Deviating vitals; add-on sensors get switched on |
| Emergency | Critical thresholds breached; emergency mode and alerts fire |
| Recovery | Vitals settle; the risk level walks back down step by step |
| Invalid / malformed packets | Junk on the wire; nothing crashes, rejects are listed |

Test-mode records are stored with `source='test'` and are never mixed into the
hardware history.

## Run it with the board

1. Plug the STM32 in and note the COM port in Device Manager.
2. Pick that port in the dashboard, set the baud rate (115200 by default) and
   click **Connect**.

While nothing is connected the dashboard says **DEVICE NOT CONNECTED** and
shows no values. The system never invents readings.

---

## What the board should send

One JSON object per line (JSON Lines), newline-terminated:

```json
{"hr":78,"spo2":98,"body_temp":36.7,"ambient_temp":29.4,"humidity":58,"pressure":1008,"pm25":12,"ecg":0.12,"accel":0.03}
```

Only the continuous fields need to be streamed all the time:
`hr`, `spo2`, `body_temp`, `ambient_temp`, `humidity`, `pressure`.
`ecg`, `pm25` and `accel` are add-on sensors and should only be sampled after
the backend asks for them.

Common field-name variants (`heart_rate`, `temp`, `rh`, `pm2_5`, …) are
accepted, unknown fields are ignored, and malformed lines are counted and
shown in the dashboard instead of breaking the stream.

### Command sent back to the board

When the engine decides it needs more evidence it writes one JSON line to the
same serial port:

```json
{"cmd":"set_addon","sensors":["ecg","accel"],"enable":true,"mode":"emergency"}
```

The firmware should enable the listed sensors and start including those fields
in its packets. `{"enable":false,"sensors":[]}` returns the board to
continuous-only mode. No specific sensor part numbers are assumed anywhere —
the ranges, thresholds and baud rate all live in `config.py`.

---

## How a decision is made

```
live packet
   -> validation            reject junk, drop implausible values
   -> Welford statistics    running mean/variance per signal, per person
   -> personalized z-score  blended with a population prior while learning
   -> safety limits         absolute warning and critical thresholds
   -> add-on activation     ask the board for ECG / PM2.5 / accelerometer
   -> fuzzy inference       deviation, safety, environment, add-on evidence
   -> risk governor         fast to escalate, slow and hysteretic to relax
   -> risk level, risk score, reason, decision confidence, emergency mode
```

**Welford** keeps a numerically stable running mean and variance without
storing history. Learning is frozen whenever a reading is outside its safe
range or the level is above ATTENTION, so an event is never absorbed into
"normal for this person".

**Personalized z-score** measures deviation in units of that person's own
spread. Until enough samples exist, a population prior is blended in, so a
cold start behaves sensibly instead of wildly. The spread never counts as
tighter than a fixed floor or a fraction of the personal mean, so a very
steady baseline cannot turn an ordinary fluctuation into a huge z-score.

**Context from movement.** When the accelerometer shows sustained activity
(not an impact spike), a fast heart rate below the exertion ceiling is read as
exertion rather than an alarm, and the heart-rate deviation is damped. SpO2,
temperature and impact-level motion are judged exactly as usual, so exercise
reads as elevated while a genuine event still escalates.

**Safety limits** are absolute and independent of personalization — a SpO₂ of
84% is critical regardless of what this person usually reads. A critical
breach floors the risk score inside the emergency band.

**Fuzzy inference** combines four graded inputs (deviation, safety severity,
environmental stress, add-on evidence) through 14 rules. Rules that reach the
same conclusion are aggregated with a max, and the crisp score is the
strength-weighted average of the rule consequents, so the score moves smoothly
rather than jumping at boundaries.

Reaching the emergency band without a hard threshold breach needs
corroboration from a second system; a single deviating signal is capped just
below it.

**Risk governor** turns that score into one of NORMAL / ATTENTION / HIGH RISK /
EMERGENCY. Escalation takes one sample; de-escalation needs five consecutive
confirmations plus a hysteresis margin, and moves one step at a time. A
critical breach bypasses the delay upward.

**Decision confidence** weighs baseline maturity, how many signals arrived,
how clearly one fuzzy rule dominates, how steady the score is, and whether the
add-on sensors corroborate the finding.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | Link state, mode, port, parser counters, DB counts |
| GET | `/api/latest` | Latest decision, baseline, recent alerts |
| GET | `/api/baseline` | Learned per-signal mean, spread, sample counts |
| GET | `/api/history?limit=200&source=hardware\|test\|all` | Stored records |
| GET | `/api/alerts?limit=50` | Alert events |
| GET | `/api/ports` | COM ports, plus the VIRTUAL test port |
| POST | `/api/connect` | `{"port":"COM5","baudrate":115200,"scenario":"normal"}` |
| POST | `/api/disconnect` | Stop the link |
| POST | `/api/scenario` | Switch the test-mode scenario |
| POST | `/api/command` | Manually enable or disable add-on sensors |
| POST | `/api/reset-baseline` | Start learning the personal baseline again |
| WS | `/ws` | Live snapshot, readings, alerts, rejects, link changes |

---

## Data

SQLite, at `data/monitoring.db`, created automatically.

* `readings` — timestamp, every sensor value, z-scores, risk level, risk
  score, reason, confidence, emergency flag, add-on state, `source`
* `alerts` — escalations, emergencies, recoveries, add-on activations
* `baseline` — the learned per-signal statistics

---

## Tests

```bat
python tests\run_all.py
```

or, if pytest is installed:

```bat
pytest -q
```

Covered: Welford accuracy, baseline maturity and freezing, z-scores, safety
thresholds, governor escalation and hysteresis, the normal / exercise /
abnormal / emergency / recovery scenarios, malformed and partial packets,
missing fields, out-of-range values, serial connect failure, disconnect and
reconnect, add-on command generation, database insertion and source
separation, every REST endpoint, and live WebSocket updates.

The API and WebSocket tests skip themselves if FastAPI is not installed, so
the core engine tests still run on a bare Python.

---

## Layout

```
project/
├── app.py                  FastAPI server, REST + WebSocket
├── config.py               thresholds, ranges, serial settings, tuning
├── models.py               request/response schemas
├── packet_parser.py        JSON-Lines parsing and validation
├── serial_reader.py        COM port discovery, reading, reconnect, commands
├── virtual_device.py       test-mode packet generator (never on the live path)
├── database.py             SQLite storage
├── decision_engine.py      Welford, z-score, safety, fuzzy, governor
├── monitoring_service.py   wiring between all of the above
├── dashboard/              index.html, style.css, app.js
├── tests/                  engine, parser, service, API tests
├── requirements.txt
├── run_dashboard.bat
└── .gitignore
```

## Troubleshooting

**The port list only shows VIRTUAL.** pyserial is missing or no board is
attached. Run `pip install -r requirements.txt`, then click Rescan.

**Connect fails with "access denied".** Another program (Arduino IDE, PuTTY,
a serial monitor) already holds the COM port. Close it and try again.

**Connected but no values.** The header shows "No data — link stale" after
eight quiet seconds. Check the baud rate and that the firmware ends every
packet with a newline.

**Port 8000 is busy.** Run
`python -m uvicorn app:app --port 8080` and open <http://127.0.0.1:8080>.
