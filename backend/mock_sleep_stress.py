"""Date-seeded Google-shaped sample data for sleep stress development."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache

from sleep_stress import (
    adapt_google_hr, adapt_google_hrv, adapt_google_sleep, prepare_night, score_night,
)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _raw_night(day: date) -> tuple[dict, list[dict], list[dict]]:
    rng = random.Random(day.toordinal() + 28411)
    start = datetime.combine(day - timedelta(days=1), time(22, 20), timezone.utc)
    start += timedelta(minutes=rng.randrange(-30, 31, 5))
    count = rng.randrange(84, 103)
    end = start + timedelta(minutes=5 * count)
    event_count = rng.choices((0, 1, 2, 3), weights=(3, 4, 2, 1))[0]
    event_starts = rng.sample(range(10, count - 12), event_count)
    event_windows = set()
    for first in event_starts:
        event_windows.update(range(first, first + rng.randint(2, 6)))
    awake_windows = set(rng.sample(range(8, count - 5), rng.randint(1, 4)))
    quality = rng.choices(("full", "partial", "poor"), weights=(7, 2, 1))[0]
    missing_hr_fraction = {"full": 0.025, "partial": 0.24, "poor": 0.58}[quality]
    stages = []
    hrv_points = []
    hr_points = []
    stage_hrv = {"LIGHT": 43, "REM": 36, "DEEP": 51, "AWAKE": 44}
    stage_hr = {"LIGHT": 59, "REM": 64, "DEEP": 55, "AWAKE": 65}
    nightly_hrv = rng.gauss(0, 2.5)
    nightly_hr = rng.gauss(0, 1.8)
    for index in range(count):
        window_start = start + timedelta(minutes=5 * index)
        window_end = window_start + timedelta(minutes=5)
        cycle, cycle_index = index % 18, index // 18
        stage = ("AWAKE" if index in awake_windows else
                 "DEEP" if cycle < max(1, 5 - cycle_index) else
                 "REM" if cycle >= 14 - min(3, cycle_index) else "LIGHT")
        stages.append({"startTime": _timestamp(window_start), "endTime": _timestamp(window_end),
                       "type": stage})
        stressed = index in event_windows and stage != "AWAKE"
        rmssd = max(8, stage_hrv[stage] + nightly_hrv + rng.gauss(0, 5))
        if stressed:
            rmssd *= rng.uniform(0.55, 0.72)
        hrv_points.append({"heartRateVariability": {
            "sampleTime": {"physicalTime": _timestamp(window_start), "utcOffset": "7200s"},
            "rootMeanSquareOfSuccessiveDifferencesMilliseconds": round(rmssd, 2),
            "standardDeviationMilliseconds": round(rmssd * 1.4, 2),
        }})
        bpm = stage_hr[stage] + nightly_hr + rng.gauss(0, 2)
        if stressed:
            bpm += rng.uniform(9, 15)
        if rng.random() < missing_hr_fraction:
            continue
        for tick in range(30):
            if rng.random() < 0.025:
                continue
            sample_time = window_start + timedelta(seconds=10 * tick)
            reading = 200 if rng.random() < 0.003 else max(35, bpm + rng.gauss(0, 2))
            hr_points.append({"heartRate": {
                "sampleTime": {"physicalTime": _timestamp(sample_time), "utcOffset": "7200s"},
                "beatsPerMinute": str(round(reading)),
            }})
    short_awakenings = []
    if count > 44:
        awakening_start = start + timedelta(minutes=5 * 40 + 1)
        short_awakenings.append({"startTime": _timestamp(awakening_start),
                                 "endTime": _timestamp(awakening_start + timedelta(minutes=2)),
                                 "type": "AWAKE"})
    sleep_point = {"name": f"mock-sleep-{day.isoformat()}", "sleep": {
        "interval": {"startTime": _timestamp(start), "endTime": _timestamp(end),
                     "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
        "type": "STAGES", "stages": stages, "shortAwakenings": short_awakenings,
        "metadata": {"processed": True, "stagesStatus": "SUCCEEDED",
                     "mainSleep": True, "nap": False},
    }}
    return sleep_point, hrv_points, hr_points


@lru_cache(maxsize=16)
def prepared_mock_nights(today: date, days: int):
    """Return the same realistic raw and adapted nights for scoring and calibration."""
    first = today - timedelta(days=days + 13)
    prepared = []
    for offset in range((today - first).days + 1):
        day = first + timedelta(days=offset)
        sleep_point, hrv_points, hr_points = _raw_night(day)
        night = adapt_google_sleep(sleep_point)
        windows = adapt_google_hrv(hrv_points, anchor="start")  # mock timestamps are generated at window starts
        prepared.append(prepare_night(night, windows, [adapt_google_hr(item) for item in hr_points]))
    return tuple(prepared)


@lru_cache(maxsize=16)
def mock_sleep_stress_history(today: date, days: int) -> tuple[dict, ...]:
    """Score every requested night from prior nights, with no refresh-time randomness."""
    prepared = prepared_mock_nights(today, days)
    scored = []
    for current in prepared[-days:]:
        computed_at = current.night.end_utc + timedelta(minutes=45)
        scored.append(score_night(current, prepared, computed_at=computed_at))
    return tuple(scored)
