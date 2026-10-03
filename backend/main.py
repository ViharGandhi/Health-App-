"""
main.py
=======
FastAPI application — the bridge between the Next.js frontend and the
three algorithm files (strain.py, recovery.py, sleepscore.py).

Routes:
  GET  /api/auth/login         → start Google OAuth
  GET  /api/auth/callback      → receive OAuth code, store session
  GET  /api/auth/status        → is the user connected?
  POST /api/auth/disconnect    → clear session
  GET  /api/dashboard          → all three scores (mock or real)
  GET  /api/recovery           → recovery score detail
  GET  /api/sleep              → sleep score detail
  GET  /api/strain             → strain score detail

Run with:
  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import sys
import os
import math
from datetime import datetime, timedelta, date
from statistics import median
from typing import Optional, Literal

# Allow importing the algo files from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env file (must be in the backend/ directory)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Algorithm imports ──────────────────────────────────────────────────────────
from strain import StrainCalculator, WorkoutInterval, HeartRateZone
from sleepscore import SleepCalculator, SleepData
from sleep_consistency import SleepConsistencyCalculator, SleepNight
from sleep_efficiency import SleepEfficiencyCalculator

# ── App-layer imports ──────────────────────────────────────────────────────────
from auth import router as auth_router, get_session, get_valid_access_token, set_session
from google_health_client import GoogleHealthClient
from sleep_trends import build_consistency_scores, build_sleep_trend, range_start
from health_trends import build_health_response
from mock_data import (
    get_mock_dashboard, compute_mock_strain, compute_mock_sleep,
    compute_mock_recovery, get_mock_sleep_consistency_trend, get_mock_sleep_consistency_score,
    get_mock_sleep_efficiency_trend, get_mock_health
)
from models import (
    DashboardResponse, RecoveryResponse, SleepResponse, StrainResponse,
    ZoneMinutes, WorkoutDetail, SleepStages, SleepTrendResponse, SleepConsistencyScoreResponse, HealthResponse
)


# ──────────────────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Ojas Fitness API",
    description="Backend for the Ojas fitness dashboard",
    version="1.0.0",
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount auth router
app.include_router(auth_router)

USER_AGE = int(os.getenv("USER_AGE", "22"))

# 14-day strain load history — persists in memory for dev; replace with DB later
# Seeded with realistic values for the capacity baseline
_STRAIN_LOAD_HISTORY: list[float] = [
    310.0, 340.0, 295.0, 360.0, 320.0, 345.0,
    330.0, 315.0, 355.0, 325.0, 340.0, 350.0,
    320.0, 335.0,
]

# HRV baseline — replace with rolling DB value later
_HRV_BASELINE: float = 41.2
_RHR_BASELINE: float = 56.0


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_token(request: Request, response: Response) -> Optional[str]:
    """Returns a valid access token from the session, or None if not connected."""
    session = get_session(request)
    if not session:
        return None
    old_token = session.get("access_token")
    token = await get_valid_access_token(session)
    if token and token != old_token:
        set_session(response, session)
    return token


def _client_day(request: Request) -> date:
    """Use the wearer's device calendar day for Google daily summaries."""
    supplied = request.headers.get("x-user-date")
    if supplied:
        try:
            return date.fromisoformat(supplied)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-User-Date")
    return date.today()


def _client_age(request: Request) -> Optional[int]:
    supplied = request.headers.get("x-user-age")
    if supplied is None:
        return None
    try:
        age = int(supplied)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-User-Age")
    if not 18 <= age <= 100:
        raise HTTPException(status_code=400, detail="Age must be between 18 and 100")
    return age


# ──────────────────────────────────────────────────────────────────────────────
# Real-data computation (called when Google token is available)
# ──────────────────────────────────────────────────────────────────────────────

