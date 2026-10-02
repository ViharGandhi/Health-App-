"""Date-aligned sleep efficiency and timing trends for device and sample data."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from models import SleepTrendDay, SleepTrendResponse
from sleep_consistency import SleepConsistencyCalculator, SleepNight
from sleep_efficiency import SleepEfficiencyCalculator


def range_start(end: date, timeframe: str) -> date:
    if timeframe == "W":
        return end - timedelta(days=6)
    if timeframe == "M":
        return end - timedelta(days=29)
    months = 6 if timeframe == "6M" else 12
    month_index = end.year * 12 + end.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    prior = date(year, month, min(end.day, calendar.monthrange(year, month)[1]))
    return prior + timedelta(days=1)


def build_sleep_trend(
    records: list[dict], start: date, end: date, timeframe: str,
    metric: str, is_mock: bool,
) -> SleepTrendResponse:
    def usable(record: dict) -> bool:
        bedtime, wake = record["bed_time"], record["wake_time"]
        asleep, period = record["time_asleep_minutes"], record["time_in_bed_minutes"]
        return (bedtime < wake and 0 < (wake - bedtime).total_seconds() <= 24 * 3600
                and SleepEfficiencyCalculator.calculate_single_night(asleep * 60, period * 60) is not None)

    by_date = {record["date"]: record for record in records if usable(record)}
    days: list[SleepTrendDay] = []
    valid_efficiency: list[tuple[float, float]] = []
    current = start
    while current <= end:
        record = by_date.get(current)
        item = SleepTrendDay(date=current.isoformat())
        if record:
            if metric == "efficiency":
                asleep = record.get("time_asleep_minutes", 0)
                period = record.get("time_in_bed_minutes", 0)
                item.value = SleepEfficiencyCalculator.calculate_single_night(asleep * 60, period * 60)
                if item.value is not None:
                    item.asleep_hours = round(asleep / 60, 2)
                    item.in_bed_hours = round(period / 60, 2)
                    valid_efficiency.append((asleep, period))
            else:
                window = [by_date.get(current - timedelta(days=offset)) for offset in range(6, -1, -1)]
                if all(window):
                    result = SleepConsistencyCalculator.calculate([
                        SleepNight(day["date"], day["bed_time"], day["wake_time"])
                        for day in window if day
                    ])
                    item.value = result.timing_variability_minutes
                    item.bed_variability_minutes = result.bed_time_variability_minutes
                    item.wake_variability_minutes = result.wake_time_variability_minutes
                item.bed_time = record["bed_time"].strftime("%I:%M %p").lstrip("0")
                item.wake_time = record["wake_time"].strftime("%I:%M %p").lstrip("0")
        days.append(item)
        current += timedelta(days=1)

    values = [day.value for day in days if day.value is not None]
    if metric == "efficiency" and valid_efficiency:
        average = round(100 * sum(asleep for asleep, _ in valid_efficiency)
                        / sum(period for _, period in valid_efficiency), 1)
    else:
        average = round(sum(values) / len(values), 1) if values else None
    return SleepTrendResponse(
        is_mock=is_mock, timeframe=timeframe,
        range_start=start.isoformat(), range_end=end.isoformat(),
        average_value=average,
        recorded_nights=sum(1 for day in days if by_date.get(date.fromisoformat(day.date))),
        scored_days=len(values), days=days,
    )
