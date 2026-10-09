"""Date-aligned sleep efficiency and timing trends for device and sample data."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from models import (
    SleepConsistencyScorePoint, SleepConsistencyScoreResponse,
    SleepTrendDay, SleepTrendResponse,
)
from sleep_consistency import (
    SleepConsistencyCalculator, SleepNight, consistency_label, score_main_sleep,
)
from sleep_efficiency import SleepEfficiencyCalculator


class DateRangeError(ValueError):
    pass


def range_start(end: date, timeframe: str) -> date:
    if timeframe == "W":
        return end - timedelta(days=6)
    if timeframe == "M":
        return end - timedelta(days=29)
    months = 6 if timeframe == "6M" else 12
    month_index = end.year * 12 + end.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    if not 1 <= year <= 9999:
        raise DateRangeError('Calendar window cannot be represented')
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
        estimator='pooled_sleep_efficiency' if metric == 'efficiency' else 'seven_night_clock_variability',
        is_mock=is_mock, timeframe=timeframe,
        range_start=start.isoformat(), range_end=end.isoformat(),
        average_value=average,
        recorded_nights=sum(1 for day in days if by_date.get(date.fromisoformat(day.date))),
        scored_days=len(values), days=days,
    )


def build_consistency_scores(
    records: list[dict], end: date, timeframe: str, is_mock: bool,
) -> SleepConsistencyScoreResponse:
    """Score each wake date, then group scored days into rolling chart buckets."""
    start = range_start(end, timeframe)
    previous_end = start - timedelta(days=1)
    previous_start = range_start(previous_end, timeframe)
    by_date = {
        record["date"]: SleepNight(record["date"], record["bed_time"], record["wake_time"])
        for record in records if record["bed_time"] < record["wake_time"]
    }
    daily = {day: score_main_sleep(night, by_date) for day, night in by_date.items()}

    def values_between(first: date, last: date) -> list[float]:
        return [result.score for day, result in daily.items()
                if first <= day <= last and result.score is not None]

    def mean_score(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    periods: list[tuple[date, date]] = []
    if timeframe in ("W", "M"):
        periods = [(start + timedelta(days=index), start + timedelta(days=index))
                   for index in range((end - start).days + 1)]
    elif timeframe == "6M":
        last = end
        while last >= start:
            first = max(start, last - timedelta(days=6))
            periods.append((first, last))
            last = first - timedelta(days=1)
        periods.reverse()
    else:
        def month_back(count: int) -> date:
            year, month_zero = divmod(end.year * 12 + end.month - 1 - count, 12)
            month = month_zero + 1
            return date(year, month, min(end.day, calendar.monthrange(year, month)[1]))

        periods = [(month_back(index + 1) + timedelta(days=1), month_back(index))
                   for index in range(11, -1, -1)]

    points = []
    for first, last in periods:
        values = values_between(first, last)
        score = mean_score(values)
        result = daily.get(first) if timeframe == "W" else None
        points.append(SleepConsistencyScorePoint(
            start_date=first.isoformat(), end_date=last.isoformat(),
            score=score, label=consistency_label(score) if score is not None else None,
            scored_days=len(values),
            drift_minutes=round(result.drift_minutes, 1) if result and result.drift_minutes is not None else None,
        ))

    current_values = values_between(start, end)
    band_counts = {label: 0 for label in ("Optimal", "Good", "Fair", "Poor")}
    for value in current_values:
        band_counts[consistency_label(round(value, 1))] += 1
    previous_values = values_between(previous_start, previous_end)
    average = mean_score(current_values)
    previous_average = mean_score(previous_values)
    latest_day = max((day for day in by_date if day <= end), default=None)
    latest = daily.get(latest_day) if latest_day else None
    latest_score = round(latest.score, 1) if latest and latest.score is not None else None
    return SleepConsistencyScoreResponse(
        is_mock=is_mock, timeframe=timeframe,
        range_start=start.isoformat(), range_end=end.isoformat(),
        latest_sleep_date=latest_day.isoformat() if latest_day else None,
        latest_score=latest_score,
        latest_label=(consistency_label(latest_score) if latest_score is not None
                      else "Calibrating" if latest_day else None),
        latest_drift_minutes=round(latest.drift_minutes, 1) if latest and latest.drift_minutes is not None else None,
        average_score=average,
        average_label=consistency_label(average) if average is not None else None,
        scored_days=len(current_values), total_days=(end - start).days + 1,
        previous_average_score=previous_average,
        change_percentage_points=(round(average - previous_average, 1)
                                  if average is not None and previous_average is not None else None),
        band_counts=band_counts,
        points=points,
    )
