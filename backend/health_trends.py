"""Date-aligned vital trends with a prior-only personal reference."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import isfinite
from statistics import mean, median

from models import HealthPoint, HealthResponse, HeartRatePoint, LatestHeartRate, HealthHeartRateResponse
from sleep_trends import range_start
from recovery_score import positive


METRICS = ("hrv", "deep_sleep_hrv", "nrem_hr", "rhr", "spo2", "respiratory_rate", "skin_temperature", "vo2_max")


def valid_health_value(metric: str, value) -> bool:
    """Existing HR quality limits and percentage units; no new clinical ceilings."""
    if not isinstance(value, (int, float)) or not positive(value):
        return False
    if metric in ("rhr", "nrem_hr"):
        return 30 <= value <= 230
    if metric == "spo2":
        return value <= 100
    return True


def build_heart_rate_response(
    samples: list[tuple[datetime, float]], day: date, is_mock: bool,
) -> HealthHeartRateResponse:
    valid = [(timestamp, value) for timestamp, value in samples
             if timestamp.date() == day and isfinite(value) and value > 0]
    buckets: dict[int, list[float]] = {}
    for timestamp, value in valid:
        slot = (timestamp.hour * 60 + timestamp.minute) // 15
        buckets.setdefault(slot, []).append(value)
    points = [HeartRatePoint(time=f"{slot // 4:02d}:{(slot % 4) * 15:02d}",
                            value=round(median(values), 1))
              for slot, values in sorted(buckets.items())]
    latest = max(valid, key=lambda sample: sample[0]) if valid else None
    return HealthHeartRateResponse(
        date=day.isoformat(), is_mock=is_mock, heart_rate=points,
        latest_heart_rate=LatestHeartRate(sample_time=latest[0].isoformat(), value=latest[1]) if latest else None,
    )


def build_health_response(
    history: dict[str, list[dict]], samples: list[tuple],
    start: date, end: date, timeframe: str, is_mock: bool,
) -> HealthResponse:
    metrics = {}
    previous_end = start - timedelta(days=1)
    previous_start = range_start(previous_end, timeframe)
    averages = {}
    previous_averages = {}
    for key in METRICS:
        by_date = {point["date"]: {**point, "value": point.get("value")
                                 if valid_health_value(key, point.get("value")) else None}
                   for point in history.get(key, [])}
        for lower, upper, target in ((start, end, averages), (previous_start, previous_end, previous_averages)):
            values = [point["value"] for day, point in by_date.items()
                      if lower.isoformat() <= day <= upper.isoformat() and point.get("value") is not None]
            target[key] = mean(values) if values else None
        series = []
        day = start
        while day <= end:
            item = by_date.get(day.isoformat(), {})
            previous = [by_date.get((day - timedelta(days=offset)).isoformat(), {}).get("value")
                        for offset in range(14, 0, -1)]
            valid = [value for value in previous if value is not None]
            series.append(HealthPoint(
                date=day.isoformat(), value=item.get("value"),
                baseline=round(median(valid), 2) if len(valid) >= 7 else None,
                estimated=item.get("estimated"), method=item.get("method"),
            ))
            day += timedelta(days=1)
        metrics[key] = series

    heart = build_heart_rate_response(samples, end, is_mock)
    return HealthResponse(date=end.isoformat(), timeframe=timeframe,
                          range_start=start.isoformat(), range_end=end.isoformat(),
                          previous_range_start=previous_start.isoformat(), previous_range_end=previous_end.isoformat(),
                          averages=averages, previous_averages=previous_averages,
                          is_mock=is_mock, metrics=metrics, heart_rate=heart.heart_rate,
                          latest_heart_rate=heart.latest_heart_rate)
