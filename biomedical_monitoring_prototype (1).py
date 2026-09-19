"""
Personalized Environment-Aware Biomedical Monitoring System
Standalone Python prototype

Pipeline:
Continuous vitals -> personal baseline (Welford) -> Z-score [-5, +5]
-> safety/risk trigger -> emergency sensor activation
-> fuzzy risk decision -> risk + reason + confidence

This is an educational/prototype decision-support system.
It is NOT a clinically validated diagnostic device.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================
# CONFIGURATION
# ============================================================

BASELINE_SECONDS = 10
TICK_SECONDS = 0.5

Z_LIMIT = 5.0
FLAG_Z = 2.0

# Prototype safety thresholds. These are NOT clinical thresholds.
SPO2_CRITICAL = 90.0
HR_LOW_CRITICAL = 45.0
HR_HIGH_CRITICAL = 140.0
TEMP_HIGH_CRITICAL = 39.0

RISK_RANK = {
    "NORMAL": 0,
    "ATTENTION": 1,
    "HIGH RISK": 2,
    "EMERGENCY": 3,
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_std(variance: float) -> float:
    """Prevent division by an almost-zero standard deviation."""
    return max(math.sqrt(max(variance, 0.0)), 0.05)


# ============================================================
# WELFORD PERSONAL BASELINE
# ============================================================

@dataclass
class Welford:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2

    @property
    def variance(self) -> float:
        if self.count < 2:
            return 0.0
        return self.m2 / (self.count - 1)

    @property
    def std(self) -> float:
        return safe_std(self.variance)

    def z_score(self, value: float) -> float:
        if self.count < 2:
            return 0.0
        z = (value - self.mean) / self.std
        return clamp(z, -Z_LIMIT, Z_LIMIT)


@dataclass
class PersonalBaseline:
    hr: Welford = field(default_factory=Welford)
    spo2: Welford = field(default_factory=Welford)
    body_temp: Welford = field(default_factory=Welford)
    ambient_temp: Welford = field(default_factory=Welford)
    humidity: Welford = field(default_factory=Welford)

    ready: bool = False

    def learn(self, sample: Dict[str, float]) -> None:
        self.hr.update(sample["hr"])
        self.spo2.update(sample["spo2"])
        self.body_temp.update(sample["body_temp"])
        self.ambient_temp.update(sample["ambient_temp"])
        self.humidity.update(sample["humidity"])

    def finish(self) -> None:
        self.ready = True

    def z_scores(self, sample: Dict[str, float]) -> Dict[str, float]:
        return {
            "hr_z": self.hr.z_score(sample["hr"]),
            "spo2_z": self.spo2.z_score(sample["spo2"]),
            "temp_z": self.body_temp.z_score(sample["body_temp"]),
            "ambient_temp_z": self.ambient_temp.z_score(sample["ambient_temp"]),
            "humidity_z": self.humidity.z_score(sample["humidity"]),
        }

    def summary(self) -> str:
        return (
            f"HR={self.hr.mean:.1f}±{self.hr.std:.1f}, "
            f"SpO2={self.spo2.mean:.1f}±{self.spo2.std:.1f}, "
            f"BodyTemp={self.body_temp.mean:.2f}±{self.body_temp.std:.2f}"
        )


# ============================================================
# SIMULATED SENSOR DATA
# ============================================================

@dataclass
class Scenario:
    name: str
    hr_delta: float = 0.0
    spo2_delta: float = 0.0
    body_temp_delta: float = 0.0
    ambient_temp: float = 28.0
    humidity: float = 55.0
    pm25: Optional[float] = None
    ecg_abnormality: Optional[float] = None
    accel_rms: Optional[float] = None
    fall: bool = False
    description: str = ""


def make_sensor_sample(
    baseline: PersonalBaseline,
    scenario: Scenario,
    rng: random.Random,
) -> Dict[str, float]:
    """Create one simulated sensor reading."""

    hr = baseline.hr.mean + scenario.hr_delta + rng.gauss(0, 1.0)
    spo2 = baseline.spo2.mean + scenario.spo2_delta + rng.gauss(0, 0.25)
    body_temp = baseline.body_temp.mean + scenario.body_temp_delta + rng.gauss(0, 0.04)

    return {
        "hr": hr,
        "spo2": spo2,
        "body_temp": body_temp,
        "ambient_temp": scenario.ambient_temp + rng.gauss(0, 0.3),
        "humidity": scenario.humidity + rng.gauss(0, 1.0),
        "pm25": scenario.pm25,
        "ecg_abnormality": scenario.ecg_abnormality,
        "accel_rms": scenario.accel_rms,
        "fall": scenario.fall,
    }


# ============================================================
# EMERGENCY SENSOR CONTROL
# ============================================================

class EmergencySensors:
    """
    Prototype representation of GPIO/enable control.

    In hardware, the STM32 would control sensor enable pins or
    a suitable power-control circuit. It should not directly
    power a high-current sensor from a GPIO pin.
    """

    def __init__(self) -> None:
        self.active = False

    def power_on(self) -> None:
        if not self.active:
            self.active = True
            print("  [ACTION] Emergency Mode ON")
            print("  [ACTION] ECG + PM2.5 + Accelerometer activated")

    def power_off(self) -> None:
        if self.active:
            self.active = False
            print("  [ACTION] Emergency Mode OFF")
            print("  [ACTION] Additional sensors returned to standby")


# ============================================================
# SAFETY / INITIAL RISK TRIGGER
# ============================================================

def initial_risk_trigger(sample: Dict[str, float], z: Dict[str, float]) -> Tuple[bool, List[str]]:
    """
    Conservative trigger for activating the additional sensors.

    One unusual value alone is not automatically treated as an
    emergency. The trigger is intended to start deeper assessment.
    """

    reasons: List[str] = []

    hr_abnormal = abs(z["hr_z"]) >= FLAG_Z
    spo2_abnormal = z["spo2_z"] <= -FLAG_Z
    temp_abnormal = abs(z["temp_z"]) >= FLAG_Z

    critical = (
        sample["spo2"] <= SPO2_CRITICAL
        or sample["hr"] <= HR_LOW_CRITICAL
        or sample["hr"] >= HR_HIGH_CRITICAL
        or sample["body_temp"] >= TEMP_HIGH_CRITICAL
    )

    abnormal_count = int(hr_abnormal) + int(spo2_abnormal) + int(temp_abnormal)

    if hr_abnormal:
        reasons.append(f"HR {z['hr_z']:+.1f}σ")
    if spo2_abnormal:
        reasons.append(f"SpO2 {z['spo2_z']:+.1f}σ")
    if temp_abnormal:
        reasons.append(f"Temp {z['temp_z']:+.1f}σ")
    if critical:
        reasons.append("critical safety threshold")

    # Deeper sensing starts for critical readings or multiple
    # personalized deviations.
    trigger = critical or abnormal_count >= 2
    return trigger, reasons


# ============================================================
# FUZZY LOGIC
# ============================================================

def fuzzy_low(x: float) -> float:
    """Membership in LOW for a 0..1 abnormality value."""
    if x <= 0.20:
        return 1.0
    if x >= 0.50:
        return 0.0
    return (0.50 - x) / 0.30


def fuzzy_medium(x: float) -> float:
    """Membership in MEDIUM for a 0..1 abnormality value."""
    if x <= 0.20 or x >= 0.80:
        return 0.0
    if x < 0.50:
        return (x - 0.20) / 0.30
    return (0.80 - x) / 0.30


def fuzzy_high(x: float) -> float:
    """Membership in HIGH for a 0..1 abnormality value."""
    if x <= 0.50:
        return 0.0
    if x >= 0.80:
        return 1.0
    return (x - 0.50) / 0.30


def fuzzy_risk(
    physio_abnormality: float,
    ecg_abnormality: float,
    environment_risk: float,
    fall_signal: float,
    safety_signal: float,
) -> Dict[str, float | str]:
    """
    Explainable fuzzy-style decision layer.

    Inputs are normalized to 0..1.
    The final risk score is a weighted aggregation followed by
    linguistic membership rules.
    """

    physio_abnormality = clamp(physio_abnormality, 0, 1)
    ecg_abnormality = clamp(ecg_abnormality, 0, 1)
    environment_risk = clamp(environment_risk, 0, 1)
    fall_signal = clamp(fall_signal, 0, 1)
    safety_signal = clamp(safety_signal, 0, 1)

    # Linguistic memberships.
    p_high = fuzzy_high(physio_abnormality)
    e_high = fuzzy_high(ecg_abnormality)
    env_med = fuzzy_medium(environment_risk)
    env_high = fuzzy_high(environment_risk)

    # Fuzzy rules.
    rule_attention = max(
        fuzzy_medium(physio_abnormality),
        env_med,
    )

    rule_high = max(
        min(p_high, max(e_high, env_med)),
        safety_signal * 0.8,
    )

    rule_emergency = max(
        min(p_high, e_high),
        min(p_high, fall_signal),
        min(safety_signal, max(e_high, fall_signal)),
        min(p_high, env_high, e_high),
    )

    # Defuzzified risk score.
    score = (
        0.38 * physio_abnormality
        + 0.30 * ecg_abnormality
        + 0.10 * environment_risk
        + 0.12 * fall_signal
        + 0.10 * safety_signal
    )

    score = clamp(score, 0, 1)

    if rule_emergency >= 0.70 or (score >= 0.65 and safety_signal > 0):
        label = "EMERGENCY"
    elif rule_high >= 0.55 or score >= 0.45:
        label = "HIGH RISK"
    elif rule_attention >= 0.35 or score >= 0.25:
        label = "ATTENTION"
    else:
        label = "NORMAL"

    return {
        "label": label,
        "score": score,
        "rule_attention": rule_attention,
        "rule_high": rule_high,
        "rule_emergency": rule_emergency,
    }


# ============================================================
# RISK ENGINE
# ============================================================

def calculate_risk(
    sample: Dict[str, float],
    z: Dict[str, float],
    emergency_mode: bool,
) -> Dict[str, object]:

    # Personalized physiological abnormality.
    hr_ab = clamp(abs(z["hr_z"]) / 4.0, 0, 1)
    spo2_ab = clamp(max(0.0, -z["spo2_z"]) / 4.0, 0, 1)
    temp_ab = clamp(abs(z["temp_z"]) / 4.0, 0, 1)

    physio = (
        0.35 * hr_ab
        + 0.45 * spo2_ab
        + 0.20 * temp_ab
    )

    # ECG only becomes available in Emergency Mode.
    ecg = (
        float(sample["ecg_abnormality"])
        if emergency_mode and sample["ecg_abnormality"] is not None
        else 0.0
    )

    # Environment risk.
    pm25 = sample["pm25"] if emergency_mode else None
    pm_risk = (
        clamp((float(pm25) - 35.0) / 115.0, 0, 1)
        if pm25 is not None
        else 0.0
    )

    ambient_heat = clamp((sample["ambient_temp"] - 32.0) / 12.0, 0, 1)
    environment = max(pm_risk, ambient_heat)

    fall = 1.0 if emergency_mode and sample["fall"] else 0.0

    safety = 0.0
    if sample["spo2"] <= SPO2_CRITICAL:
        safety = max(safety, 1.0)
    if sample["hr"] <= HR_LOW_CRITICAL or sample["hr"] >= HR_HIGH_CRITICAL:
        safety = max(safety, 1.0)
    if sample["body_temp"] >= TEMP_HIGH_CRITICAL:
        safety = max(safety, 0.8)

    result = fuzzy_risk(
        physio_abnormality=physio,
        ecg_abnormality=ecg,
        environment_risk=environment,
        fall_signal=fall,
        safety_signal=safety,
    )

    reasons: List[str] = []

    if abs(z["hr_z"]) >= FLAG_Z:
        reasons.append(f"HR {z['hr_z']:+.1f}σ")
    if z["spo2_z"] <= -FLAG_Z:
        reasons.append(f"SpO2 {z['spo2_z']:+.1f}σ")
    if abs(z["temp_z"]) >= FLAG_Z:
        reasons.append(f"Body temperature {z['temp_z']:+.1f}σ")

    if emergency_mode and ecg >= 0.5:
        reasons.append("irregular ECG pattern")

    if emergency_mode and pm25 is not None and pm25 >= 35:
        reasons.append(f"PM2.5 {pm25:.0f}")

    if emergency_mode and fall:
        reasons.append("fall/unusual movement")

    if safety > 0:
        reasons.append("safety threshold exceeded")

    if not reasons:
        reasons.append("within personal baseline range")

    # Confidence is a system decision-confidence heuristic, NOT
    # a calibrated medical probability.
    available = 4 + int(emergency_mode) * 3
    margin = min(
        abs(float(result["score"]) - 0.25),
        abs(float(result["score"]) - 0.45),
        abs(float(result["score"]) - 0.65),
    )

    confidence = clamp(
        0.50 + 0.06 * available + 0.80 * margin,
        0.50,
        0.95,
    )

    result["reason"] = ", ".join(reasons)
    result["confidence"] = confidence
    result["physio_abnormality"] = physio
    result["ecg_abnormality"] = ecg
    result["environment_risk"] = environment
    result["fall_signal"] = fall
    result["safety_signal"] = safety

    return result


# ============================================================
# ANTI-FLAPPING RISK GOVERNOR
# ============================================================

class RiskGovernor:
    """
    Prevents rapid switching between risk labels.

    Escalation requires 2 consecutive higher-risk readings.
    De-escalation requires 6 consecutive lower-risk readings.
    """

    def __init__(self) -> None:
        self.current = "NORMAL"
        self.up_count = 0
        self.down_count = 0

    def reset(self) -> None:
        self.current = "NORMAL"
        self.up_count = 0
        self.down_count = 0

    def update(self, candidate: str) -> str:
        current_rank = RISK_RANK[self.current]
        candidate_rank = RISK_RANK[candidate]

        if candidate_rank > current_rank:
            self.up_count += 1
            self.down_count = 0
            if self.up_count >= 2:
                self.current = candidate
                self.up_count = 0

        elif candidate_rank < current_rank:
            self.down_count += 1
            self.up_count = 0
            if self.down_count >= 6:
                self.current = candidate
                self.down_count = 0

        else:
            self.up_count = 0
            self.down_count = 0

        return self.current


# ============================================================
# PERSONALIZED MONITOR
# ============================================================

class Monitor:
    def __init__(self, seed: int = 7) -> None:
        self.rng = random.Random(seed)
        self.baseline = PersonalBaseline()
        self.emergency_sensors = EmergencySensors()
        self.governor = RiskGovernor()
        self.previous_label = "NORMAL"

    def create_baseline(self) -> None:
        print("\n=== PERSONAL BASELINE LEARNING ===")
        print(f"Learning stable readings for approximately {BASELINE_SECONDS} seconds...")

        samples = int(BASELINE_SECONDS / TICK_SECONDS)

        for _ in range(samples):
            sample = {
                "hr": 72 + self.rng.gauss(0, 1.0),
                "spo2": 98 + self.rng.gauss(0, 0.15),
                "body_temp": 36.7 + self.rng.gauss(0, 0.03),
                "ambient_temp": 27.0 + self.rng.gauss(0, 0.2),
                "humidity": 55 + self.rng.gauss(0, 0.8),
            }
            self.baseline.learn(sample)

        self.baseline.finish()

        print("Baseline ready.")
        print("Personal baseline:", self.baseline.summary())

    def run_scenario(
        self,
        scenario: Scenario,
        ticks: int = 12,
    ) -> Dict[str, object]:

        print(f"\n--- Scenario: {scenario.name} ---")
        print(scenario.description)

        self.governor.reset()
        self.previous_label = "NORMAL"

        emergency_triggered = False
        peak_rank = 0
        peak_label = "NORMAL"
        peak_confidence = 0.0
        peak_reason = ""

        for tick in range(ticks):
            sample = make_sensor_sample(self.baseline, scenario, self.rng)
            z = self.baseline.z_scores(sample)

            if not emergency_triggered:
                trigger, trigger_reasons = initial_risk_trigger(sample, z)

                if trigger:
                    emergency_triggered = True
                    print(
                        "  [TRIGGER] Deeper assessment started:",
                        ", ".join(trigger_reasons),
                    )
                    self.emergency_sensors.power_on()

            risk = calculate_risk(
                sample,
                z,
                emergency_mode=emergency_triggered,
            )

            candidate = str(risk["label"])
            label = self.governor.update(candidate)

            rank = RISK_RANK[label]

            if rank > peak_rank:
                peak_rank = rank
                peak_label = label
                peak_confidence = float(risk["confidence"])
                peak_reason = str(risk["reason"])

            if label != self.previous_label:
                print(
                    f"  [RISK] {self.previous_label} -> {label} "
                    f"| score={float(risk['score']):.2f} "
                    f"| confidence={float(risk['confidence']):.0%}"
                )
                print(f"  [REASON] {risk['reason']}")

                if label == "EMERGENCY":
                    print("  [ALERT] Emergency risk detected.")

                self.previous_label = label

        self.emergency_sensors.power_off()

        return {
            "scenario": scenario.name,
            "peak_label": peak_label,
            "peak_confidence": peak_confidence,
            "peak_reason": peak_reason,
            "emergency_mode": emergency_triggered,
        }


# ============================================================
# TEST SCENARIOS
# ============================================================

def build_scenarios() -> List[Scenario]:
    return [
        Scenario(
            name="Normal",
            description="Stable readings close to the personal baseline.",
        ),
        Scenario(
            name="Exercise",
            hr_delta=18,
            accel_rms=0.45,
            description="Heart rate rises with high activity; other signals remain stable.",
        ),
        Scenario(
            name="Heat Stress",
            hr_delta=12,
            body_temp_delta=0.45,
            ambient_temp=39,
            humidity=60,
            description="High ambient heat with elevated HR and body temperature.",
        ),
        Scenario(
            name="High PM2.5",
            hr_delta=5,
            spo2_delta=-1.2,
            ambient_temp=31,
            humidity=65,
            pm25=145,
            description="High particulate exposure with a personalized SpO2 decrease.",
        ),
        Scenario(
            name="SpO2 Drop + HR Change",
            hr_delta=28,
            spo2_delta=-5.5,
            description="Multiple personalized physiological deviations.",
        ),
        Scenario(
            name="Abnormal ECG",
            hr_delta=16,
            spo2_delta=-1.0,
            ecg_abnormality=0.90,
            pm25=40,
            accel_rms=0.10,
            description="Abnormal ECG pattern combined with physiological deviation.",
        ),
        Scenario(
            name="Fall / Emergency",
            hr_delta=32,
            spo2_delta=-6.0,
            ecg_abnormality=0.85,
            pm25=80,
            accel_rms=0.02,
            fall=True,
            description="Fall/unusual movement with multiple abnormal signals.",
        ),
    ]


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("=" * 68)
    print("PERSONALIZED ENVIRONMENT-AWARE BIOMEDICAL MONITORING")
    print("=" * 68)
    print("Prototype pipeline:")
    print("Baseline -> Welford -> Z-score [-5,+5] -> Safety Trigger")
    print("-> Emergency Sensors -> Fuzzy Logic -> Risk + Reason + Confidence")
    print("\nNote: Prototype only; thresholds are unvalidated.")

    monitor = Monitor(seed=7)
    monitor.create_baseline()

    results: List[Dict[str, object]] = []

    for scenario in build_scenarios():
        results.append(monitor.run_scenario(scenario))

    print("\n" + "=" * 68)
    print("SCENARIO SUMMARY")
    print("=" * 68)

    for result in results:
        print(
            f"{str(result['scenario']):<24} "
            f"Peak: {str(result['peak_label']):<10} "
            f"Confidence: {float(result['peak_confidence']):.0%} "
            f"Emergency Mode: {result['emergency_mode']}"
        )
        print(f"  Reason: {result['peak_reason']}")

    print("\nPrototype execution completed.")


if __name__ == "__main__":
    main()
