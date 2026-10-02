"""Sleep timing variability from seven consecutive main sleep periods.

Clock-time standard deviation is a descriptive sleep regularity measure.
It is not the Sleep Regularity Index, which requires epoch-level sleep/wake data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time
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