async def _compute_real_strain(client: GoogleHealthClient, target_date: date, age: Optional[int] = None) -> StrainResponse:
    max_hr = StrainCalculator.estimated_max_hr(age if age is not None else USER_AGE)

    # Fetch intraday HR samples
    samples = await client.get_intraday_heart_rate(target_date)
    # Fetch workout sessions
    sessions = await client.get_workout_sessions(target_date)
    workout_intervals = [
        WorkoutInterval(start=s["start"], end=s["end"], activity_name=s["activity_name"])
        for s in sessions
    ]

    if not samples:
        # No data today — return zeros
        return StrainResponse(
            score_21=0.0, score_100=0.0,
            workout_strain=0.0, incidental_strain=0.0,
            zone_minutes=ZoneMinutes(), workouts=[],
            max_hr=round(max_hr, 1), avg_hr=None,
            age_used=age if age is not None else USER_AGE, age_is_default=age is None,
            is_calibrating=True, is_mock=False,
        )

    result = StrainCalculator.calculate_workout_aware(workout_intervals, samples, max_hr)
    capacity    = StrainCalculator.capacity(_STRAIN_LOAD_HISTORY)
    calibrating = StrainCalculator.is_calibrating(_STRAIN_LOAD_HISTORY)
    score_100   = StrainCalculator.score(result.total, capacity)
    score_21    = StrainCalculator.score_to_whoop_scale(score_100)

    _, all_zone_mins = StrainCalculator.calculate(samples, max_hr)
    total_zone = ZoneMinutes(
        zone1=all_zone_mins.get(HeartRateZone.ZONE1, 0.0),
        zone2=all_zone_mins.get(HeartRateZone.ZONE2, 0.0),
        zone3=all_zone_mins.get(HeartRateZone.ZONE3, 0.0),
        zone4=all_zone_mins.get(HeartRateZone.ZONE4, 0.0),
        zone5=all_zone_mins.get(HeartRateZone.ZONE5, 0.0),
    )
    workouts = [
        WorkoutDetail(
            activity_name=d.activity_name,
            strain=d.strain,
            zone_minutes=ZoneMinutes(
                zone1=d.zone_minutes.get(HeartRateZone.ZONE1, 0.0),
                zone2=d.zone_minutes.get(HeartRateZone.ZONE2, 0.0),
                zone3=d.zone_minutes.get(HeartRateZone.ZONE3, 0.0),
                zone4=d.zone_minutes.get(HeartRateZone.ZONE4, 0.0),
                zone5=d.zone_minutes.get(HeartRateZone.ZONE5, 0.0),
            ),
        )
        for d in result.details
    ]
    hr_vals = [hr for _, hr in samples]
    avg_hr = sum(hr_vals) / len(hr_vals) if hr_vals else None

    return StrainResponse(
        score_21=round(score_21, 1), score_100=round(score_100, 1),
        workout_strain=round(result.workout_strain, 1),
        incidental_strain=round(result.incidental_strain, 1),
        zone_minutes=total_zone, workouts=workouts,
        max_hr=round(max_hr, 1),
        avg_hr=round(avg_hr, 1) if avg_hr else None,
        age_used=age if age is not None else USER_AGE, age_is_default=age is None,
        is_calibrating=calibrating, is_mock=False,
    )


