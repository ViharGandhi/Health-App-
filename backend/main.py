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
from typing import Optional

# Allow importing the algo files from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load .env file (must be in the backend/ directory)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Algorithm imports ──────────────────────────────────────────────────────────
from strain import StrainCalculator, WorkoutInterval, HeartRateZone
from recovery import RecoveryCalculator, RecoveryInput
from sleepscore import SleepCalculator, SleepData
from sleep_consistency import SleepConsistencyCalculator, SleepNight

# ── App-layer imports ──────────────────────────────────────────────────────────
from auth import router as auth_router, get_session, get_valid_access_token, set_session
from google_health_client import GoogleHealthClient
from mock_data import get_mock_dashboard, compute_mock_strain, compute_mock_sleep, compute_mock_recovery
from models import (
    DashboardResponse, RecoveryResponse, SleepResponse, StrainResponse,
    ZoneMinutes, WorkoutDetail, SleepStages
)

# ──────────────────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Soma Fitness API",
    description="Backend for the WHOOP-style Fitbit dashboard",
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

async def _get_token(request: Request) -> Optional[str]:
    """Returns a valid access token from the session, or None if not connected."""
    session = get_session(request)
    if not session:
        return None
    token = await get_valid_access_token(session)
    # Persist refreshed token back to cookie
    if token:
        response = JSONResponse({})  # dummy — token update handled in route
        set_session(response, session)
    return token


def _recovery_status(score: float) -> str:
    if score >= 67:
        return "green"
    elif score >= 34:
        return "yellow"
    return "red"


# ──────────────────────────────────────────────────────────────────────────────
# Real-data computation (called when Google token is available)
# ──────────────────────────────────────────────────────────────────────────────

async def _compute_real_strain(client: GoogleHealthClient, target_date: date) -> StrainResponse:
    max_hr = StrainCalculator.estimated_max_hr(USER_AGE)

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
        is_calibrating=calibrating, is_mock=False,
    )


