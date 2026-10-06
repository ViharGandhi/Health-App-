"""Seeded Google v4-shaped Recovery fixtures; independent of dashboard demo scoring.

Run from the repo root: .venv/Scripts/python.exe backend/mock_recovery.py
"""

import asyncio
import json
import math
import random
import re
from datetime import date, datetime, timedelta

from google_health_client import GoogleHealthClient, _local_datetime


SCENARIOS = ("normal", "above_normal", "below_normal", "building_reference",
             "sparse_recent", "low_confidence", "missing_rhr", "method_change",
             "missing_today_hrv", "short_sleep", "missing_sleep", "illness_flag")


def mock_recovery_points(day: date, scenario: str = "normal") -> dict[str, list[dict]]:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown Recovery scenario: {scenario}")
    rng = random.Random(4107)
    points = {key: [] for key in ("daily-heart-rate-variability", "daily-resting-heart-rate",
                                 "daily-respiratory-rate", "daily-sleep-temperature-derivations",
                                 "sleep", "heart-rate", "exercise")}
    count = 20 if scenario == "building_reference" else 24 if scenario == "low_confidence" else 60
    recent = 3 if scenario == "sparse_recent" else 7
    for offset in [*range(8, 8 + count), *range(recent)]:
        when = day - timedelta(days=offset)
        google_date = {"year": when.year, "month": when.month, "day": when.day}
        shift = (.20 if scenario in ("above_normal", "illness_flag") else -.20 if scenario == "below_normal" else .04) if offset < 7 else 0
        hrv = round(math.exp(math.log(44) + rng.gauss(0, .085) + shift), 2)
        if not (offset == 0 and scenario == "missing_today_hrv"):
            points["daily-heart-rate-variability"].append({"dailyHeartRateVariability": {
                "date": google_date, "averageHeartRateVariabilityMilliseconds": hrv}})
        rhr_shift = (-3 if scenario in ("above_normal", "illness_flag") else 3 if scenario == "below_normal" else 0) if offset < 7 else 0
        rhr = round(55 + rng.gauss(0, 1.8) + rhr_shift)
        method = "ONLY_WITH_AWAKE_DATA" if offset >= 8 and scenario == "method_change" else "WITH_SLEEP"
        if scenario != "missing_rhr":
            points["daily-resting-heart-rate"].append({"dailyRestingHeartRate": {
                "date": google_date, "beatsPerMinute": str(rhr),
                "dailyRestingHeartRateMetadata": {"calculationMethod": method}}})
        points["daily-respiratory-rate"].append({"dailyRespiratoryRate": {
            "date": google_date, "breathsPerMinute": 20 if offset == 0 and scenario == "illness_flag" else round(16 + rng.gauss(0, .25), 2)}})
        points["daily-sleep-temperature-derivations"].append({"dailySleepTemperatureDerivations": {
            "date": google_date, "nightlyTemperatureCelsius": round(33 + rng.gauss(0, .18), 2)}})

    for offset in range(8):
        wake_day = day - timedelta(days=offset)
        end = datetime.combine(wake_day, datetime.min.time()) + timedelta(hours=7, minutes=rng.randrange(45))
        start = end - timedelta(minutes=540)
        minutes = rng.randint(330, 495)
        if offset == 0:
            minutes = 270 if scenario == "below_normal" else 150 if scenario == "short_sleep" else 470
        if not (offset == 0 and scenario == "missing_sleep"):
            points["sleep"].append({"name": f"demo-main-{wake_day}", "sleep": {
                "interval": {"startTime": start.isoformat() + "Z", "endTime": end.isoformat() + "Z",
                             "startUtcOffset": "0s", "endUtcOffset": "0s"},
                "metadata": {"mainSleep": True, "nap": False, "processed": True},
                "summary": {"minutesAsleep": str(minutes), "minutesAwake": str(540 - minutes),
                            "minutesInSleepPeriod": "540"}}})
    yesterday = day - timedelta(days=1)
    points["sleep"].append({"name": "demo-nap", "sleep": {
        "interval": {"startTime": f"{yesterday}T14:00:00Z", "endTime": f"{yesterday}T14:30:00Z",
                     "startUtcOffset": "0s", "endUtcOffset": "0s"},
        "metadata": {"mainSleep": False, "nap": True, "processed": True},
        "summary": {"minutesAsleep": "22"}}})
    for offset in range(1, 9):
        activity_day = day - timedelta(days=offset)
        start = datetime.combine(activity_day, datetime.min.time()) + timedelta(hours=9)
        for minute in range(120):
            clock = start + timedelta(minutes=minute)
            bpm = max(50, round(95 + 35 * math.sin(minute / 12 + offset) + rng.gauss(0, 8)))
            points["heart-rate"].append({"heartRate": {
                "sampleTime": {"physicalTime": clock.isoformat() + "Z", "utcOffset": "0s"},
                "beatsPerMinute": str(bpm)}})
        if offset % 2:
            points["exercise"].append({"exercise": {
                "interval": {"startTime": (start + timedelta(minutes=20)).isoformat() + "Z",
                             "endTime": (start + timedelta(minutes=50)).isoformat() + "Z",
                             "startUtcOffset": "0s", "endUtcOffset": "0s"},
                "displayName": "Demo run"}})
    return points


class MockRecoveryClient(GoogleHealthClient):
    """Exercise real API normalization and batching, replacing only network I/O."""
    def __init__(self, day: date, scenario: str = "normal"):
        super().__init__("demo-not-a-token")
        self.points = mock_recovery_points(day, scenario)
        self.calls = []

    async def _points(self, data_type, filter_expr, *, reconcile=True):
        self.calls.append((data_type, filter_expr))
        left, right = [date.fromisoformat(value) for value in re.findall(r'"(\d{4}-\d{2}-\d{2})"', filter_expr)]
        result = []
        for point in self.points[data_type]:
            value = next(value for key, value in point.items() if key != "name")
            if "date" in value:
                when = date(**value["date"])
            elif data_type == "heart-rate":
                clock = value["sampleTime"]
                when = _local_datetime(clock["physicalTime"], clock.get("utcOffset", "0s")).date()
            else:
                interval = value["interval"]
                edge = "end" if data_type == "sleep" else "start"
                when = _local_datetime(interval[edge + "Time"], interval.get(edge + "UtcOffset", "0s")).date()
            if left <= when < right:
                result.append(point)
        return result


async def preview():
    from main import _compute_connected_recovery
    day = date.today()
    rows = []
    for scenario in SCENARIOS:
        client = MockRecoveryClient(day, scenario)
        result = await _compute_connected_recovery(client, day, 30)
        rows.append({"scenario": scenario, "is_mock": True, "status": result.status,
                     "z": result.z, "percent": result.percent, "zone": result.zone,
                     "confidence": result.confidence, "estimated": result.estimated,
                     "components": result.components, "sleep_context": result.sleep_context,
                     "baseline_days": result.baseline_days, "recent_nights": result.recent_nights,
                     "illness_flag": result.illness_flag, "range_fetches": len(client.calls)})
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    asyncio.run(preview())
