"""
recovery.py
===========
Python port of:
  - Soma/Calculators/RecoveryCalculator.swift
  - Soma/Calculators/BaselineCalculator.swift
"""

import math
from backend.validity import positive, resting_hr
from typing import Optional

MIN_DAYS_REQUIRED = 7


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def normalize_ratio(value: float, low: float, high: float) -> float:
    if low == high:
        return 50.0
    if high > low:
        return clamp((value - low) / (high - low) * 100.0, 0.0, 100.0)
    else:
        return clamp((low - value) / (low - high) * 100.0, 0.0, 100.0)


def log_hrv_stats(values: list) -> Optional[tuple]:
    """
    Recency-weighted geometric baseline + log-domain spread of an HRV series.
    HRV is log-normally distributed; industry tools (Oura, HRV4Training) work in ln-space.
    Returns (mean_ln, sd_ln), or None if fewer than MIN_DAYS_REQUIRED samples.
    'values' must be ordered oldest -> newest.
    """
    positives = [v for v in values if positive(v)]
    if len(positives) < MIN_DAYS_REQUIRED:
        return None
    lns = [math.log(v) for v in positives]
    # EWMA in log-space, alpha=0.25 -> ~7-day responsiveness
    alpha = 2.0 / (7.0 + 1.0)
    ewma = lns[0]
    for i in range(1, len(lns)):
        ewma = alpha * lns[i] + (1 - alpha) * ewma
    mean = sum(lns) / len(lns)
    variance = sum((x - mean) ** 2 for x in lns) / (len(lns) - 1)
    sd = math.sqrt(variance)
    return (ewma, sd)


def hrv_z_score(today: float, values: list) -> Optional[float]:
    """Z-score of today's HRV against personal log-domain baseline. Positive = above norm = better."""
    if not positive(today):
        return None
    stats = log_hrv_stats(values)
    if stats is None or stats[1] == 0:
        return None
    mean_ln, sd_ln = stats
    return (math.log(today) - mean_ln) / sd_ln


class RecoveryInput:
    """
    All inputs needed to compute a recovery score.
    today_hrv         : Morning HRV (rMSSD, ms). None -> defaults to 50.
    hrv_baseline      : Scalar HRV baseline (fallback when hrv_history is short).
    today_rhr         : Resting heart rate today (bpm). None -> defaults to 50.
    rhr_baseline      : Personal scalar RHR baseline.
    sleep_score       : Last night sleep score 0-100.
    yesterday_strain  : Yesterday strain 0-21 (WHOOP-style).
    acr               : Acute-to-Chronic Ratio; penalty when > 1.3.
    hrv_history       : List of recent HRV values oldest->newest. Uses z-score when >= 7.
    recovery_adjustment: Signed offset for benign physiology (e.g. menstrual cycle).
    """
    def __init__(self, today_hrv=None, hrv_baseline=None, today_rhr=None,
                 rhr_baseline=None, sleep_score=0.0, yesterday_strain=0.0,
                 acr=None, hrv_history=None, recovery_adjustment=0.0):
        self.today_hrv = today_hrv
        self.hrv_baseline = hrv_baseline
        self.today_rhr = today_rhr
        self.rhr_baseline = rhr_baseline
        self.sleep_score = sleep_score
        self.yesterday_strain = yesterday_strain
        self.acr = acr
        self.hrv_history = hrv_history
        self.recovery_adjustment = recovery_adjustment


