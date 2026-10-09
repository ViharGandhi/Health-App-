"""
Sleep Score Calculation — Python port of Soma's Swift calculators (Modified).

Modifications:
  1. Stage Mix Score compares stage durations against `sleep_need` as denominator
     (rather than actual sleep got).
  2. Adjusted Weights:
     - Sleeping HRV: 5% (was 10%)
     - Sleeping HR: 5% (was 8%)
     - HR Dip: 18% (was 10%)
     - Duration: 27% (was 25%, absorbed 2% from Sleep Efficiency)
     - Stage Mix: 20%
     - Sleep Efficiency: 10% (was 12%)
     - Restfulness (WASO): 15% (was 10%, absorbed 5% from Latency)
     Total: 100%
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers (from BaselineCalculator.swift)
# ──────────────────────────────────────────────────────────────────────────────

def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp *value* into [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def normalize_ratio(value: float, low: float, high: float) -> float:
    """
    Normalize a ratio clamped to [low, high] → 0–100.
    Supports inverted ranges where high < low (e.g. sleeping HR where lower
    is better).
    """
    if low == high:
        return 50.0  # Default to neutral if range is invalid

    if high > low:
        # Standard range: low maps to 0, high maps to 100
        return clamp((value - low) / (high - low) * 100.0, 0.0, 100.0)
    else:
        # Inverted range: low maps to 100, high maps to 0 (lower is better)
        return clamp((low - value) / (low - high) * 100.0, 0.0, 100.0)


MIN_DAYS_REQUIRED = 7


def compute_baseline(history: List[Tuple[datetime, float]]) -> Optional[float]:
    """
    Generic rolling-mean baseline from any (date, value) history.
    Used for sleeping HR, sleeping HRV, sleep duration, etc.
    """
    if not history:
        return None
    values = [v for _, v in history]
    return sum(values) / len(values)


def log_hrv_stats(values: List[float]) -> Optional[Tuple[float, float]]:
    """
    Recency-weighted geometric baseline + log-domain spread of an HRV series.

    HRV (rMSSD / SDNN) is log-normally distributed — working in ln-space
    avoids distortion at both tails.

    Returns (mean_ln, sd_ln) or None if fewer than MIN_DAYS_REQUIRED positive
    samples.  *values* must be ordered oldest → newest.
    """
    positives = [v for v in values if math.isfinite(v) and v > 0]
    if len(positives) < MIN_DAYS_REQUIRED:
        return None

    lns = [math.log(v) for v in positives]

    # EWMA of ln, alpha tuned for ~7-day responsiveness.
    alpha = 2.0 / (7.0 + 1.0)  # 0.25
    ewma = lns[0]
    for i in range(1, len(lns)):
        ewma = alpha * lns[i] + (1 - alpha) * ewma

    # Sample standard deviation of ln across the window.
    mean = sum(lns) / len(lns)
    variance = sum((x - mean) ** 2 for x in lns) / (len(lns) - 1)
    sd = math.sqrt(variance)
    return (ewma, sd)


def hrv_z_score(today: float, values: List[float]) -> Optional[float]:
    """
    Z-score of today's HRV against the personal log-domain baseline.
    Positive = HRV above personal norm (better recovery).
    """
    if not math.isfinite(today) or today <= 0:
        return None
    stats = log_hrv_stats(values)
    if stats is None or stats[1] <= 0:
        return None
    return (math.log(today) - stats[0]) / stats[1]


# ──────────────────────────────────────────────────────────────────────────────
# SleepData model (from SleepData.swift)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SleepData:
    """Mirror of the Swift SleepData struct. Durations are in *seconds*."""

    total_duration: float         # seconds (deep + rem + core)
    deep_sleep_duration: float
    rem_sleep_duration: float
    core_sleep_duration: float
    awake_duration: float
    in_bed_duration: float
    sleep_start_time: Optional[datetime]   # night sleep only
    sleep_end_time: Optional[datetime]     # night sleep only
    interruption_count: int                # distinct awake segments

    # Daytime nap data (10 AM – 8 PM on the target date)
    nap_duration_seconds: float = 0.0
    nap_start_time: Optional[datetime] = None
    nap_end_time: Optional[datetime] = None

    # Sleep onset latency
    sleep_latency_seconds: Optional[float] = None  # seconds from in-bed to first sleep onset

    # — convenience properties —

    @property
    def total_duration_hours(self) -> float:
        return self.total_duration / 3600.0

    @property
    def deep_percentage(self) -> float:
        return self.deep_sleep_duration / self.total_duration if self.total_duration > 0 else 0.0

    @property
    def rem_percentage(self) -> float:
        return self.rem_sleep_duration / self.total_duration if self.total_duration > 0 else 0.0

    @property
    def core_percentage(self) -> float:
        return self.core_sleep_duration / self.total_duration if self.total_duration > 0 else 0.0

    @classmethod
    def empty(cls) -> "SleepData":
        return cls(
            total_duration=0,
            deep_sleep_duration=0,
            rem_sleep_duration=0,
            core_sleep_duration=0,
            awake_duration=0,
            in_bed_duration=0,
            sleep_start_time=None,
            sleep_end_time=None,
            interruption_count=0,
        )


# ──────────────────────────────────────────────────────────────────────────────
# SleepCalculator (from SleepCalculator.swift)
# ──────────────────────────────────────────────────────────────────────────────

class SleepCalculator:
    """Calculates sleep score 0–100 plus sleep-need & debt helpers."""

    # Optimal stage targets (as fraction of sleep need)
    OPTIMAL_DEEP_RATIO: float = 0.20   # 20%
    OPTIMAL_REM_RATIO: float  = 0.20   # 20%
    OPTIMAL_CORE_RATIO: float = 0.50   # 50%

    @staticmethod
    def compute_duration_score(total_hours: float, sleep_need: float,
                               steepness: float = 8.0, midpoint: float = 0.75) -> float:
        """Approved rescaling: the original sigmoid reaches 100 at need."""
        if total_hours <= 0 or sleep_need <= 0:
            return 0.0
        ratio = total_hours / sleep_need
        if ratio <= 1.0:
            raw = 100.0 / (1.0 + math.exp(-steepness * (ratio - midpoint)))
            at_need = 100.0 / (1.0 + math.exp(-steepness * (1.0 - midpoint)))
            return raw / at_need * 100.0
        if ratio <= 1.10:
            return 100.0
        return max(30.0, 100.0 - (ratio - 1.10) * 75.0)

    # ── age-adjusted deep target ──

    @staticmethod
    def optimal_deep_ratio(age: Optional[int] = None) -> float:
        """
        Age-adjusted deep-sleep target.
        Targets 20 % up to age 30, then eases ~0.2 pp/yr, floored at 10 %.
        Returns the baseline 20 % when age is unknown.
        """
        if age is None or age <= 30:
            return SleepCalculator.OPTIMAL_DEEP_RATIO
        reduced = SleepCalculator.OPTIMAL_DEEP_RATIO - (age - 30) * 0.002
        return max(0.10, reduced)

    # ── sub-component helpers ──

    @staticmethod
    def compute_sleeping_hrv_score(
        sleeping_hrv: Optional[float] = None,
        baseline: Optional[float] = None,
    ) -> float:
        """HRV during sleep (higher = better; ratio vs baseline)."""
        if sleeping_hrv is None or baseline is None or baseline <= 0:
            return 50.0
        # ratio in [0.7, 1.3] → score [0, 100]
        return normalize_ratio(sleeping_hrv / baseline, low=0.7, high=1.3)

    @staticmethod
    def compute_sleeping_hr_score(
        sleeping_hr: Optional[float] = None,
        baseline: Optional[float] = None,
    ) -> float:
        """Heart rate during sleep (lower = better; inverted ratio vs baseline)."""
        if sleeping_hr is None or baseline is None or baseline <= 0:
            return 50.0
        # ratio in [0.7, 1.3] → score [100, 0] (inverted)
        ratio = sleeping_hr / baseline
        return normalize_ratio(ratio, low=1.3, high=0.7)

    @staticmethod
    def compute_interruption_score(count: int) -> float:
        """Each interruption costs 15 points; floor at 0."""
        return max(0.0, 100.0 - count * 15.0)

    @staticmethod
    def compute_restfulness_score(sleep: SleepData) -> float:
        """
        WASO-based restfulness score (replaces raw interruption count).
        Uses Wake After Sleep Onset (total awake duration) as the primary
        signal with exponential decay, plus a mild penalty for the number
        of distinct awakenings.
        """
        waso_minutes = sleep.awake_duration / 60.0
        waso_score = 100.0 * math.exp(-0.035 * waso_minutes)
        interrupt_penalty = min(15.0, sleep.interruption_count * 2.5)
        return clamp(waso_score - interrupt_penalty, 0.0, 100.0)

    @staticmethod
    def compute_sleep_efficiency_score(sleep: SleepData) -> float:
        """
        Sleep efficiency: time_asleep / time_in_bed.
        Maps efficiency  0.70 → score 0,  0.95 → score 100.
        """
        if sleep.in_bed_duration <= 0 or sleep.total_duration <= 0:
            return 50.0
        efficiency = sleep.total_duration / sleep.in_bed_duration
        return normalize_ratio(efficiency, low=0.70, high=0.95)

    @staticmethod
    def compute_hr_dip_score(
        sleeping_hr: Optional[float] = None,
        waking_hr: Optional[float] = None,
    ) -> float:
        """
        Heart-rate dip score.
        Measures the percentage drop from average waking HR to average sleeping HR.
        Maps dip  0 % → score 0,  25 % → score 100.
        """
        if sleeping_hr is None or waking_hr is None or waking_hr <= 0:
            return 50.0
        dip_pct = (waking_hr - sleeping_hr) / waking_hr * 100.0
        return normalize_ratio(dip_pct, low=0.0, high=25.0)

    @staticmethod
    def compute_sleep_latency_score(
        latency_seconds: Optional[float] = None,
    ) -> float:
        """
        Bidirectional sleep-latency score (Oura approach).
        Optimal range: 10–20 minutes → score 100.
        Too fast (< 5 min) → penalized.
        Too slow (> 30 min) → penalized.
        """
        if latency_seconds is None:
            return 50.0
        lat_min = latency_seconds / 60.0

        if 10.0 <= lat_min <= 20.0:
            return 100.0
        elif lat_min < 10.0:
            if lat_min < 5.0:
                return 50.0 + (lat_min / 5.0) * 25.0
            return 75.0 + ((lat_min - 5.0) / 5.0) * 25.0
        else:
            return clamp(100.0 - ((lat_min - 20.0) / 25.0) * 100.0, 0.0, 100.0)

    # ── main score ──

    @staticmethod
    def calculate_score(
        sleep: SleepData,
        sleep_need: float,
        sleeping_hrv: Optional[float] = None,
        sleeping_hr: Optional[float] = None,
        waking_hr: Optional[float] = None,
        hrv_baseline: Optional[float] = None,
        sleeping_hr_baseline: Optional[float] = None,
        age: Optional[int] = None,
        duration_steepness: float = 8.0,
        duration_midpoint: float = 0.75,
    ) -> float:
        """
        Calculates sleep score 0–100.

        Updated Weights:
          Duration        (27 %): sigmoid curve for undersleep, plateau + oversleep penalty
          Stage mix       (20 %): deep/REM/core vs optimal target based on sleep_need
          Sleep Efficiency(10 %): time_asleep / time_in_bed (reduced to 10%)
          Sleeping HRV    ( 5 %): sleeping HRV relative to baseline (reduced to 5%)
          Sleeping HR     ( 5 %): sleeping HR relative to baseline (reduced to 5%)
          HR Dip          (18 %): % drop from waking HR to sleeping HR (increased to 18%)
          Restfulness     (15 %): WASO-based + interruption count (increased to 15%)

        Duration scoring uses a sigmoid function for undersleep instead of a
        linear ramp.  The sigmoid is gentle near full sleep, drops steeply
        around 75 % of sleep need (the clinically meaningful deprivation
        threshold), and flattens again at severe deprivation rather than
        crashing to 0.

        Parameters
        ----------
        duration_steepness : float
            Controls how sharply the sigmoid drops around the midpoint.
            Higher = steeper transition.  Default 8.0.
        duration_midpoint : float
            The ratio (actual / need) at which the sigmoid's inflection
            point sits.  Default 0.75 (75 % of sleep need).
        """
        night_hours = sleep.total_duration / 3600.0
        nap_hours = sleep.nap_duration_seconds / 3600.0
        total_hours = night_hours + nap_hours

        if total_hours <= 0 or sleep_need <= 0:
            return 0.0

        # 1. Duration — sigmoid for undersleep, plateau + oversleep penalty
        duration_score = SleepCalculator.compute_duration_score(total_hours, sleep_need,
                                                               duration_steepness, duration_midpoint)

        # 2. Stage quality — compares stage durations against sleep_need as denominator
        sleep_need_seconds = sleep_need * 3600.0
        if sleep_need_seconds > 0:
            deep_ratio = sleep.deep_sleep_duration / sleep_need_seconds
            rem_ratio = sleep.rem_sleep_duration / sleep_need_seconds
            core_ratio = sleep.core_sleep_duration / sleep_need_seconds

            deep_target = SleepCalculator.optimal_deep_ratio(age)
            deep_score = min(100.0, deep_ratio / deep_target * 100.0)
            rem_score = min(100.0, rem_ratio / SleepCalculator.OPTIMAL_REM_RATIO * 100.0)
            core_score = min(100.0, core_ratio / SleepCalculator.OPTIMAL_CORE_RATIO * 100.0)
            stage_score = 0.40 * deep_score + 0.40 * rem_score + 0.20 * core_score
        else:
            stage_score = 0.0

        # 3. Sleep Efficiency
        efficiency_score = SleepCalculator.compute_sleep_efficiency_score(sleep)

        # 4. HRV during sleep (reduced weight to 5%)
        hrv_score = SleepCalculator.compute_sleeping_hrv_score(sleeping_hrv, hrv_baseline)

        # 5. Heart rate during sleep (reduced weight to 5%)
        hr_score = SleepCalculator.compute_sleeping_hr_score(sleeping_hr, sleeping_hr_baseline)

        # 6. Heart Rate Dip (increased weight to 18%)
        effective_waking_hr = waking_hr if waking_hr is not None else sleeping_hr_baseline
        hr_dip_score = SleepCalculator.compute_hr_dip_score(sleeping_hr, effective_waking_hr)

        # 7. Restfulness — WASO-based (increased to 15%)
        restfulness_score = SleepCalculator.compute_restfulness_score(sleep)

        score = (
            0.27 * duration_score
            + 0.20 * stage_score
            + 0.10 * efficiency_score
            + 0.05 * hrv_score
            + 0.05 * hr_score
            + 0.18 * hr_dip_score
            + 0.15 * restfulness_score
        )

        return clamp(score, 0.0, 100.0)

    # ── sleep need ──

    @staticmethod
    def calculate_sleep_need(
        baseline_sleep: float = 7.0,
        recent_need_vs_actual: Optional[List[Tuple[float, float]]] = None,
        yesterday_strain: float = 0.0,
    ) -> float:
        """Calculates sleep need in hours."""
        if recent_need_vs_actual is None:
            recent_need_vs_actual = []

        if not recent_need_vs_actual:
            debt_per_night = 0.0
        else:
            total_debt = sum(max(0.0, baseline_sleep - actual) for _, actual in recent_need_vs_actual)
            debt_per_night = total_debt / len(recent_need_vs_actual)

        strain_factor = (yesterday_strain / 21.0) * 0.5
        need = baseline_sleep + debt_per_night + strain_factor
        return clamp(need, 7.0, 9.5)

    # ── sleep debt ──

    @staticmethod
    def compute_sleep_debt(need_vs_actual: List[Tuple[float, float]]) -> float:
        """Total sleep debt from the last N days (hours)."""
        return sum(max(0.0, need - actual) for need, actual in need_vs_actual)

    # ── bedtime recommendation ──

    @staticmethod
    def bedtime_target(
        wake_time: datetime,
        sleep_need: float,
        latency_minutes: int = 12,
    ) -> datetime:
        """Recommended bedtime to meet a given sleep need for a target wake time."""
        total_seconds = sleep_need * 3600.0 + latency_minutes * 60.0
        return wake_time - timedelta(seconds=total_seconds)


# ──────────────────────────────────────────────────────────────────────────────
# SleepConsistencyCalculator (from SleepConsistencyCalculator.swift)
# ──────────────────────────────────────────────────────────────────────────────

class SleepConsistencyCalculator:
    """Computes a sleep consistency score (0–100)."""

    @staticmethod
    def calculate(
        start_times: List[Optional[datetime]],
        end_times: List[Optional[datetime]],
    ) -> Optional[float]:
        start_mins = [
            SleepConsistencyCalculator._minutes_from_midnight(dt, is_evening=True)
            for dt in start_times
            if dt is not None
        ]
        start_mins = [m for m in start_mins if m is not None]

        end_mins = [
            SleepConsistencyCalculator._minutes_from_midnight(dt, is_evening=False)
            for dt in end_times
            if dt is not None
        ]
        end_mins = [m for m in end_mins if m is not None]

        if len(start_mins) < 3 or len(end_mins) < 3:
            return None

        start_stddev = SleepConsistencyCalculator._stddev(start_mins)
        end_stddev = SleepConsistencyCalculator._stddev(end_mins)
        avg_stddev = (start_stddev + end_stddev) / 2.0

        max_stddev = 120.0
        return clamp((1.0 - avg_stddev / max_stddev) * 100.0, 0.0, 100.0)

    @staticmethod
    def _minutes_from_midnight(
        dt: Optional[datetime], is_evening: bool
    ) -> Optional[float]:
        if dt is None:
            return None
        mins = float(dt.hour * 60 + dt.minute)
        if is_evening and dt.hour >= 18:
            mins -= 1440
        return mins

    @staticmethod
    def _stddev(values: List[float]) -> float:
        if len(values) <= 1:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)


# ──────────────────────────────────────────────────────────────────────────────
# AyurvedicSleepCalculator (from AyurvedicSleepCalculator.swift)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoringWindow:
    start: datetime
    end: datetime
    points_per_hour: float
    label: str


@dataclass
class WindowBreakdown:
    label: str
    hours_slept: float
    points_per_hour: float
    earned: float


class AyurvedicSleepCalculator:
    """Ayurvedic Sleep Points score (0.0–10.0)."""

    MAX_RAW_POINTS: float = 8.0

    @staticmethod
    def build_windows(evening_date: date) -> List[ScoringWindow]:
        nine_pm = datetime.combine(evening_date, time(21, 0))
        five_pm = nine_pm - timedelta(hours=4)
        midnight = nine_pm + timedelta(hours=3)
        three_am = midnight + timedelta(hours=3)
        six_am = three_am + timedelta(hours=3)
        eight_am = six_am + timedelta(hours=2)

        return [
            ScoringWindow(start=five_pm, end=midnight, points_per_hour=2.0, label="Before 12 AM"),
            ScoringWindow(start=midnight, end=three_am, points_per_hour=1.0, label="12–3 AM"),
            ScoringWindow(start=three_am, end=six_am, points_per_hour=0.5, label="3–6 AM"),
            ScoringWindow(start=six_am, end=eight_am, points_per_hour=0.25, label="6–8 AM"),
        ]

    @staticmethod
    def raw_points(
        start: datetime, end: datetime, windows: List[ScoringWindow]
    ) -> float:
        total = 0.0
        for w in windows:
            overlap_start = max(start, w.start)
            overlap_end = min(end, w.end)
            if overlap_end > overlap_start:
                hours = (overlap_end - overlap_start).total_seconds() / 3600.0
                total += hours * w.points_per_hour
        return total

    @staticmethod
    def calculate(
        intervals: List[Tuple[datetime, datetime]],
        evening_date: date,
    ) -> float:
        if not intervals:
            return 0.0
        windows = AyurvedicSleepCalculator.build_windows(evening_date)
        raw = sum(
            AyurvedicSleepCalculator.raw_points(s, e, windows) for s, e in intervals
        )
        normalized = min(10.0, (raw / AyurvedicSleepCalculator.MAX_RAW_POINTS) * 10.0)
        return round(normalized, 1)

    @staticmethod
    def breakdown(
        start: datetime, end: datetime, evening_date: date
    ) -> List[WindowBreakdown]:
        results = []
        for w in AyurvedicSleepCalculator.build_windows(evening_date):
            overlap_start = max(start, w.start)
            overlap_end = min(end, w.end)
            hours = (
                (overlap_end - overlap_start).total_seconds() / 3600.0
                if overlap_end > overlap_start
                else 0.0
            )
            results.append(
                WindowBreakdown(
                    label=w.label,
                    hours_slept=hours,
                    points_per_hour=w.points_per_hour,
                    earned=hours * w.points_per_hour,
                )
            )
        return results

    @staticmethod
    def guidance_text(score: float) -> str:
        if 8 <= score <= 10:
            return "Excellent circadian sleep"
        elif 6 <= score < 8:
            return "Good alignment"
        elif 4 <= score < 6:
            return "Late sleep pattern"
        else:
            return "Very late sleep pattern"

    @staticmethod
    def guidance_hex(score: float) -> str:
        if 8 <= score <= 10:
            return "00C853"
        elif 6 <= score < 8:
            return "69F0AE"
        elif 4 <= score < 6:
            return "FFD600"
        else:
            return "FF1744"

    @staticmethod
    def improvement_tip(
        sleep_start: datetime,
        sleep_end: datetime,
        current_score: float,
        evening_date: date,
    ) -> Optional[str]:
        if current_score >= 8.0:
            return None
        windows = AyurvedicSleepCalculator.build_windows(evening_date)
        midnight = windows[0].end
        if sleep_start >= midnight:
            return (
                "Most of your sleep is occurring after midnight. "
                "Try going to bed before midnight for better recovery."
            )

        eleven_pm = windows[0].start + timedelta(hours=6)
        if sleep_start > eleven_pm:
            for minutes in [30, 45, 60, 90]:
                shifted_start = sleep_start - timedelta(minutes=minutes)
                shifted_end = sleep_end - timedelta(minutes=minutes)
                new_raw = AyurvedicSleepCalculator.raw_points(
                    shifted_start, shifted_end, windows
                )
                new_score = min(
                    10.0, (new_raw / AyurvedicSleepCalculator.MAX_RAW_POINTS) * 10.0
                )
                pct = ((new_score - current_score) / max(current_score, 0.1)) * 100
                if pct >= 8:
                    return (
                        f"Going to bed {minutes} minutes earlier could boost "
                        f"your sleep points by {round(pct)}%."
                    )
            return "You are missing the highest recovery window (9–11 PM)."

        return "Going to bed a little earlier would improve your circadian alignment."


# ──────────────────────────────────────────────────────────────────────────────
# Demo / Run block
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # --- User Sleep Data ---
    # In Bed: 12h 2m (43,320s), Asleep: 8h 30m (30,600s), Awake: 3h 32m 30s (12,750s)
    # Stages: REM 1h 51m 30s (6,690s), Core 6h 10m 00s (22,200s), Deep 0h 28m 30s (1,710s)
    rem_seconds = 1 * 3600 + 51 * 60 + 30
    core_seconds = 6 * 3600 + 10 * 60
    deep_seconds = 28 * 60 + 30
    total_sleep_seconds = rem_seconds + core_seconds + deep_seconds  # 8h 30m (30,600s)

    in_bed_seconds = 12 * 3600 + 2 * 60
    awake_seconds = 3 * 3600 + 32 * 60 + 30

    my_sleep = SleepData(
        total_duration=total_sleep_seconds,
        deep_sleep_duration=deep_seconds,
        rem_sleep_duration=rem_seconds,
        core_sleep_duration=core_seconds,
        awake_duration=awake_seconds,
        in_bed_duration=in_bed_seconds,
        sleep_start_time=None,
        sleep_end_time=None,
        interruption_count=0,
        nap_duration_seconds=0.0,
        sleep_latency_seconds=None,
    )

    sleep_need = 8.0 + 44.0 / 60.0   # 8h 44m = 8.733 hours
    sleeping_hrv = 49.8              # ms
    hrv_baseline = 41.8              # ms
    sleeping_hr = 62.0               # bpm
    sleeping_hr_baseline = 61.8      # bpm
    waking_hr = 72.0                 # bpm
    age = 22

    score = SleepCalculator.calculate_score(
        sleep=my_sleep,
        sleep_need=sleep_need,
        sleeping_hrv=sleeping_hrv,
        sleeping_hr=sleeping_hr,
        waking_hr=waking_hr,
        hrv_baseline=hrv_baseline,
        sleeping_hr_baseline=sleeping_hr_baseline,
        age=age,
    )

    print("========================================")
    print(f" YOUR MODIFIED SLEEP SCORE: {score:.1f} / 100 (Exact: {score:.2f})")
    print("========================================")
    print("\n--- Sub-Component Breakdown (Modified) ---")

    # 1. Duration (sigmoid for undersleep, oversleep penalty)
    duration_hrs = total_sleep_seconds / 3600.0
    ratio = duration_hrs / sleep_need
    steepness = 8.0
    midpoint = 0.75
    if ratio <= 1.0:
        x = steepness * (ratio - midpoint)
        duration_sub = 100.0 / (1.0 + math.exp(-x))
    elif ratio <= 1.10:
        duration_sub = 100.0
    else:
        excess = ratio - 1.10
        duration_sub = max(30.0, 100.0 - excess * 75.0)
    print(f"1. Duration Score      : {duration_sub:5.1f}%  (Weight: 27%) -> {0.27 * duration_sub:5.2f} pts")
    print(f"   [Asleep: {duration_hrs:.2f}h / Need: {sleep_need:.2f}h = {ratio*100:.1f}%]  (sigmoid: steepness={steepness}, midpoint={midpoint})")

    # 2. Stage Quality (using sleep_need as denominator)
    sleep_need_seconds = sleep_need * 3600.0
    deep_tgt = SleepCalculator.optimal_deep_ratio(age)
    deep_sub = min(100.0, ((deep_seconds / sleep_need_seconds) / deep_tgt) * 100.0)
    rem_sub = min(100.0, ((rem_seconds / sleep_need_seconds) / SleepCalculator.OPTIMAL_REM_RATIO) * 100.0)
    core_sub = min(100.0, ((core_seconds / sleep_need_seconds) / SleepCalculator.OPTIMAL_CORE_RATIO) * 100.0)
    stage_sub = 0.40 * deep_sub + 0.40 * rem_sub + 0.20 * core_sub
    print(f"2. Stage Mix Score     : {stage_sub:5.1f}%  (Weight: 20%) -> {0.20 * stage_sub:5.2f} pts")
    print(f"   - Deep: {deep_seconds/60:.1f}m ({deep_seconds/sleep_need_seconds*100:.1f}% of need vs {deep_tgt*100:.1f}% target) -> {deep_sub:.1f}%")
    print(f"   - REM : {rem_seconds/60:.1f}m ({rem_seconds/sleep_need_seconds*100:.1f}% of need vs 20.0% target) -> {rem_sub:.1f}%")
    print(f"   - Core: {core_seconds/60:.1f}m ({core_seconds/sleep_need_seconds*100:.1f}% of need vs 50.0% target) -> {core_sub:.1f}%")

    # 3. Sleep Efficiency
    eff_sub = SleepCalculator.compute_sleep_efficiency_score(my_sleep)
    eff_pct = total_sleep_seconds / in_bed_seconds * 100 if in_bed_seconds > 0 else 0
    print(f"3. Sleep Efficiency    : {eff_sub:5.1f}%  (Weight: 10%) -> {0.10 * eff_sub:5.2f} pts")
    print(f"   [{eff_pct:.1f}% of in-bed time spent asleep]")

    # 4. Sleeping HRV (Weight: 5%)
    hrv_sub = SleepCalculator.compute_sleeping_hrv_score(sleeping_hrv, hrv_baseline)
    print(f"4. Sleeping HRV Score  : {hrv_sub:5.1f}%  (Weight:  5%) -> {0.05 * hrv_sub:5.2f} pts")
    print(f"   [{sleeping_hrv} ms vs baseline {hrv_baseline} ms]")

    # 5. Sleeping HR (Weight: 5%)
    hr_sub = SleepCalculator.compute_sleeping_hr_score(sleeping_hr, sleeping_hr_baseline)
    print(f"5. Sleeping HR Score   : {hr_sub:5.1f}%  (Weight:  5%) -> {0.05 * hr_sub:5.2f} pts")
    print(f"   [{sleeping_hr} bpm vs baseline {sleeping_hr_baseline} bpm]")

    # 6. Heart Rate Dip (Weight: 18%)
    hr_dip_sub = SleepCalculator.compute_hr_dip_score(sleeping_hr, waking_hr)
    dip_pct = (waking_hr - sleeping_hr) / waking_hr * 100 if (waking_hr is not None and waking_hr > 0) else 0
    print(f"6. Heart Rate Dip      : {hr_dip_sub:5.1f}%  (Weight: 18%) -> {0.18 * hr_dip_sub:5.2f} pts")
    print(f"   [{dip_pct:.1f}% dip: {waking_hr} bpm waking -> {sleeping_hr} bpm sleeping]")

    # 7. Restfulness / WASO (Weight: 15%, absorbed 5% from Latency)
    rest_sub = SleepCalculator.compute_restfulness_score(my_sleep)
    waso_min = awake_seconds / 60.0
    print(f"7. Restfulness (WASO)  : {rest_sub:5.1f}%  (Weight: 15%) -> {0.15 * rest_sub:5.2f} pts")
    print(f"   [{waso_min:.1f} min awake, {my_sleep.interruption_count} wake segment(s)]")

    print("========================================")
