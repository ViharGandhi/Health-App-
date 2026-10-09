"""Read Fitbit wearable data from the Google Health API v4."""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from health_read_store import HealthReadStore, ReadRange, read_range, exact_key, CacheInvalidated
from read_metrics import count


BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
WEARABLES = "users/me/dataSourceFamilies/google-wearables"

# Short-lived, process-local reads; never share results between access tokens.
_point_cache: OrderedDict = OrderedDict()
_point_requests: dict = {}
_request_lanes: OrderedDict = OrderedDict()
_range_locks: dict = {}


@lru_cache(maxsize=4)
def read_store(path: str) -> HealthReadStore:
    return HealthReadStore(path)


def _day_filter(field: str, start: date, end: date) -> str:
    """Build an inclusive local-date range with an exclusive upper bound."""
    return (f'{field} >= "{start.isoformat()}" AND '
            f'{field} < "{(end + timedelta(days=1)).isoformat()}"')


def _local_datetime(value: str, offset: str, *, preserve_offset: bool = False) -> datetime:
    """Return wall-clock time in the offset supplied by Google."""
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    seconds = float(offset.removesuffix("s")) if offset else 0.0
    local = instant.astimezone(timezone(timedelta(seconds=seconds)))
    return local if preserve_offset else local.replace(tzinfo=None)


def _google_date(value: dict) -> date:
    return date(value["year"], value["month"], value["day"])


