"""Read Fitbit wearable data from the Google Health API v4."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx


BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
WEARABLES = "users/me/dataSourceFamilies/google-wearables"


def _day_filter(field: str, start: date, end: date) -> str:
    """Build an inclusive local-date range with an exclusive upper bound."""
    return (f'{field} >= "{start.isoformat()}" AND '
            f'{field} < "{(end + timedelta(days=1)).isoformat()}"')


def _local_datetime(value: str, offset: str) -> datetime:
    """Return a naive wall-clock time in the offset supplied by Google."""
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    seconds = float(offset.removesuffix("s")) if offset else 0.0
    return instant.astimezone(timezone(timedelta(seconds=seconds))).replace(tzinfo=None)


def _google_date(value: dict) -> date:
    return date(value["year"], value["month"], value["day"])


class GoogleHealthClient:
    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def _points(self, data_type: str, filter_expr: str) -> list[dict]:
        """Fetch every page of reconciled wearable data; propagate API errors."""
        url = f"{BASE_URL}/{data_type}/dataPoints:reconcile"
        params = {"filter": filter_expr, "dataSourceFamily": WEARABLES}
        points: list[dict] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                payload = response.json()
                points.extend(payload.get("dataPoints", []))
                token = payload.get("nextPageToken")
                if not token:
                    return points
                params["pageToken"] = token

    async def get_daily_hrv(self, target_date: date) -> Optional[float]:
        points = await self._points(
            "daily-heart-rate-variability",
            _day_filter("dailyHeartRateVariability.date", target_date, target_date),
        )
        for point in points:
            metric = point.get("dailyHeartRateVariability", {})
            if "averageHeartRateVariabilityMilliseconds" in metric:
                return float(metric["averageHeartRateVariabilityMilliseconds"])
        return None

    async def get_resting_heart_rate(self, target_date: date) -> Optional[float]:
        points = await self._points(
            "daily-resting-heart-rate",
            _day_filter("dailyRestingHeartRate.date", target_date, target_date),
        )
        for point in points:
            metric = point.get("dailyRestingHeartRate", {})
            if "beatsPerMinute" in metric:
                return float(metric["beatsPerMinute"])
        return None

    async def get_hrv_history(self, days: int = 14) -> list[float]:
        # Exclude today: the observation being scored cannot set its own baseline.
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        points = await self._points(
            "daily-heart-rate-variability",
            _day_filter("dailyHeartRateVariability.date", start, end),
        )
        dated = []
        for point in points:
            metric = point.get("dailyHeartRateVariability", {})
            value = metric.get("averageHeartRateVariabilityMilliseconds")
            if value is not None and float(value) > 0:
                dated.append((_google_date(metric["date"]), float(value)))
        return [value for _, value in sorted(dated)]

    async def get_intraday_heart_rate(self, target_date: date) -> list[tuple[datetime, float]]:
        points = await self._points(
            "heart-rate",
            _day_filter("heartRate.sample_time.civil_time", target_date, target_date),
        )
        samples = []
        for point in points:
            metric = point.get("heartRate", {})
            clock = metric.get("sampleTime", {})
            if clock.get("physicalTime") and metric.get("beatsPerMinute") is not None:
                samples.append((
                    _local_datetime(clock["physicalTime"], clock.get("utcOffset", "0s")),
                    float(metric["beatsPerMinute"]),
                ))
        return sorted(samples)

    async def get_workout_sessions(self, target_date: date) -> list[dict]:
        points = await self._points(
            "exercise",
            _day_filter("exercise.interval.civil_start_time", target_date, target_date),
        )
        sessions = []
        for point in points:
            exercise = point.get("exercise", {})
            interval = exercise.get("interval", {})
            if interval.get("startTime") and interval.get("endTime"):
                sessions.append({
                    "start": _local_datetime(interval["startTime"], interval.get("startUtcOffset", "0s")),
                    "end": _local_datetime(interval["endTime"], interval.get("endUtcOffset", "0s")),
                    "activity_name": exercise.get("displayName") or exercise.get("exerciseType", "Workout"),
                })
        return sessions

    async def _sleep_records(self, start: date, end: date) -> list[dict]:
        points = await self._points(
            "sleep", _day_filter("sleep.interval.civil_end_time", start, end)
        )
        records = []
        for point in points:
            sleep = point.get("sleep", {})
            interval = sleep.get("interval", {})
            if sleep.get("metadata", {}).get("nap") or not interval.get("startTime") or not interval.get("endTime"):
                continue
            start_dt = _local_datetime(interval["startTime"], interval.get("startUtcOffset", "0s"))
            end_dt = _local_datetime(interval["endTime"], interval.get("endUtcOffset", "0s"))
            summary = sleep.get("summary", {})
            stage_totals = {s["type"]: float(s["minutes"]) * 60 for s in summary.get("stagesSummary", [])}
            awake_count = sum(int(s.get("count", 0)) for s in summary.get("stagesSummary", []) if s.get("type") == "AWAKE")
            records.append({
                "date": end_dt.date(), "sleep_start_time": start_dt, "sleep_end_time": end_dt,
                "total_duration": float(summary.get("minutesAsleep", 0)) * 60,
                "deep_sleep_duration": stage_totals.get("DEEP", 0.0),
                "rem_sleep_duration": stage_totals.get("REM", 0.0),
                "core_sleep_duration": stage_totals.get("LIGHT", 0.0),
                "awake_duration": float(summary.get("minutesAwake", 0)) * 60,
                "in_bed_duration": float(summary.get("minutesInSleepPeriod", 0)) * 60,
                "interruption_count": awake_count,
                "sleep_latency_seconds": float(summary["minutesToFallAsleep"]) * 60 if "minutesToFallAsleep" in summary else None,
                "nap_duration_seconds": 0.0,
                # These metrics are separate API data types, not fields on a sleep session.
                "sleeping_hrv": None, "sleeping_hr": None, "waking_hr": None,
            })
        # Keep the longest session ending on each local date.
        by_date = {}
        for record in records:
            day = record["date"]
            if day not in by_date or record["total_duration"] > by_date[day]["total_duration"]:
                by_date[day] = record
        return [by_date[day] for day in sorted(by_date)]

    async def get_sleep_session(self, target_date: date) -> Optional[dict]:
        records = await self._sleep_records(target_date, target_date)
        return records[0] if records else None

    async def get_sleep_history_nights(self, days: int = 4) -> list[dict]:
        records = await self._sleep_records(date.today() - timedelta(days=days - 1), date.today())
        return [{"date": r["date"], "bed_time": r["sleep_start_time"],
                 "wake_time": r["sleep_end_time"]} for r in records]

    async def get_sleep_efficiency_history(self, days: int = 7) -> list[dict]:
        records = await self._sleep_records(date.today() - timedelta(days=days - 1), date.today())
        return [{
            "date": r["date"],
            "time_asleep_minutes": r["total_duration"] / 60,
            "time_in_bed_minutes": r["in_bed_duration"] / 60,
            "awake_minutes": r["awake_duration"] / 60,
            "start_time": r["sleep_start_time"], "end_time": r["sleep_end_time"],
        } for r in records]