async def _compute_real_sleep(client: GoogleHealthClient, target_date: date, yesterday_strain_21: float, age: Optional[int] = None) -> SleepResponse:
    raw = await client.get_sleep_session(target_date)
    if not raw:
        # No sleep data — return zeros
        return SleepResponse(
            score=0.0, sleep_need_hours=8.0, total_sleep_hours=0.0,
            sleep_debt_hours=0.0, efficiency_pct=None,
            stages=SleepStages(deep_minutes=0, rem_minutes=0, core_minutes=0, awake_minutes=0, total_minutes=0),
            duration_score=0.0, stage_score=0.0, restfulness_score=0.0, hr_dip_score=0.0,
            is_mock=False,
        )

    sleep = SleepData(
        total_duration=raw["total_duration"],
        deep_sleep_duration=raw["deep_sleep_duration"],
        rem_sleep_duration=raw["rem_sleep_duration"],
        core_sleep_duration=raw["core_sleep_duration"],
        awake_duration=raw["awake_duration"],
        in_bed_duration=raw["in_bed_duration"],
        sleep_start_time=raw.get("sleep_start_time"),
        sleep_end_time=raw.get("sleep_end_time"),
        interruption_count=raw.get("interruption_count", 0),
        nap_duration_seconds=raw.get("nap_duration_seconds", 0.0),
        sleep_latency_seconds=raw.get("sleep_latency_seconds"),
    )

    sleep_need = SleepCalculator.calculate_sleep_need(
        baseline_sleep=7.5,
        yesterday_strain=yesterday_strain_21,
    )
    sleeping_hrv = raw.get("sleeping_hrv")
    sleeping_hr  = raw.get("sleeping_hr")
    waking_hr    = raw.get("waking_hr")

    score = SleepCalculator.calculate_score(
        sleep=sleep,
        sleep_need=sleep_need,
        sleeping_hrv=sleeping_hrv,
        sleeping_hr=sleeping_hr,
        waking_hr=waking_hr,
        hrv_baseline=_HRV_BASELINE,
        sleeping_hr_baseline=(_RHR_BASELINE + 4),
        age=age if age is not None else USER_AGE,
    )

    total_h = sleep.total_duration / 3600.0
    ratio = total_h / sleep_need
    if ratio <= 1.0:
        x = 8.0 * (ratio - 0.75)
        dur_score = 100.0 / (1.0 + math.exp(-x))
    elif ratio <= 1.10:
        dur_score = 100.0
    else:
        dur_score = max(30.0, 100.0 - (ratio - 1.10) * 75.0)

    efficiency = SleepEfficiencyCalculator.calculate_single_night(sleep.total_duration, sleep.in_bed_duration)
    stages = SleepStages(
        deep_minutes=round(sleep.deep_sleep_duration / 60, 1),
        rem_minutes=round(sleep.rem_sleep_duration / 60, 1),
        core_minutes=round(sleep.core_sleep_duration / 60, 1),
        awake_minutes=round(sleep.awake_duration / 60, 1),
        total_minutes=round(sleep.total_duration / 60, 1),
    )
    sleep_debt = SleepCalculator.compute_sleep_debt([(sleep_need, total_h)])
    restfulness = SleepCalculator.compute_restfulness_score(sleep)
    hr_dip = SleepCalculator.compute_hr_dip_score(sleeping_hr, waking_hr)
    sn_s = sleep_need * 3600
    deep_tgt = SleepCalculator.optimal_deep_ratio(age if age is not None else USER_AGE)
    d_s = min(100.0, (sleep.deep_sleep_duration / sn_s / deep_tgt) * 100) if sn_s > 0 else 0
    r_s = min(100.0, (sleep.rem_sleep_duration  / sn_s / 0.20) * 100) if sn_s > 0 else 0
    c_s = min(100.0, (sleep.core_sleep_duration / sn_s / 0.50) * 100) if sn_s > 0 else 0
    stage_score = 0.40 * d_s + 0.40 * r_s + 0.20 * c_s
    # Seven consecutive nights are required for timing variability.
    history_nights = await client.get_sleep_history_nights(days=7, end_date=target_date)
    parsed_nights = [
        SleepNight(night_date=n["date"], bed_time=n["bed_time"], wake_time=n["wake_time"])
        for n in history_nights
    ]
    consistency_res = SleepConsistencyCalculator.calculate(parsed_nights)
    deep_sleep_hrv = await client.get_deep_sleep_hrv(target_date)

    return SleepResponse(
        score=round(score, 1),
        sleep_need_hours=round(sleep_need, 2),
        total_sleep_hours=round(total_h, 2),
        sleep_debt_hours=round(max(0.0, sleep_debt), 2),
        efficiency_pct=efficiency,
        stages=stages,
        sleeping_hrv=sleeping_hrv,
        deep_sleep_hrv=deep_sleep_hrv,
        sleeping_hr=sleeping_hr,
        consistency_minutes=consistency_res.timing_variability_minutes,
        average_bed_time=consistency_res.average_bed_time_str,
        average_wake_time=consistency_res.average_wake_time_str,
        sleep_start=raw.get("sleep_start_time") and raw["sleep_start_time"].strftime("%I:%M %p"),
        sleep_end=raw.get("sleep_end_time") and raw["sleep_end_time"].strftime("%I:%M %p"),
        duration_score=round(dur_score, 1),
        stage_score=round(stage_score, 1),
        restfulness_score=round(restfulness, 1),
        hr_dip_score=round(hr_dip, 1),
        is_mock=False,
    )


async def _compute_real_recovery(
    client: GoogleHealthClient,
    target_date: date,
    sleep_hours: Optional[float] = None,
    sleep_efficiency_pct: Optional[float] = None,
) -> RecoveryResponse:
    history = await client.get_health_history(target_date - timedelta(days=14), target_date, ("hrv", "rhr"))
    today_key = target_date.isoformat()
    today_hrv_point = next((point for point in history["hrv"] if point["date"] == today_key), None)
    today_rhr_point = next((point for point in history["rhr"] if point["date"] == today_key), None)
    today_hrv = today_hrv_point["value"] if today_hrv_point else None
    today_rhr = today_rhr_point["value"] if today_rhr_point else None
    rhr_method = today_rhr_point.get("method") if today_rhr_point else None
    hrv_history = [point["value"] for point in history["hrv"] if point["date"] < today_key and point["value"] > 0]
    rhr_history = [point["value"] for point in history["rhr"] if point["date"] < today_key and point["value"] > 0 and point.get("method") == rhr_method]
    calibrating = (
        today_hrv is None or today_hrv <= 0 or today_rhr is None or today_rhr <= 0
        or len(hrv_history) < 7 or len(rhr_history) < 7
    )
    return RecoveryResponse(
        score=None, status="calibrating" if calibrating else "signals",
        today_hrv=today_hrv if today_hrv is not None and today_hrv > 0 else None,
        today_rhr=today_rhr if today_rhr is not None and today_rhr > 0 else None,
        hrv_baseline=round(median(hrv_history), 1) if len(hrv_history) >= 7 else None,
        rhr_baseline=round(median(rhr_history), 1) if len(rhr_history) >= 7 else None,
        hrv_reference_count=len(hrv_history), rhr_reference_count=len(rhr_history),
        rhr_method=rhr_method,
        sleep_hours=sleep_hours, sleep_efficiency_pct=sleep_efficiency_pct,
        training_recommendation="",
        is_calibrating=calibrating,
        is_mock=False,
    )


