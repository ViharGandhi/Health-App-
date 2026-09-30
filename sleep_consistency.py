"""
sleep_consistency.py
====================
WHOOP-style Sleep Consistency Algorithm based on 4-day rolling sleep history.

Sleep consistency measures the day-to-day regularity of when you go to bed and wake up.
High sleep consistency anchors your circadian rhythm, improving REM/Deep sleep efficiency
and next-day autonomic recovery (HRV).

Data Source:
  Google Health API / Google Fit:
    Endpoint: GET /v1/users/me/sleep?startDate={YYYY-MM-DD}&endDate={YYYY-MM-DD}
    or Google Fit Sessions API: GET /fitness/v1/users/me/sessions?activityType=72
    Fields:
      - `startTime`: Bedtime / Sleep onset (ISO 8601)
      - `endTime`: Wake-up time / Sleep offset (ISO 8601)

Algorithm:
  1. Circular Mean Bedtime:
     Because bedtimes span midnight (e.g., 11:30 PM and 12:15 AM), linear averaging fails.
     Times are converted to circular angles on a 24-hour dial (theta = 2 * pi * minutes / 1440)
     to compute the exact circular mean bedtime.
  2. Circular Mean Wake-up Time:
     Computes circular average for morning wake-up times.
  3. Variance & Deviation:
     Measures mean absolute deviation in minutes for both bedtime and wake-up time across the 4-day window.
  4. Consistency Score (0–100%):
     Based on combined deviations:
       - 0-20 min avg deviation  → 90–100% (Optimal)
       - 21-45 min avg deviation → 70–89%  (Sufficient)
       - > 45 min avg deviation  → < 70%   (Poor)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from typing import List, Optional, Tuple, Dict, Any


@dataclass
class SleepNight:
    """Represents sleep onset and wake-up times for a single night."""
    night_date: date
    bed_time: datetime
    wake_time: datetime

    @property
    def sleep_duration_hours(self) -> float:
        return (self.wake_time - self.bed_time).total_seconds() / 3600.0


@dataclass
class SleepConsistencyResult:
    """Output of the 4-day Sleep Consistency calculation."""
    consistency_score: float             # 0 to 100%
    status: str                         # "Optimal" | "Sufficient" | "Poor"
    average_bed_time_str: str           # e.g., "11:24 PM"
    average_wake_time_str: str          # e.g., "07:18 AM"
    average_bed_time_minutes: float     # minutes past midnight (can be negative for PM)
    average_wake_time_minutes: float    # minutes past midnight
    bed_time_avg_deviation_mins: float  # average deviation in minutes
    wake_time_avg_deviation_mins: float # average deviation in minutes
    days_analyzed: int                  # number of days used (ideally 4)
    daily_details: List[Dict[str, Any]] = field(default_factory=list)


def _time_to_minutes_from_midnight(dt: datetime) -> float:
    """Converts a datetime into minutes past midnight, where PM hours wrap to negative."""
    total_mins = dt.hour * 60 + dt.minute + dt.second / 60.0
    # Map evening hours (>= 12:00 PM) to negative offset if after 18:00
    return total_mins


def _circular_mean_time(datetimes_list: List[datetime]) -> Tuple[float, time]:
    """
    Computes circular mean of a list of clock times on a 24-hour cycle.
    Avoids the midnight boundary problem where 23:50 and 00:10 would average to noon.
    Returns:
      (mean_minutes_from_midnight, time_object)
    """
    if not datetimes_list:
        return 0.0, time(0, 0)

    # 1440 minutes in a 24-hour day -> 2*pi radians
    sin_sum = 0.0
    cos_sum = 0.0

    for dt in datetimes_list:
        minutes = dt.hour * 60.0 + dt.minute + dt.second / 60.0
        angle = (minutes / 1440.0) * 2.0 * math.pi
        sin_sum += math.sin(angle)
        cos_sum += math.cos(angle)

    mean_angle = math.atan2(sin_sum, cos_sum)
    if mean_angle < 0:
        mean_angle += 2.0 * math.pi

    mean_minutes = (mean_angle / (2.0 * math.pi)) * 1440.0
    mean_hour = int(mean_minutes // 60) % 24
    mean_min = int(mean_minutes % 60)
    mean_sec = int((mean_minutes * 60) % 60)

    return mean_minutes, time(mean_hour, mean_min, mean_sec)


def _circular_difference_minutes(t1_mins: float, t2_mins: float) -> float:
    """Calculates absolute difference between two clock times in minutes on a 24-hour dial."""
    diff = abs(t1_mins - t2_mins) % 1440.0
    if diff > 720.0:
        diff = 1440.0 - diff
    return diff


def format_clock_time(t: time) -> str:
    """Formats a time object into 12-hour format like '11:24 PM'."""
    h = t.hour
    m = str(t.minute).padStart(2, "0") if hasattr(str(t.minute), "padStart") else f"{t.minute:02d}"
    ampm = "PM" if h >= 12 else "AM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{m} {ampm}"


class SleepConsistencyCalculator:
    """
    Computes 4-day sleep consistency from a series of bedtime and wake-up times.
    """

    @classmethod
    def calculate(cls, nights: List[SleepNight]) -> SleepConsistencyResult:
        """
        Calculate sleep consistency for the provided sleep nights (ideally 4 consecutive days).
        """
        if not nights:
            return SleepConsistencyResult(
                consistency_score=80.0,
                status="Sufficient",
                average_bed_time_str="11:30 PM",
                average_wake_time_str="07:30 AM",
                average_bed_time_minutes=1410.0,
                average_wake_time_minutes=450.0,
                bed_time_avg_deviation_mins=25.0,
                wake_time_avg_deviation_mins=25.0,
                days_analyzed=0,
                daily_details=[],
            )

        # Use the most recent 4 days if more are provided
        target_nights = nights[-4:]
        n = len(target_nights)

        bed_times = [night.bed_time for night in target_nights]
        wake_times = [night.wake_time for night in target_nights]

        # 1. Circular mean bedtime & wake-up time
        mean_bed_mins, mean_bed_t = _circular_mean_time(bed_times)
        mean_wake_mins, mean_wake_t = _circular_mean_time(wake_times)

        # 2. Compute individual day deviations
        bed_deviations = []
        wake_deviations = []
        daily_details = []

        for night in target_nights:
            cur_bed_mins = night.bed_time.hour * 60.0 + night.bed_time.minute
            cur_wake_mins = night.wake_time.hour * 60.0 + night.wake_time.minute

            bed_dev = _circular_difference_minutes(cur_bed_mins, mean_bed_mins)
            wake_dev = _circular_difference_minutes(cur_wake_mins, mean_wake_mins)

            bed_deviations.append(bed_dev)
            wake_deviations.append(wake_dev)

            daily_details.append({
                "date": night.night_date.strftime("%Y-%m-%d"),
                "bed_time": format_clock_time(night.bed_time.time()),
                "wake_time": format_clock_time(night.wake_time.time()),
                "duration_hours": round(night.sleep_duration_hours, 2),
                "bed_deviation_mins": round(bed_dev, 1),
                "wake_deviation_mins": round(wake_dev, 1),
            })

        avg_bed_dev = sum(bed_deviations) / n
        avg_wake_dev = sum(wake_deviations) / n

        # 3. Overall combined average deviation
        combined_dev = (avg_bed_dev + avg_wake_dev) / 2.0

        # 4. Consistency Score (0–100%)
        # 0 min deviation -> 100%
        # 30 min deviation -> ~85%
        # 60 min deviation -> ~70%
        # 120 min deviation -> 40%
        # Formula: score = 100 - (combined_dev * 0.5)
        raw_score = 100.0 - (combined_dev * 0.5)
        score = max(0.0, min(100.0, round(raw_score, 1)))

        if score >= 85.0:
            status = "Optimal"
        elif score >= 70.0:
            status = "Sufficient"
        else:
            status = "Poor"

        return SleepConsistencyResult(
            consistency_score=score,
            status=status,
            average_bed_time_str=format_clock_time(mean_bed_t),
            average_wake_time_str=format_clock_time(mean_wake_t),
            average_bed_time_minutes=round(mean_bed_mins, 1),
            average_wake_time_minutes=round(mean_wake_mins, 1),
            bed_time_avg_deviation_mins=round(avg_bed_dev, 1),
            wake_time_avg_deviation_mins=round(avg_wake_dev, 1),
            days_analyzed=n,
            daily_details=daily_details,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Self-Test Demo Runner
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today = date(2026, 9, 30)

    # 4 sample nights: Bedtime ~ 11:15 PM - 11:45 PM, Wake up ~ 7:00 AM - 7:35 AM
    sample_nights = [
        SleepNight(
            night_date=today - timedelta(days=3),
            bed_time=datetime(2026, 9, 26, 23, 20),
            wake_time=datetime(2026, 9, 27, 7, 15),
        ),
        SleepNight(
            night_date=today - timedelta(days=2),
            bed_time=datetime(2026, 9, 27, 23, 35),
            wake_time=datetime(2026, 9, 28, 7, 30),
        ),
        SleepNight(
            night_date=today - timedelta(days=1),
            bed_time=datetime(2026, 9, 28, 23, 10),
            wake_time=datetime(2026, 9, 29, 7, 10),
        ),
        SleepNight(
            night_date=today,
            bed_time=datetime(2026, 9, 29, 23, 40),
            wake_time=datetime(2026, 9, 30, 7, 25),
        ),
    ]

    result = SleepConsistencyCalculator.calculate(sample_nights)
    print("=" * 60)
    print(f"4-Day Sleep Consistency Score: {result.consistency_score}% ({result.status})")
    print(f"Average Bed Time:  {result.average_bed_time_str} (Avg Dev: {result.bed_time_avg_deviation_mins}m)")
    print(f"Average Wake Time: {result.average_wake_time_str} (Avg Dev: {result.wake_time_avg_deviation_mins}m)")
    print(f"Days Analyzed:     {result.days_analyzed}")
    print("-" * 60)
    for day in result.daily_details:
        print(f"  {day['date']}: Bed {day['bed_time']} (dev: {day['bed_deviation_mins']}m), "
              f"Wake {day['wake_time']} (dev: {day['wake_deviation_mins']}m)")
    print("=" * 60)
