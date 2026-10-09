"""Recorded Recovery/vital trend data for the reference-style UI; gaps stay gaps."""

import math
import random
from datetime import date, timedelta
from statistics import mean

from recovery_score import baseline_bounds, positive, recovery_from_history, robust, MIN_BASELINE_DAYS
from sleep_trends import range_start
from validity import valid_metric


METRICS = ("recovery", "hrv", "rhr", "respiratory_rate", "sleep_performance")
VITALS = ("hrv", "rhr", "respiratory_rate", "skin_temperature", "spo2")


def typical_ranges(history: dict, day: date, age=None) -> dict:
    start, end = baseline_bounds(day)
    today_rhr = next((p for p in history.get("rhr", []) if p["date"] == day.isoformat()), {})
    ranges = {}
    for metric in VITALS:
        values = [p["value"] for p in history.get(metric, [])
                  if start.isoformat() <= p["date"] <= end.isoformat() and valid_metric(metric, p.get("value"), age)
                  and (metric != "rhr" or today_rhr.get("method") in ("WITH_SLEEP", "ONLY_WITH_AWAKE_DATA")
                       and p.get("method") == today_rhr["method"])]
        if len(values) < MIN_BASELINE_DAYS:
            ranges[metric] = None
            continue
        transformed = [math.log(v) for v in values] if metric == "hrv" else values
        center, spread = robust(transformed, .05 if metric == "hrv" else 1.0 if metric == "rhr" else 0.0)
        if spread == 0:
            ranges[metric] = None
            continue
        low, high = center - spread, center + spread
        if metric == "hrv":
            low, high = math.exp(low), math.exp(high)
        ranges[metric] = {"low": low, "high": high, "days": len(values)}
    return ranges


def build_recovery_analytics(history: dict, sleeps: list[dict], end: date, timeframe: str,
                             current: dict, *, is_mock: bool, demo_mode: str = "estimate", age=None) -> dict:
    start = range_start(end, timeframe)
    previous_end = start - timedelta(days=1)
    previous_start = range_start(previous_end, timeframe)
    dated = {key: {p["date"]: p for p in values} for key, values in history.items()}
    sleep_by_date = {s["date"]: s for s in sleeps}
    rhr_method = dated.get("rhr", {}).get(end.isoformat(), {}).get("method")
    all_days = []
    day = previous_start
    while day <= end:
        key = day.isoformat()
        reading = recovery_from_history(history, day, age=age)
        sleep = sleep_by_date.get(key, {})
        row = {"date": key, "recovery": reading.percent, "zone": reading.zone,
               "confidence": reading.confidence, "sleep_context_missing": True,
               "sleep_performance": sleep.get("performance"),
               **{metric: value if valid_metric(metric, value := dated.get(metric, {}).get(key, {}).get("value"), age) else None
                  for metric in VITALS}}
        if dated.get("rhr", {}).get(key, {}).get("method") != rhr_method or rhr_method not in ("WITH_SLEEP", "ONLY_WITH_AWAKE_DATA"):
            row["rhr"] = None
        if key == end.isoformat():
            row.update(recovery=current["score"], zone=current.get("zone"), confidence=current.get("confidence"),
                       sleep_context_missing=current.get("sleep_context", {}).get("performance") is None
                       if current.get("sleep_context") else True)
        if demo_mode == "legacy" and is_mock and key != end.isoformat():
            row.update(recovery=None, zone=None, confidence=None)
        all_days.append(row)
        day += timedelta(days=1)
    days = [d for d in all_days if d["date"] >= start.isoformat()]
    previous = [d for d in all_days if d["date"] < start.isoformat()]
    def averages(rows):
        return {metric: mean(values) if (values := [r[metric] for r in rows if positive(r[metric]) or r[metric] == 0]) else None
                for metric in METRICS}
    ranges = typical_ranges(history, end, age)
    latest = days[-1]
    assessed = [metric for metric in VITALS if ranges[metric] is not None and positive(latest.get(metric))]
    within = sum(ranges[metric]["low"] <= latest[metric] <= ranges[metric]["high"] for metric in assessed)
    # A week needs extra prior daily readings for the screenshot's 30-day comparison.
    comparisons = {}
    for metric in METRICS[1:]:
        if metric == "sleep_performance":
            values = [s["performance"] for s in sleeps if (end - timedelta(days=30)).isoformat() <= s["date"] < end.isoformat()
                      and s.get("performance") is not None]
        else:
            values = [p["value"] for p in history.get(metric, [])
                      if (end - timedelta(days=30)).isoformat() <= p["date"] < end.isoformat() and valid_metric(metric, p.get("value"), age)
                      and (metric != "rhr" or rhr_method in ("WITH_SLEEP", "ONLY_WITH_AWAKE_DATA") and p.get("method") == rhr_method)]
        comparisons[metric] = mean(values) if values else None
    buckets = []
    for offset in range(6, 0, -1):
        left = range_start(end, "6M") if offset == 6 else _months_back(end, offset) + timedelta(days=1)
        right = _months_back(end, offset - 1)
        rows = [d for d in days if left.isoformat() <= d["date"] <= right.isoformat()]
        buckets.append({"start_date": left.isoformat(), "end_date": right.isoformat(),
                        "averages": averages(rows), "counts": {m: sum(d[m] is not None for d in rows) for m in METRICS}})
    return {"is_mock": is_mock, 'estimator': current.get('estimator', 'connected_recovery'), "demo_mode": demo_mode if is_mock else None, "timeframe": timeframe,
            "range_start": start.isoformat(), "range_end": end.isoformat(),
            "previous_range_end": previous_end.isoformat(), "days": days,
            "averages": averages(days), "previous_averages": averages(previous),
            "typical_ranges": ranges, "prior_30_day_averages": comparisons, "monthly_buckets": buckets,
            "current": current, "sleep": sleep_by_date.get(end.isoformat()),
            "health_monitor": {"within": within, "assessed": len(assessed), "expected": len(VITALS)},
            "notes": ("Older prototype demo: historical prototype scores are not stored; earlier bars remain blank. "
                      if is_mock and demo_mode == "legacy" else
                      "Historical Recovery estimates use HRV/RHR without unavailable historical sleep need; confidence is reduced. ")
                      + "Missing values remain gaps. Typical ranges are median ± one robust SD, not medical limits."}


def _months_back(day: date, count: int) -> date:
    import calendar
    year, month = divmod(day.year * 12 + day.month - 1 - count, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def mock_recovery_history(start: date, end: date) -> dict:
    """Date-seeded sample readings, stable across ranges, with outliers and gaps."""
    result = {metric: [] for metric in VITALS}
    day = start
    while day <= end:
        ordinal = day.toordinal()
        rng = random.Random(ordinal + 7823)
        if ordinal % 37 != 0:
            values = {"hrv": max(12, 46 + 4 * math.sin(ordinal / 12) + rng.gauss(0, 3.4)),
                      "rhr": 59 + 1.2 * math.sin(ordinal / 10) + rng.gauss(0, 1.3),
                      "respiratory_rate": 15.8 + .15 * math.sin(ordinal / 8) + rng.gauss(0, .24),
                      "skin_temperature": 33 + rng.gauss(0, .2), "spo2": min(100, 97.5 + rng.gauss(0, .4))}
            if ordinal % 19 == 0:
                values["hrv"] += 12
            for metric, value in values.items():
                if metric == "skin_temperature" and ordinal % 13 == 0:
                    continue
                result[metric].append({"date": day.isoformat(), "value": round(value, 2),
                                       "method": "WITH_SLEEP" if metric == "rhr" else None})
        day += timedelta(days=1)
    return result