class GoogleHealthClient:
    def __init__(self, access_token: str, *, cache: bool = False, account_id: str | None = None,
                 store: HealthReadStore | None = None):
        self.cache = cache
        self.account_key = hashlib.sha256((f'account:{account_id}' if account_id else access_token).encode()).hexdigest()
        self.store = (store or read_store(os.getenv('HEALTH_DATA_DB_PATH', str(Path(__file__).parent / 'data' / 'health_cache.sqlite3')))) if cache and account_id else None
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def _points(self, data_type: str, filter_expr: str, *, reconcile: bool = True) -> list[dict]:
        if self.store and getattr(self, 'stored_only', False):
            count('database_hits')
            query = read_range(filter_expr)
            if query is None:
                before = re.fullmatch(r'([a-z_.]+) < "([^"]+)"', filter_expr)
                if before:
                    query = read_range(f'{before[1]} >= "1900-01-01" AND {before[1]} < "{before[2]}"')
            if query:
                return await asyncio.to_thread(self.store.local_read, self.account_key, data_type, query, reconcile)
            return await asyncio.to_thread(self.store.exact_read, self.account_key,
                                          exact_key(data_type, filter_expr, reconcile), now=0) or []
        if not self.cache:
            return await self._fetch_points(data_type, filter_expr, reconcile=reconcile)
        key = (self.account_key, data_type, filter_expr, reconcile)
        if self.store:
            key += (await asyncio.to_thread(self.store.epoch, self.account_key),)
        cached = _point_cache.get(key)
        if cached and cached[0] > time.monotonic():
            count('memory_hits')
            _point_cache.move_to_end(key)
            return cached[1]
        request_key = (asyncio.get_running_loop(),) + key
        if request_key not in _point_requests:
            _point_requests[request_key] = asyncio.create_task(self._cache_points(key, data_type, filter_expr, reconcile, request_key))
        return await asyncio.shield(_point_requests[request_key])

    async def _cache_points(self, key: tuple, data_type: str, filter_expr: str, reconcile: bool, request_key=None) -> list[dict]:
        try:
            points = await self._stored_points(data_type, filter_expr, reconcile) if self.store else await self._fetch_points(data_type, filter_expr, reconcile=reconcile)
            _point_cache[key] = (time.monotonic() + 60, points)
            _point_cache.move_to_end(key)
            while len(_point_cache) > 64:
                _point_cache.popitem(last=False)
            return points
        finally:
            _point_requests.pop(request_key or key, None)

    async def _stored_points(self, kind: str, expression: str, reconciled: bool) -> list[dict]:
        for attempt in range(3):
            try:
                return await self._read_stored_points(kind, expression, reconciled)
            except CacheInvalidated:
                if attempt == 2:
                    raise

    async def _read_stored_points(self, kind: str, expression: str, reconciled: bool) -> list[dict]:
        key = exact_key(kind, expression, reconciled)
        query = read_range(expression)
        # Serialize overlapping reads of the same stream, not unrelated metrics.
        lane_key = (asyncio.get_running_loop(), self.account_key, kind, query.field if query else key, reconciled)
        lock = _range_locks.setdefault(lane_key, asyncio.Lock())
        async with lock:
            epoch = await asyncio.to_thread(self.store.epoch, self.account_key)
            exact = await asyncio.to_thread(self.store.exact_read, self.account_key, key)
            if exact is not None:
                count('database_hits')
                return exact
            if query:
                points, missing = await asyncio.to_thread(self.store.range_read, self.account_key, kind, query, reconciled)
                if not missing:
                    count('database_hits')
                    return points
                for lower, upper in missing:
                    points = await self._fetch_points(kind, query.expression(lower, upper), reconcile=reconciled)
                    stored = await asyncio.to_thread(self.store.range_write, self.account_key, kind,
                                                     ReadRange(query.field, lower, upper), reconciled, points, epoch=epoch)
                    if not stored:
                        # Unknown point schemas retain the original exact response.
                        full = points if missing == [(query.start, query.end)] else await self._fetch_points(kind, expression, reconcile=reconciled)
                        await asyncio.to_thread(self.store.exact_write, self.account_key, key, full, epoch=epoch)
                        return full
                    self._invalidate_calculations()
                points, missing = await asyncio.to_thread(self.store.range_read, self.account_key, kind, query, reconciled)
                if not missing:
                    return points
            points = await self._fetch_points(kind, expression, reconcile=reconciled)
            await asyncio.to_thread(self.store.exact_write, self.account_key, key, points, epoch=epoch)
            return points

    def _invalidate_calculations(self):
        # Daily Strain also feeds Sleep Need and Recovery. A corrected stored
        # reading must not leave a six-hour-old historical calculation alive.
        from strain_service import _daily_cache
        for key in list(_daily_cache):
            if key[0] == self.account_key:
                _daily_cache.pop(key, None)

    async def _pace_request(self) -> None:
        if not self.cache:
            return
        key = (asyncio.get_running_loop(), self.account_key)
        if key not in _request_lanes:
            _request_lanes[key] = [asyncio.Lock(), 0.0]
        lane = _request_lanes[key]
        _request_lanes.move_to_end(key)
        while len(_request_lanes) > 64:
            _request_lanes.popitem(last=False)
        async with lane[0]:
            delay = lane[1] - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            lane[1] = time.monotonic() + 0.5

    async def _fetch_points(self, data_type: str, filter_expr: str, *, reconcile: bool = True) -> list[dict]:
        """Fetch every page; reconcile wearable data by default, or list raw sessions."""
        url = f"{BASE_URL}/{data_type}/dataPoints" + (":reconcile" if reconcile else "")
        params = {"filter": filter_expr, "pageSize": 25 if data_type in ("sleep", "exercise") else 10000}
        if reconcile:
            params["dataSourceFamily"] = WEARABLES
        points: list[dict] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                for attempt in range(4):
                    await self._pace_request()
                    started = time.monotonic()
                    response = await client.get(url, headers=self.headers, params=params)
                    count('google_requests')
                    count('google_ms', (time.monotonic() - started) * 1000)
                    if response.status_code not in (429, 503) or attempt == 3:
                        break
                    retry_after = response.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2 ** attempt
                    await asyncio.sleep(min(delay, 30))
                response.raise_for_status()
                payload = response.json()
                points.extend(payload.get("dataPoints", []))
                token = payload.get("nextPageToken")
                if not token:
                    return points
                params["pageToken"] = token

    async def get_sleep_stage_points(self, start: date | None, end: date) -> list[dict]:
        """List identifiable sleep sessions, preserving IDs for upserts and webhook jobs."""
        field = "sleep.interval.civil_end_time"
        expr = (_day_filter(field, start, end) if start else
                f'{field} < "{(end + timedelta(days=1)).isoformat()}"')
        return await self._points("sleep", expr, reconcile=False)

    async def get_health_user_id(self) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get("https://health.googleapis.com/v4/users/me/identity", headers=self.headers)
            response.raise_for_status()
            return response.json()["healthUserId"]

    async def get_sleep_heart_rate_points(self, start: datetime, end: datetime) -> list[dict]:
        """Raw timestamped BPM for one sleep, including sleeps spanning midnight/DST."""
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("Require an ordered, timezone-aware sleep interval")
        start_text = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end_text = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return await self._points("heart-rate", (
            f'heart_rate.sample_time.physical_time >= "{start_text}" AND '
            f'heart_rate.sample_time.physical_time < "{end_text}"'
        ))

    async def get_daily_hrv(self, target_date: date) -> Optional[float]:
        points = await self._points(
            "daily-heart-rate-variability",
            _day_filter("daily_heart_rate_variability.date", target_date, target_date),
        )
        for point in points:
            metric = point.get("dailyHeartRateVariability", {})
            if "averageHeartRateVariabilityMilliseconds" in metric:
                return float(metric["averageHeartRateVariabilityMilliseconds"])
        return None

    async def get_deep_sleep_hrv(self, target_date: date) -> Optional[float]:
        points = await self._points(
            "daily-heart-rate-variability",
            _day_filter("daily_heart_rate_variability.date", target_date, target_date),
        )
        for point in points:
            value = point.get("dailyHeartRateVariability", {}).get(
                "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds"
            )
            if value is not None:
                return float(value)
        return None

    async def get_resting_heart_rate(self, target_date: date) -> Optional[float]:
        points = await self._points(
            "daily-resting-heart-rate",
            _day_filter("daily_resting_heart_rate.date", target_date, target_date),
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
            _day_filter("daily_heart_rate_variability.date", start, end),
        )
        dated = []
        for point in points:
            metric = point.get("dailyHeartRateVariability", {})
            value = metric.get("averageHeartRateVariabilityMilliseconds")
            if value is not None and float(value) > 0:
                dated.append((_google_date(metric["date"]), float(value)))
        return [value for _, value in sorted(dated)]

    async def get_health_history(self, start: date, end: date, metrics: tuple[str, ...] | None = None) -> dict[str, list[dict]]:
        """Fetch dated Fitbit Air summaries; optional API fields stay absent."""
        specs = {
            "hrv": ("daily-heart-rate-variability", "dailyHeartRateVariability", "averageHeartRateVariabilityMilliseconds"),
            "deep_sleep_hrv": ("daily-heart-rate-variability", "dailyHeartRateVariability", "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds"),
            "nrem_hr": ("daily-heart-rate-variability", "dailyHeartRateVariability", "nonRemHeartRateBeatsPerMinute"),
            "rhr": ("daily-resting-heart-rate", "dailyRestingHeartRate", "beatsPerMinute"),
            "spo2": ("daily-oxygen-saturation", "dailyOxygenSaturation", "averagePercentage"),
            "respiratory_rate": ("daily-respiratory-rate", "dailyRespiratoryRate", "breathsPerMinute"),
            "skin_temperature": ("daily-sleep-temperature-derivations", "dailySleepTemperatureDerivations", "nightlyTemperatureCelsius"),
            "vo2_max": ("daily-vo2-max", "dailyVo2Max", "vo2Max"),
        }
        history: dict[str, list[dict]] = {}
        fetched: dict[str, list[dict]] = {}
        for key, (data_type, field, value_field) in specs.items():
            if metrics is not None and key not in metrics:
                continue
            if data_type not in fetched:
                fetched[data_type] = await self._points(data_type, _day_filter(f"{data_type.replace('-', '_')}.date", start, end))
            dated = {}
            for point in fetched[data_type]:
                metric = point.get(field, {})
                value = metric.get(value_field)
                if not metric.get("date") or value is None:
                    continue
                day = _google_date(metric["date"])
                if start <= day <= end:
                    dated[day.isoformat()] = {
                        "date": day.isoformat(), "value": float(value),
                        "estimated": metric.get("estimated") if key == "vo2_max" else None,
                        "method": metric.get("dailyRestingHeartRateMetadata", {}).get("calculationMethod") if key == "rhr" else None,
                    }
            history[key] = [dated[day] for day in sorted(dated)]
        return history

    async def get_intraday_heart_rate(self, target_date: date, end_date: date | None = None, *, preserve_offset: bool = False) -> list[tuple[datetime, float]]:
        points = await self._points(
            "heart-rate",
            _day_filter("heart_rate.sample_time.civil_time", target_date, end_date or target_date),
        )
        samples = []
        for point in points:
            metric = point.get("heartRate", {})
            clock = metric.get("sampleTime", {})
            if clock.get("physicalTime") and metric.get("beatsPerMinute") is not None:
                samples.append((
                    _local_datetime(clock["physicalTime"], clock.get("utcOffset", "0s"), preserve_offset=preserve_offset),
                    float(metric["beatsPerMinute"]),
                ))
        return sorted(samples)

    async def get_sleep_stress_points(self, start: date, end: date) -> tuple[list[dict], list[dict], list[dict]]:
        """Fetch paginated sleep, sample RMSSD, and sample HR for overnight scoring."""
        sample_start = f"{(start - timedelta(days=1)).isoformat()}T00:00:00Z"
        sample_end = f"{(end + timedelta(days=2)).isoformat()}T00:00:00Z"
        def sample_filter(field: str) -> str:
            return f'{field} >= "{sample_start}" AND {field} < "{sample_end}"'

        sleep = await self.get_sleep_stage_points(start, end)
        hrv = await self._points("heart-rate-variability", sample_filter(
            "heart_rate_variability.sample_time.physical_time"))
        hr = await self._points("heart-rate", sample_filter("heart_rate.sample_time.physical_time"))
        return sleep, hrv, hr

    async def get_workout_sessions(self, target_date: date, end_date: date | None = None, *, preserve_offset: bool = False) -> list[dict]:
        points = await self._points(
            "exercise",
            _day_filter("exercise.interval.civil_start_time", target_date, end_date or target_date),
        )
        sessions = []
        for point in points:
            exercise = point.get("exercise", {})
            interval = exercise.get("interval", {})
            if interval.get("startTime") and interval.get("endTime"):
                sessions.append({
                    "start": _local_datetime(interval["startTime"], interval.get("startUtcOffset", "0s"), preserve_offset=preserve_offset),
                    "end": _local_datetime(interval["endTime"], interval.get("endUtcOffset", "0s"), preserve_offset=preserve_offset),
                    "activity_name": exercise.get("displayName") or exercise.get("exerciseType", "Workout"),
                    "exercise_type": exercise.get("exerciseType"),
                    "active_minutes": float(exercise["activeDuration"].removesuffix("s")) / 60 if exercise.get("activeDuration") else
                        (datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00")) -
                         datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00"))).total_seconds() / 60,
                })
        return sessions

    async def get_daily_steps(self, start: date, end: date) -> dict[date, int]:
        if self.store and getattr(self, 'stored_only', False):
            values = await asyncio.to_thread(self.store.stored_steps, self.account_key, start, end)
            return {date.fromisoformat(day): value for day, value in values.items()}
        if not self.store:
            return await self._fetch_daily_steps(start, end)
        key = exact_key('steps-rollup', f'{start}/{end}', True)
        lane_key = (asyncio.get_running_loop(), self.account_key, key)
        async with _range_locks.setdefault(lane_key, asyncio.Lock()):
            epoch = await asyncio.to_thread(self.store.epoch, self.account_key)
            cached = await asyncio.to_thread(self.store.exact_read, self.account_key, key)
            if cached is not None:
                return {date.fromisoformat(day): count for day, count in cached.items()}
            values = await self._fetch_daily_steps(start, end)
            try:
                await asyncio.to_thread(self.store.exact_write, self.account_key, key,
                                        {day.isoformat(): count for day, count in values.items()}, epoch=epoch)
            except CacheInvalidated:
                # The next read re-fetches; never repopulate storage after refresh.
                pass
            return values

    async def _fetch_daily_steps(self, start: date, end: date) -> dict[date, int]:
        """Wearable daily rollups preserve absent readings separately from true zeros."""
        values = {}
        lower = start
        async with httpx.AsyncClient(timeout=20.0) as client:
            while lower <= end:
                upper = min(end + timedelta(days=1), lower + timedelta(days=90))
                body = {"range": {"start": {"date": {"year": lower.year, "month": lower.month, "day": lower.day}},
                                  "end": {"date": {"year": upper.year, "month": upper.month, "day": upper.day}}},
                        "windowSizeDays": 1, "pageSize": 10000, "dataSourceFamily": WEARABLES}
                while True:
                    for attempt in range(4):
                        await self._pace_request()
                        started = time.monotonic()
                        response = await client.post(f"{BASE_URL}/steps/dataPoints:dailyRollUp", headers=self.headers, json=body)
                        count('google_requests')
                        count('google_ms', (time.monotonic() - started) * 1000)
                        if response.status_code not in (429, 503) or attempt == 3:
                            break
                        retry_after = response.headers.get("Retry-After", "")
                        delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2 ** attempt
                        await asyncio.sleep(min(delay, 30))
                    response.raise_for_status()
                    payload = response.json()
                    for point in payload.get("rollupDataPoints", []):
                        step_count = point.get("steps", {}).get("countSum")
                        if step_count is not None:
                            day = _google_date(point["civilStartTime"]["date"])
                            if start <= day <= end:
                                values[day] = int(step_count)
                    if not payload.get("nextPageToken"):
                        break
                    body["pageToken"] = payload["nextPageToken"]
                lower = upper
        return values

    async def _sleep_records(self, start: date, end: date) -> list[dict]:
        points = await self._points(
            "sleep", _day_filter("sleep.interval.civil_end_time", start, end)
        )
        records = []
        for point in points:
            sleep = point.get("sleep", {})
            interval = sleep.get("interval", {})
            metadata = sleep.get("metadata", {})
            if metadata.get("nap") or not interval.get("startTime") or not interval.get("endTime"):
                continue
            start_dt = _local_datetime(interval["startTime"], interval.get("startUtcOffset", "0s"))
            end_dt = _local_datetime(interval["endTime"], interval.get("endUtcOffset", "0s"))
            summary = sleep.get("summary", {})
            onset = start_dt + timedelta(minutes=float(summary.get("minutesToFallAsleep", 0)))
            wake = end_dt - timedelta(minutes=float(summary.get("minutesAfterWakeUp", 0)))
            if onset >= wake:
                continue
            stage_totals = {s["type"]: float(s["minutes"]) * 60 for s in summary.get("stagesSummary", [])}
            awake_count = sum(int(s.get("count", 0)) for s in summary.get("stagesSummary", []) if s.get("type") == "AWAKE")
            asleep_minutes = float(summary.get("minutesAsleep") or 0)
            physical_start = datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00"))
            physical_end = datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00"))
            duration_available = (summary.get("minutesAsleep") is not None and metadata.get("processed") is not False
                                  and physical_start.tzinfo is not None and physical_end.tzinfo is not None
                                  and physical_end <= datetime.now(timezone.utc) and math.isfinite(asleep_minutes)
                                  and 0 <= asleep_minutes <= (physical_end - physical_start).total_seconds() / 60)
            records.append({
                "date": end_dt.date(), "sleep_start_time": start_dt, "sleep_end_time": end_dt,
                "sleep_onset_time": onset, "wake_up_time": wake,
                "main_sleep": metadata.get("mainSleep"),
                "total_duration": asleep_minutes * 60,
                "sleep_duration_available": duration_available,
                "stage_breakdown_available": bool(summary.get('stagesSummary')),
                "restfulness_available": summary.get('minutesAwake') is not None,
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
        # Use Fitbit's main-sleep designation; only fall back for older records without it.
        by_date: dict[date, list[dict]] = {}
        for record in records:
            by_date.setdefault(record["date"], []).append(record)
        selected = []
        for day in sorted(by_date):
            sessions = by_date[day]
            main = [record for record in sessions if record["main_sleep"] is True]
            if not main and any(record["main_sleep"] is not None for record in sessions):
                continue
            selected.append(max(main or sessions, key=lambda record: record["total_duration"]))
        return selected

    async def get_sleep_need_history(self, start: date, end: date) -> dict[date, float | None]:
        records = await self._sleep_records(start, end)
        return {record["date"]: record["total_duration"] / 60 if record["sleep_duration_available"] else None
                for record in records if start <= record["date"] <= end}

    async def get_nap_minutes_history(self, start: date, end: date) -> dict[date, float]:
        points = await self._points("sleep", _day_filter("sleep.interval.civil_end_time", start, end))
        naps = {}
        now = datetime.now(timezone.utc)
        for point in points:
            sleep = point.get("sleep", {})
            metadata, summary = sleep.get("metadata", {}), sleep.get("summary", {})
            interval = sleep.get("interval", {})
            if not metadata.get("nap") or metadata.get("processed") is False or summary.get("minutesAsleep") is None:
                continue
            if not interval.get("startTime") or not interval.get("endTime"):
                continue
            left = datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00"))
            right = datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00"))
            minutes = float(summary["minutesAsleep"])
            if left.tzinfo is None or right.tzinfo is None or right > now or not 0 <= minutes <= (right - left).total_seconds() / 60 or not math.isfinite(minutes):
                continue
            day = _local_datetime(interval["endTime"], interval.get("endUtcOffset", "0s")).date()
            if start <= day <= end:
                naps[point.get("name") or (interval["startTime"], interval["endTime"])] = (day, minutes)
        totals = {}
        for day, minutes in naps.values():
            totals[day] = totals.get(day, 0.0) + minutes
        return totals

    async def get_sleep_session(self, target_date: date) -> Optional[dict]:
        records = await self._sleep_records(target_date, target_date)
        return records[0] if records else None

    async def get_sleep_history_nights(self, days: int = 4, end_date: date | None = None) -> list[dict]:
        end = end_date or date.today()
        records = await self._sleep_records(end - timedelta(days=days - 1), end)
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

    async def get_sleep_trend_history(self, start: date, end: date) -> list[dict]:
        records = await self._sleep_records(start, end)
        return [{
            "date": record["date"],
            "bed_time": record["sleep_start_time"],
            "wake_time": record["sleep_end_time"],
            "time_asleep_minutes": record["total_duration"] / 60,
            "time_in_bed_minutes": record["in_bed_duration"] / 60,
        } for record in records]

    async def get_main_sleep_timing_history(self, start: date, end: date) -> list[dict]:
        records = await self._sleep_records(start, end)
        return [{
            "date": record["date"],
            "bed_time": record["sleep_onset_time"],
            "wake_time": record["wake_up_time"],
        } for record in records]
