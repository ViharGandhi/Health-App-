"""Sleep timing variability and a four-night, clock-drift consistency score.

Clock-time standard deviation is a descriptive sleep regularity measure.
It is not the Sleep Regularity Index, which requires epoch-level sleep/wake data.
The four-night percentage is an app-specific timing heuristic, not a clinical index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional


@dataclass
class SleepNight:
    night_date: date
    bed_time: datetime
    wake_time: datetime


@dataclass
class SleepConsistencyResult:
    timing_variability_minutes: Optional[float]
    bed_time_variability_minutes: Optional[float]
    wake_time_variability_minutes: Optional[float]
    average_bed_time_str: Optional[str]
    average_wake_time_str: Optional[str]
    days_analyzed: int


@dataclass
class DailyConsistencyScore:
    score: Optional[float]
    drift_minutes: Optional[float]
    prior_nights: int


def _circular_difference(a: int, b: int) -> int:
    difference = abs(a - b)
    return min(difference, 1440 - difference)


def _drift_score(drift: float) -> float:
    if drift >= 240:
        return 0.0
    raw = lambda value: 1 / (1 + math.exp(0.05 * (value - 75)))
    return max(0.0, min(100.0, 100 * (raw(drift) - raw(240)) / (raw(0) - raw(240))))


def consistency_label(score: float) -> str:
    if score >= 90:
        return "Optimal"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


def score_main_sleep(current: SleepNight, by_date: dict[date, SleepNight]) -> DailyConsistencyScore:
    """Score one wake date against its four preceding calendar dates."""
    weights = (0.40, 0.30, 0.20, 0.10)
    weighted_score = weighted_drift = weight_sum = 0.0
    prior_nights = 0
    for offset, weight in enumerate(weights, start=1):
        previous = by_date.get(current.night_date - timedelta(days=offset))
        if previous is None:
            continue
        onset = _circular_difference(
            current.bed_time.hour * 60 + current.bed_time.minute,
            previous.bed_time.hour * 60 + previous.bed_time.minute,
        )
        wake = _circular_difference(
            current.wake_time.hour * 60 + current.wake_time.minute,
            previous.wake_time.hour * 60 + previous.wake_time.minute,
        )
        drift = (onset + wake) / 2
        weighted_score += weight * _drift_score(drift)
        weighted_drift += weight * drift
        weight_sum += weight
        prior_nights += 1
    if prior_nights < 2:
        return DailyConsistencyScore(None, None, prior_nights)
    return DailyConsistencyScore(weighted_score / weight_sum,
                                 weighted_drift / weight_sum, prior_nights)


def _clock_minutes(value: datetime) -> float:
    return value.hour * 60 + value.minute + value.second / 60


def _clock_sd(values: list[float]) -> tuple[Optional[float], Optional[float]]:
    """Circular mean and population SD, in minutes, across midnight."""
    angles = [2 * math.pi * value / 1440 for value in values]
    sin_mean = sum(math.sin(angle) for angle in angles) / len(angles)
    cos_mean = sum(math.cos(angle) for angle in angles) / len(angles)
    if math.hypot(sin_mean, cos_mean) < 1e-6:
        return None, None
    mean = math.atan2(sin_mean, cos_mean) * 1440 / (2 * math.pi) % 1440
    deviations = [((value - mean + 720) % 1440) - 720 for value in values]
    return round(math.sqrt(sum(value * value for value in deviations) / len(values)), 1), mean


def _format_clock(minutes: Optional[float]) -> Optional[str]:
    if minutes is None:
        return None
    rounded = round(minutes) % 1440
    return time(rounded // 60, rounded % 60).strftime("%I:%M %p").lstrip("0")


class SleepConsistencyCalculator:
    @staticmethod
    def calculate(nights: list[SleepNight]) -> SleepConsistencyResult:
        """Return 7-night midpoint, onset and offset timing SDs; require complete dates."""
        recent = sorted(nights, key=lambda night: night.night_date)[-7:]
        if len(recent) != 7 or any(
            (recent[index].night_date - recent[index - 1].night_date).days != 1
            for index in range(1, 7)
        ):
            return SleepConsistencyResult(None, None, None, None, None, len(recent))

        bed_sd, bed_mean = _clock_sd([_clock_minutes(night.bed_time) for night in recent])
        wake_sd, wake_mean = _clock_sd([_clock_minutes(night.wake_time) for night in recent])
        midpoint_sd, _ = _clock_sd([
            _clock_minutes(night.bed_time)
            + (night.wake_time - night.bed_time).total_seconds() / 120
            for night in recent
        ])
        return SleepConsistencyResult(
            midpoint_sd, bed_sd, wake_sd,
            _format_clock(bed_mean), _format_clock(wake_mean), 7,
        )