async def _compute_real_sleep(client: GoogleHealthClient, target_date: date, yesterday_strain_21: float) -> SleepResponse:
    raw = await client.get_sleep_session(target_date)
    if not raw:
        # No sleep data — return zeros
        return SleepResponse(
            score=0.0, sleep_need_hours=8.0, total_sleep_hours=0.0,
            sleep_debt_hours=0.0, efficiency_pct=0.0,
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
        age=USER_AGE,
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

    efficiency = sleep.total_duration / sleep.in_bed_duration * 100 if sleep.in_bed_duration > 0 else 0
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
    deep_tgt = SleepCalculator.optimal_deep_ratio(USER_AGE)
    d_s = min(100.0, (sleep.deep_sleep_duration / sn_s / deep_tgt) * 100) if sn_s > 0 else 0
    r_s = min(100.0, (sleep.rem_sleep_duration  / sn_s / 0.20) * 100) if sn_s > 0 else 0
    c_s = min(100.0, (sleep.core_sleep_duration / sn_s / 0.50) * 100) if sn_s > 0 else 0
    # 4-day sleep consistency calculation
    history_nights = await client.get_sleep_history_nights(days=4)
    parsed_nights = [
        SleepNight(night_date=n["date"], bed_time=n["bed_time"], wake_time=n["wake_time"])
        for n in history_nights
    ]
    consistency_res = SleepConsistencyCalculator.calculate(parsed_nights)

    return SleepResponse(
        score=round(score, 1),
        sleep_need_hours=round(sleep_need, 2),
        total_sleep_hours=round(total_h, 2),
        sleep_debt_hours=round(max(0.0, sleep_debt), 2),
        efficiency_pct=round(efficiency, 1),
        stages=stages,
        sleeping_hrv=sleeping_hrv,
        sleeping_hr=sleeping_hr,
        consistency_score=round(consistency_res.consistency_score, 1),
        average_bed_time=consistency_res.average_bed_time_str,
        average_wake_time=consistency_res.average_wake_time_str,
        consistency_status=consistency_res.status,
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
    sleep_score: float,
    strain_21: float,
) -> RecoveryResponse:
    today_hrv = await client.get_daily_hrv(target_date)
    today_rhr = await client.get_resting_heart_rate(target_date)
    hrv_history = await client.get_hrv_history(days=14)

    inp = RecoveryInput(
        today_hrv=today_hrv,
        hrv_baseline=_HRV_BASELINE,
        today_rhr=today_rhr,
        rhr_baseline=_RHR_BASELINE,
        sleep_score=sleep_score,
        yesterday_strain=strain_21,
        acr=None,
        hrv_history=hrv_history if len(hrv_history) >= 7 else None,
        recovery_adjustment=0.0,
    )
    r = RecoveryCalculator.calculate(inp)
    score = r["score"]
    recommendation = RecoveryCalculator.training_recommendation(
        recovery=score,
        last_3day_strain_avg=strain_21 * 0.9,
        sleep_debt_hours=0.0,
    )
    return RecoveryResponse(
        score=round(score, 1),
        status=_recovery_status(score),
        hrv_component=round(r["hrv_component"], 1),
        rhr_component=round(r["rhr_component"], 1),
        sleep_component=round(r["sleep_component"], 1),
        strain_component=round(r["strain_component"], 1),
        acr_penalty=round(r["acr_penalty"], 1),
        today_hrv=today_hrv,
        today_rhr=today_rhr,
        hrv_baseline=_HRV_BASELINE,
        rhr_baseline=_RHR_BASELINE,
        training_recommendation=recommendation,
        is_mock=False,
    )


# ──────────────────────────────────────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "message": "Soma Fitness API is running"}


@app.get("/api/dashboard", response_model=DashboardResponse)
async def dashboard(request: Request):
    """
    Returns all three scores in one call.
    Mock mode if no Google token is present; real mode otherwise.
    """
    token = await _get_token(request)
    if not token:
        return get_mock_dashboard()

    client = GoogleHealthClient(token)
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Compute in dependency order: strain(yesterday) → sleep → recovery
    yest_strain = await _compute_real_strain(client, yesterday)
    sleep   = await _compute_real_sleep(client, today, yest_strain.score_21)
    strain  = await _compute_real_strain(client, today)
    recovery = await _compute_real_recovery(client, today, sleep.score, yest_strain.score_21)

    return DashboardResponse(
        recovery=recovery,
        sleep=sleep,
        strain=strain,
        date=today.strftime("%Y-%m-%d"),
        is_mock=False,
    )


@app.get("/api/recovery", response_model=RecoveryResponse)
async def recovery_endpoint(request: Request):
    token = await _get_token(request)
    if not token:
        mock = get_mock_dashboard()
        return mock.recovery

    client = GoogleHealthClient(token)
    today = date.today()
    yesterday = today - timedelta(days=1)
    yest_strain = await _compute_real_strain(client, yesterday)
    mock_sleep_score = (await _compute_real_sleep(client, today, yest_strain.score_21)).score
    return await _compute_real_recovery(client, today, mock_sleep_score, yest_strain.score_21)


@app.get("/api/sleep", response_model=SleepResponse)
async def sleep_endpoint(request: Request):
    token = await _get_token(request)
    if not token:
        mock = get_mock_dashboard()
        return mock.sleep

    client = GoogleHealthClient(token)
    today = date.today()
    yesterday = today - timedelta(days=1)
    yest_strain = await _compute_real_strain(client, yesterday)
    return await _compute_real_sleep(client, today, yest_strain.score_21)


@app.get("/api/strain", response_model=StrainResponse)
async def strain_endpoint(request: Request):
    token = await _get_token(request)
    if not token:
        mock = get_mock_dashboard()
        return mock.strain

    client = GoogleHealthClient(token)
    return await _compute_real_strain(client, date.today())
