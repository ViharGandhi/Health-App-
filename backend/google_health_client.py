"""
google_health_client.py
========================
Wrapper for the Google Health API.
Fetches all raw data needed by the three algorithm files.

Data fetched:
  - Daily HRV (rMSSD) summary        → health_metrics endpoint
  - Resting Heart Rate                → health_metrics endpoint
  - Intraday heart rate (1-min samples) → activity endpoint
  - Sleep session + stages             → sleep endpoint
  - Workout/activity sessions          → activity endpoint

Reference: https://developers.google.com/health
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, date
from typing import Optional

import httpx

# ──────────────────────────────────────────────────────────────────────────────
# Google Health API base URL
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://health.googleapis.com/v1"


class GoogleHealthClient:
    """
    Thin async HTTP client for the Google Health API.
    All methods return parsed Python dicts/lists ready for the algo files.
    """

    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Daily health metrics — HRV, RHR, SpO2
    # ──────────────────────────────────────────────────────────────────────────

    async def get_daily_hrv(self, target_date: date) -> Optional[float]:
        """
        Returns the rMSSD (ms) daily HRV summary for `target_date`.
        Google Health API: GET /v1/users/me/healthMetrics/dailyHrv
        """
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/users/me/healthMetrics/daily-heart-rate-variability"
        params = {"startDate": date_str, "endDate": date_str}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return None

        data = resp.json()
        entries = data.get("dailyHeartRateVariabilities", [])
        if not entries:
            return None

        entry = entries[0]
        # Google Health API returns rMSSD in ms
        return entry.get("rmssd", {}).get("value")

    async def get_resting_heart_rate(self, target_date: date) -> Optional[float]:
        """
        Returns resting heart rate (bpm) for `target_date`.
        Google Health API: health metrics daily summary.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/users/me/healthMetrics/daily-resting-heart-rate"
        params = {"startDate": date_str, "endDate": date_str}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return None

        data = resp.json()
        entries = data.get("dailyRestingHeartRates", [])
        if not entries:
            return None
        return entries[0].get("bpm", {}).get("value")

    async def get_hrv_history(self, days: int = 14) -> list[float]:
        """
        Returns up to `days` of daily HRV values (oldest → newest).
        Used by RecoveryCalculator for log-domain z-score baseline.
        """
        end_date   = date.today()
        start_date = end_date - timedelta(days=days - 1)
        date_str_start = start_date.strftime("%Y-%m-%d")
        date_str_end   = end_date.strftime("%Y-%m-%d")

        url = f"{BASE_URL}/users/me/healthMetrics/daily-heart-rate-variability"
        params = {"startDate": date_str_start, "endDate": date_str_end}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return []

        data = resp.json()
        entries = data.get("dailyHeartRateVariabilities", [])
        # Sort oldest → newest
        entries.sort(key=lambda e: e.get("date", ""))
        return [e.get("rmssd", {}).get("value", 0) for e in entries if e.get("rmssd")]

    # ──────────────────────────────────────────────────────────────────────────
    # Intraday heart rate (1-min samples) — for Strain
    # ──────────────────────────────────────────────────────────────────────────

    async def get_intraday_heart_rate(self, target_date: date) -> list[tuple[datetime, float]]:
        """
        Returns [(datetime, bpm), ...] 1-minute intraday samples.
        Google Health API: activity_and_fitness endpoint for HR series.

        Returns samples sorted by timestamp (oldest first).
        """
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/users/me/healthMetrics/heart-rate"
        params = {
            "startTime": f"{date_str}T00:00:00Z",
            "endTime":   f"{date_str}T23:59:59Z",
            "granularity": "1_MINUTE",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return []

        data = resp.json()
        samples = []
        for point in data.get("heartRateSamples", []):
            ts_str = point.get("timestamp", "")
            bpm    = point.get("bpm", {}).get("value")
            if ts_str and bpm is not None:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    samples.append((ts.replace(tzinfo=None), float(bpm)))
                except ValueError:
                    continue
        return sorted(samples, key=lambda x: x[0])

    # ──────────────────────────────────────────────────────────────────────────
    # Workout / activity sessions — for Strain workout-aware partitioning
    # ──────────────────────────────────────────────────────────────────────────

    async def get_workout_sessions(self, target_date: date) -> list[dict]:
        """
        Returns list of workout sessions for `target_date`.
        Each dict: { start: datetime, end: datetime, activity_name: str }
        """
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/users/me/activitySessions"
        params = {
            "startDate": date_str,
            "endDate":   date_str,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return []

        data = resp.json()
        sessions = []
        for session in data.get("activitySessions", []):
            try:
                start = datetime.fromisoformat(session["startTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                end   = datetime.fromisoformat(session["endTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                name  = session.get("activityType", {}).get("name", "Workout")
                sessions.append({"start": start, "end": end, "activity_name": name})
            except (KeyError, ValueError):
                continue
        return sessions

    # ──────────────────────────────────────────────────────────────────────────
    # Sleep data — for SleepScore
    # ──────────────────────────────────────────────────────────────────────────

    async def get_sleep_session(self, target_date: date) -> Optional[dict]:
        """
        Returns sleep data for the night ending on `target_date`.
        Dict keys match SleepData dataclass fields (durations in seconds).
        Also returns sleeping_hrv, sleeping_hr, waking_hr.
        """
        # Sleep sessions are indexed by the wake date
        date_str = target_date.strftime("%Y-%m-%d")
        url = f"{BASE_URL}/users/me/sleep"
        params = {"startDate": date_str, "endDate": date_str}

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return None

        data = resp.json()
        sessions = data.get("sleepSessions", [])
        if not sessions:
            return None

        # Use the primary (longest) sleep session
        session = max(sessions, key=lambda s: s.get("totalDurationSeconds", 0))

        stages = session.get("stages", {})
        result = {
            "total_duration":       session.get("totalDurationSeconds", 0),
            "deep_sleep_duration":  stages.get("deepSleepDurationSeconds", 0),
            "rem_sleep_duration":   stages.get("remSleepDurationSeconds", 0),
            "core_sleep_duration":  stages.get("lightSleepDurationSeconds", 0),
            "awake_duration":       stages.get("wakeDurationSeconds", 0),
            "in_bed_duration":      session.get("inBedDurationSeconds", 0),
            "interruption_count":   session.get("wakeupCount", 0),
            "nap_duration_seconds": 0.0,
            "sleep_latency_seconds": session.get("sleepLatencySeconds"),
        }

        # Parse start/end times
        try:
            result["sleep_start_time"] = datetime.fromisoformat(
                session["startTime"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
            result["sleep_end_time"] = datetime.fromisoformat(
                session["endTime"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (KeyError, ValueError):
            result["sleep_start_time"] = None
            result["sleep_end_time"]   = None

        # Biometrics during sleep
        biometrics = session.get("biometrics", {})
        result["sleeping_hrv"] = biometrics.get("avgHrvRmssd")
        result["sleeping_hr"]  = biometrics.get("avgHeartRate")
        result["waking_hr"]    = biometrics.get("wakingHeartRate")

        return result

    async def get_sleep_history_nights(self, days: int = 4) -> list[dict]:
        """
        Fetches up to `days` of sleep history to compute Sleep Consistency.
        Google Health API: GET /v1/users/me/sleep?startDate={start}&endDate={end}
        Returns list of parsed dicts: [{"date": date, "bed_time": datetime, "wake_time": datetime}, ...]
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        url = f"{BASE_URL}/users/me/sleep"
        params = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate":   end_date.strftime("%Y-%m-%d"),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return []

        data = resp.json()
        sessions = data.get("sleepSessions", [])
        nights = []

        for s in sessions:
            try:
                start_dt = datetime.fromisoformat(s["startTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                end_dt   = datetime.fromisoformat(s["endTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                # Night date is determined by wake date
                night_date = end_dt.date()
                nights.append({
                    "date": night_date,
                    "bed_time": start_dt,
                    "wake_time": end_dt,
                })
            except (KeyError, ValueError):
                continue

        # Sort chronologically
        nights.sort(key=lambda x: x["bed_time"])
        return nights

    async def get_sleep_efficiency_history(self, days: int = 7) -> list[dict]:
        """
        Fetches up to `days` of sleep history to compute Sleep Efficiency trend.
        Google Health API: GET /v1/users/me/sleep?startDate={start}&endDate={end}
        Returns list of parsed dicts: [
            {
                "date": date,
                "time_asleep_minutes": float,
                "time_in_bed_minutes": float,
                "awake_minutes": float,
                "start_time": datetime,
                "end_time": datetime
            },
            ...
        ]
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        url = f"{BASE_URL}/users/me/sleep"
        params = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate":   end_date.strftime("%Y-%m-%d"),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, params=params)

        if resp.status_code != 200:
            return []

        data = resp.json()
        sessions = data.get("sleepSessions", [])
        nights = []

        for s in sessions:
            try:
                start_dt = datetime.fromisoformat(s["startTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                end_dt   = datetime.fromisoformat(s["endTime"].replace("Z", "+00:00")).replace(tzinfo=None)
                night_date = end_dt.date()
                total_sec = s.get("totalDurationSeconds", 0)
                in_bed_sec = s.get("inBedDurationSeconds", 0)
                stages = s.get("stages", {})
                awake_sec = stages.get("wakeDurationSeconds", 0)
                if in_bed_sec <= 0:
                    in_bed_sec = total_sec + awake_sec

                nights.append({
                    "date": night_date,
                    "time_asleep_minutes": round(total_sec / 60.0, 1),
                    "time_in_bed_minutes": round(in_bed_sec / 60.0, 1),
                    "awake_minutes": round(awake_sec / 60.0, 1),
                    "start_time": start_dt,
                    "end_time": end_dt,
                })
            except (KeyError, ValueError):
                continue

        nights.sort(key=lambda x: x["start_time"])
        return nights