# ──────────────────────────────────────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "message": "Ojas Fitness API is running"}


@app.get("/api/dashboard", response_model=DashboardResponse)
async def dashboard(request: Request, response: Response):
    """
    Returns all three scores in one call.
    Mock mode if no Google token is present; real mode otherwise.
    """
    token = await _get_token(request, response)
    if not token:
        return get_mock_dashboard()

    client = GoogleHealthClient(token)
    today = _client_day(request)
    age = _client_age(request)
    yesterday = today - timedelta(days=1)

    # Compute in dependency order: strain(yesterday) → sleep → recovery
    yest_strain = await _compute_real_strain(client, yesterday, age)
    sleep   = await _compute_real_sleep(client, today, yest_strain.score_21, age)
    strain  = await _compute_real_strain(client, today, age)
    recovery = await _compute_real_recovery(client, today, sleep.total_sleep_hours, sleep.efficiency_pct)

    return DashboardResponse(
        recovery=recovery,
        sleep=sleep,
        strain=strain,
        date=today.strftime("%Y-%m-%d"),
        is_mock=False,
    )


@app.get("/api/recovery", response_model=RecoveryResponse)
async def recovery_endpoint(request: Request, response: Response):
    token = await _get_token(request, response)
    if not token:
        mock = get_mock_dashboard()
        return mock.recovery

    client = GoogleHealthClient(token)
    today = _client_day(request)
    sleep = await client.get_sleep_session(today)
    sleep_hours = round(sleep["total_duration"] / 3600, 2) if sleep else None
    efficiency = SleepEfficiencyCalculator.calculate_single_night(sleep["total_duration"], sleep["in_bed_duration"]) if sleep else None
    return await _compute_real_recovery(client, today, sleep_hours, efficiency)


@app.get("/api/sleep", response_model=SleepResponse)
async def sleep_endpoint(request: Request, response: Response):
    token = await _get_token(request, response)
    if not token:
        mock = get_mock_dashboard()
        return mock.sleep

    client = GoogleHealthClient(token)
    today = _client_day(request)
    age = _client_age(request)
    yesterday = today - timedelta(days=1)
    yest_strain = await _compute_real_strain(client, yesterday, age)
    return await _compute_real_sleep(client, today, yest_strain.score_21, age)


@app.get("/api/strain", response_model=StrainResponse)
async def strain_endpoint(request: Request, response: Response):
    token = await _get_token(request, response)
    if not token:
        mock = get_mock_dashboard()
        return mock.strain

    client = GoogleHealthClient(token)
    return await _compute_real_strain(client, _client_day(request), _client_age(request))


@app.get("/api/health", response_model=HealthResponse)
async def health_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "1Y"] = "W"
):
    token = await _get_token(request, response)
    if not token:
        return get_mock_health(timeframe)
    today = _client_day(request)
    start = range_start(today, timeframe)
    client = GoogleHealthClient(token)
    history = await client.get_health_history(start - timedelta(days=14), today)
    samples = await client.get_intraday_heart_rate(today)
    return build_health_response(history, samples, start, today, timeframe, False)


@app.get("/api/sleep/consistency", response_model=SleepTrendResponse)
async def sleep_consistency_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "1Y"] = "W"
):
    token = await _get_token(request, response)
    if not token:
        return get_mock_sleep_consistency_trend(timeframe)
    today = _client_day(request)
    start = range_start(today, timeframe)
    client = GoogleHealthClient(token)
    history = await client.get_sleep_trend_history(start - timedelta(days=6), today)
    return build_sleep_trend(history, start, today, timeframe, "consistency", False)


@app.get("/api/sleep/consistency/score", response_model=SleepConsistencyScoreResponse)
async def sleep_consistency_score_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "Y"] = "W"
):
    today = _client_day(request)
    token = await _get_token(request, response)
    if not token:
        return get_mock_sleep_consistency_score(timeframe, today)
    start = range_start(today, timeframe)
    previous_start = range_start(start - timedelta(days=1), timeframe)
    client = GoogleHealthClient(token)
    history = await client.get_main_sleep_timing_history(previous_start - timedelta(days=4), today)
    return build_consistency_scores(history, today, timeframe, False)


@app.get("/api/sleep/efficiency", response_model=SleepTrendResponse)
async def sleep_efficiency_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "1Y"] = "W"
):
    token = await _get_token(request, response)
    if not token:
        return get_mock_sleep_efficiency_trend(timeframe)
    today = _client_day(request)
    start = range_start(today, timeframe)
    client = GoogleHealthClient(token)
    history = await client.get_sleep_trend_history(start, today)
    return build_sleep_trend(history, start, today, timeframe, "efficiency", False)
