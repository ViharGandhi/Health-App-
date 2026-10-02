"""Date-aligned vital trends with a prior-only personal reference."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from models import HealthPoint, HealthResponse, HeartRatePoint


METRICS = ("hrv", "deep_sleep_hrv", "nrem_hr", "rhr", "spo2", "respiratory_rate", "skin_temperature", "vo2_max")


def build_health_response(
    history: dict[str, list[dict]], samples: list[tuple],
    start: date, end: date, timeframe: str, is_mock: bool,
) -> HealthResponse:
    metrics = {}
    for key in METRICS:
        by_date = {point["date"]: point for point in history.get(key, [])}
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

    buckets: dict[int, list[float]] = {}
    for timestamp, value in samples:
        slot = (timestamp.hour * 60 + timestamp.minute) // 15
        buckets.setdefault(slot, []).append(value)
    heart_rate = [HeartRatePoint(time=f"{slot // 4:02d}:{(slot % 4) * 15:02d}",
                                 value=round(median(values), 1))
                  for slot, values in sorted(buckets.items())]
    return HealthResponse(date=end.isoformat(), timeframe=timeframe,
                          range_start=start.isoformat(), range_end=end.isoformat(),
                          is_mock=is_mock, metrics=metrics, heart_rate=heart_rate)