class RecoveryCalculator:
    """
    Weights (from RecoveryCalculator.swift):
      HRV Component     40%
      RHR Component     25%
      Sleep Score       25%
      Strain Recovery   10%
    """

    @staticmethod
    def calculate(inp: RecoveryInput) -> dict:
        hrv_comp    = RecoveryCalculator._hrv_component(inp.today_hrv, inp.hrv_baseline, inp.hrv_history)
        rhr_comp    = RecoveryCalculator._rhr_component(inp.today_rhr, inp.rhr_baseline)
        sleep_comp  = clamp(inp.sleep_score, 0.0, 100.0)
        strain_comp = clamp((1.0 - inp.yesterday_strain / 21.0), 0.0, 1.0) * 100.0

        recovery = 0.40 * hrv_comp + 0.25 * rhr_comp + 0.25 * sleep_comp + 0.10 * strain_comp

        acr_penalty = 0.0
        if inp.acr is not None and inp.acr > 1.3:
            excess = min(inp.acr - 1.3, 0.7)
            acr_penalty = (excess / 0.7) * 10.0
            recovery -= acr_penalty

        recovery += inp.recovery_adjustment
        final_score = clamp(recovery, 0.0, 100.0)

        return {
            "score":            round(final_score, 2),
            "hrv_component":    round(hrv_comp, 2),
            "rhr_component":    round(rhr_comp, 2),
            "sleep_component":  round(sleep_comp, 2),
            "strain_component": round(strain_comp, 2),
            "acr_penalty":      round(acr_penalty, 2),
            "adjustment":       inp.recovery_adjustment,
        }

    @staticmethod
    def training_recommendation(recovery: float, last_3day_strain_avg: float, sleep_debt_hours: float) -> str:
        if recovery >= 67:
            base = "Peak day — push intensity. Your body is recovered."
        elif recovery >= 50:
            base = "Moderate day — steady training is fine."
        elif recovery >= 34:
            base = "Easy day — stick to low intensity."
        else:
            base = "Rest day — prioritize recovery and sleep."
        suffixes = []
        if last_3day_strain_avg > 15:
            suffixes.append("Consider a deload — high cumulative strain.")
        if sleep_debt_hours > 2:
            suffixes.append("Sleep debt is elevated — aim for extra sleep tonight.")
        return base if not suffixes else base + " " + " ".join(suffixes)

    @staticmethod
    def _hrv_component(today_hrv, baseline, history) -> float:
        """
        Primary path (>=7 days history): personal log-domain z-score.
          z=0 (at baseline) -> 50;  +2 SD -> 100;  -2 SD -> 0.
          Formula: clamp(50 + z * 25, 0, 100)
        Fallback (no/short history): ratio vs scalar baseline clamped [0.5x, 1.5x] -> [0, 100].
        """
        if not positive(today_hrv):
            return 50.0
        if history is not None:
            z = hrv_z_score(today_hrv, history)
            if z is not None:
                return clamp(50.0 + z * 25.0, 0.0, 100.0)
        if not positive(baseline):
            return 50.0
        ratio = today_hrv / baseline
        return normalize_ratio(ratio, low=0.5, high=1.5)

    @staticmethod
    def _rhr_component(today_rhr, baseline) -> float:
        """
        RHR deviation from baseline -> 0-100.
        deviation = baseline - today_rhr  (positive = RHR dropped = good).
        Band: [-10 bpm, +10 bpm] -> [0, 100].
        """
        if resting_hr(today_rhr) is None or resting_hr(baseline) is None:
            return 50.0
        deviation = baseline - today_rhr
        return normalize_ratio(deviation, low=-10.0, high=10.0)


if __name__ == "__main__":
    print("=" * 60)
    print("  RECOVERY SCORE DEMO")
    print("=" * 60)

    hrv_history = [38.0, 41.0, 36.5, 40.2, 43.1, 39.8, 42.5, 44.0, 37.9, 41.3]

    inp = RecoveryInput(
        today_hrv=44.0,
        hrv_baseline=None,
        today_rhr=52.0,
        rhr_baseline=56.0,
        sleep_score=72.7,
        yesterday_strain=11.0,
        acr=None,
        hrv_history=hrv_history,
        recovery_adjustment=0.0,
    )

    r = RecoveryCalculator.calculate(inp)

    print(f"\n  Recovery Score : {r['score']:.1f} / 100")
    print("\n  --- Component Breakdown ---")
    print(f"  HRV Component   (40%) : {r['hrv_component']:6.1f}  -> {0.40 * r['hrv_component']:5.2f} pts")
    print(f"  RHR Component   (25%) : {r['rhr_component']:6.1f}  -> {0.25 * r['rhr_component']:5.2f} pts")
    print(f"  Sleep Component (25%) : {r['sleep_component']:6.1f}  -> {0.25 * r['sleep_component']:5.2f} pts")
    print(f"  Strain Recovery (10%) : {r['strain_component']:6.1f}  -> {0.10 * r['strain_component']:5.2f} pts")
    if r['acr_penalty'] > 0:
        print(f"  ACR Penalty           : -{r['acr_penalty']:.2f} pts")
    print(f"  Adjustment            :  {r['adjustment']:+.2f} pts")
    print(f"  {'-'*40}")
    print(f"  Final Score           : {r['score']:.2f} / 100")
    rec = RecoveryCalculator.training_recommendation(r['score'], 12.0, 1.5)
    print(f"\n  Training Recommendation: {rec}")
    print("=" * 60)
