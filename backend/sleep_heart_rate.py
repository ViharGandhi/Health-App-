"""Observed BPM within a completed main sleep; no HRV-to-BPM reconstruction."""

from datetime import date, datetime, timedelta, timezone
import math
import random

from sleep_stage_ranges import instant, adapt_google_sleep, stage_stats
from sleep_selection import main_sleep_key


def local_time(value: str, offset: str) -> str:
    return instant(value).astimezone(timezone(timedelta(seconds=float(offset.removesuffix("s"))))).isoformat()


def select_sleep(points: list[dict], today: date, sleep_id: str | None = None, *, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    candidates = []
    for point in points:
        if point.get("dataSource", {}).get("platform") not in (None, "FITBIT"):
            continue
        sleep = point["sleep"]
        meta, interval = sleep.get("metadata", {}), sleep["interval"]
        if meta.get("nap") or meta.get("mainSleep") is False:
            continue
        start, end = instant(interval["startTime"]), instant(interval["endTime"])
        wake_date = date.fromisoformat(local_time(interval["endTime"], interval["endUtcOffset"])[:10])
        if end <= start or end > now or wake_date > today:
            continue
        if sleep_id is not None and point["name"] != sleep_id:
            continue
        key = main_sleep_key(meta.get('mainSleep'), start, end, point['name'])
        if key is not None:
            candidates.append((wake_date, key, point))
    return max(candidates, key=lambda item: item[:2])[-1] if candidates else None


def build_sleep_heart_rate(point: dict | None, readings: list[dict], is_mock: bool) -> dict:
    if point is None:
        return {"is_mock": is_mock, 'estimator': 'observed_sleep_heart_rate', "status": "no_sleep", "samples": [], "stage_intervals": []}
    interval = point["sleep"]["interval"]
    start, end = instant(interval["startTime"]), instant(interval["endTime"])
    samples, conflicts = {}, set()
    for reading in readings:
        metric = reading.get("heartRate", {})
        try:
            clock = metric["sampleTime"]
            timestamp = instant(clock["physicalTime"])
            bpm = float(metric["beatsPerMinute"])
            if not start <= timestamp < end or not 1 <= bpm <= 300 or not bpm.is_integer():
                continue
            sample = {"timestamp": timestamp.isoformat(),
                      "local_time": local_time(clock["physicalTime"], clock["utcOffset"]), "bpm": int(bpm)}
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if timestamp in samples and samples[timestamp] != sample:
            conflicts.add(timestamp)  # Reconciled data should not contain ambiguous duplicates.
        samples[timestamp] = sample
    ordered = [samples[t] for t in sorted(samples) if t not in conflicts]
    start_local = local_time(interval["startTime"], interval["startUtcOffset"])
    end_local = local_time(interval["endTime"], interval["endUtcOffset"])
    night = adapt_google_sleep(point)
    stats, _ = stage_stats(night)
    stage_intervals = [{"stage": s.stage, "start": s.start_utc.isoformat(), "end": s.end_utc.isoformat()}
                       for s in night.segments] if stats else []
    return {"is_mock": is_mock, 'estimator': 'observed_sleep_heart_rate', "status": "ok" if ordered else "no_readings",
            "sleep_id": point["name"], "night_date": end_local[:10],
            "start": start.isoformat(), "end": end.isoformat(),
            "start_local": start_local, "end_local": end_local, "samples": ordered,
            "stage_intervals": stage_intervals}


def mock_sleep_heart_rate_points(point: dict) -> list[dict]:
    """Date-seeded synthetic readings, varied across stages, with a device gap.

    The 45-second demo cadence is a fixture choice, not an API sampling guarantee.
    """
    sleep = point["sleep"]
    interval = sleep["interval"]
    start, end = instant(interval["startTime"]), instant(interval["endTime"])
    rng = random.Random(int(start.timestamp()))
    baseline = rng.randint(51, 65)
    duration = (end - start).total_seconds()
    stages = [(instant(s["startTime"]), instant(s["endTime"]), s["type"]) for s in sleep.get("stages", [])]
    readings, elapsed = [], 0
    while elapsed < duration:
        timestamp = start + timedelta(seconds=elapsed)
        stage = next((kind for left, right, kind in stages if left <= timestamp < right), "ASLEEP")
        bump = {"AWAKE": 15, "LIGHT": 1, "DEEP": -7, "REM": 6}.get(stage, 0)
        bpm = round(baseline + bump + 3 * math.sin(elapsed / 700) + rng.gauss(0, 2.5))
        if not duration * 0.4 <= elapsed < duration * 0.4 + 720:
            readings.append({"heartRate": {"sampleTime": {"physicalTime": timestamp.isoformat(),
                            "utcOffset": interval["startUtcOffset"]}, "beatsPerMinute": str(bpm)}})
        elapsed += rng.randint(35, 55)
    return readings
