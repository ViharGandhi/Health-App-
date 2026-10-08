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
import logging
import time
import asyncio
import hashlib
import json
import inspect
from functools import wraps
from dataclasses import asdict
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from statistics import median
from typing import Optional, Literal

# Allow importing the algo files from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import httpx
from read_metrics import read_metrics
from page_snapshots import cached_page_result
from dynamic_sync import sync_dynamic
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env file (must be in the backend/ directory)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Algorithm imports ──────────────────────────────────────────────────────────
from strain import StrainConfig, strain_analytics
from strain_service import fetch_strain_inputs, calculate_days, strain_response, demo_inputs, load_strain_days
from sleepscore import SleepCalculator, SleepData
from sleep_consistency import SleepConsistencyCalculator, SleepNight
from sleep_efficiency import SleepEfficiencyCalculator

# ── App-layer imports ──────────────────────────────────────────────────────────
from auth import router as auth_router, get_session, get_valid_access_token, set_session
from google_health_client import GoogleHealthClient
from sleep_trends import build_consistency_scores, build_sleep_trend, range_start
from sleep_stress_store import SleepStressStore
from sleep_stress_pipeline import compute_connected_sleep_stress
from sleep_stress import summarize_nights
from mock_sleep_stress import mock_sleep_stress_history
from mock_sleep_stage_ranges import mock_stage_ranges, mock_stage_points
from sleep_heart_rate import select_sleep, build_sleep_heart_rate, mock_sleep_heart_rate_points
from sleep_analytics import sleep_observations, build_sleep_analytics, timing_records, demo_sleep_need_inputs
from sleep_need import SleepNeedResult, format_sleep_minutes
from sleep_need_inputs import SleepNeedInputs, need_components
from recovery_score import recovery_from_history, baseline_bounds, MIN_BASELINE_DAYS, MIN_RECENT_NIGHTS
from recovery_analytics import build_recovery_analytics, mock_recovery_history, VITALS
from sleep_stage_pipeline import sync_stage_ranges
from sleep_stage_webhooks import router as sleep_stage_webhook_router, stage_store
from health_trends import build_health_response, build_heart_rate_response
from strain_analytics import strain_range_start, strain_day, build_strain_analytics
from mock_data import (
    get_mock_dashboard, compute_mock_strain, compute_mock_sleep,
    compute_mock_recovery, get_mock_sleep_consistency_trend, get_mock_sleep_consistency_score,
    get_mock_sleep_efficiency_trend, get_mock_health
)
from models import (
    DashboardResponse, RecoveryResponse, SleepResponse, StrainResponse,
    SleepStages, SleepTrendResponse, SleepConsistencyScoreResponse,
    SleepStressHistoryResponse, HealthResponse, HealthHeartRateResponse
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
    expose_headers=['X-Data-Cache', 'X-Data-Updated-At', 'Server-Timing', 'X-Google-Requests'],
)

# Mount auth router
app.include_router(auth_router)
app.include_router(sleep_stage_webhook_router)


@app.middleware("http")
async def data_timings(request: Request, call_next):
    metrics = {}
    context = read_metrics.set(metrics)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        if request.url.path.startswith('/api/') and not request.url.path.startswith('/api/auth/'):
            elapsed = (time.perf_counter() - started) * 1000
            response.headers['Server-Timing'] = f'api;dur={elapsed:.1f}, google;dur={metrics.get("google_ms", 0):.1f}'
            response.headers['X-Google-Requests'] = str(int(metrics.get('google_requests', 0)))
            logging.getLogger('uvicorn.error').info('Data read %s: %.0fms, google=%d, database_hits=%d, memory_hits=%d, snapshot_hits=%d',
                request.url.path, elapsed, metrics.get('google_requests', 0), metrics.get('database_hits', 0), metrics.get('memory_hits', 0), metrics.get('snapshot_hits', 0))
        return response
    finally:
        read_metrics.reset(context)


@app.exception_handler(httpx.HTTPStatusError)
async def google_status_error(request: Request, error: httpx.HTTPStatusError):
    status = error.response.status_code
    if status == 429:
        return JSONResponse({"detail": "Google Health is limiting requests. Wait a minute and retry."},
                            status_code=429, headers={"Retry-After": "60"})
    if status in (401, 403):
        return JSONResponse({"detail": "Google Health access failed. Check your connection and granted permissions."}, status_code=status)
    return JSONResponse({"detail": "Google Health could not return this data. Please retry."}, status_code=502)


@app.exception_handler(httpx.RequestError)
async def google_network_error(request: Request, error: httpx.RequestError):
    return JSONResponse({"detail": "Could not reach Google Health. Please retry."}, status_code=502)

USER_AGE = int(os.getenv("USER_AGE", "22"))

# HRV baseline — replace with rolling DB value later
_HRV_BASELINE: float = 41.2
_RHR_BASELINE: float = 56.0


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_token(request: Request, response: Response) -> Optional[str]:
    """Returns a valid access token from the session, or None if not connected."""
    if hasattr(request.state, 'valid_health_token'):
        return request.state.valid_health_token
    session = get_session(request)
    if not session:
        return None
    old_token = session.get("access_token")
    token = await get_valid_access_token(session)
    if token and token != old_token:
        set_session(response, session)
    if token:
        request.state.valid_health_token = token
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

STRAIN_CONFIG = StrainConfig.from_env(os.environ)


def _google_client(token: str, request: Request):
    session = get_session(request) or {}
    identity = session.get("health_user_id") or session.get("user_email")
    client = GoogleHealthClient(token, cache=True, account_id=identity) if identity else GoogleHealthClient(token, cache=True)
    try:
        client.strain_timezone = ZoneInfo(request.headers.get("x-user-timezone", "UTC"))
    except ZoneInfoNotFoundError:
        raise HTTPException(400, "Invalid X-User-Timezone")
    sex = request.headers.get("x-user-sex") or os.getenv("USER_SEX")
    if sex is not None and sex.lower() not in ("m", "f"):
        raise HTTPException(400, "X-User-Sex must be m or f")
    client.strain_sex, client.strain_sex_defaulted = (sex or "m").lower(), sex is None
    if getattr(client, 'store', None) is not None:
        client.stored_only = True
    return client


def _cached_data_page(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        request, response = kwargs.get('request'), kwargs.get('response')
        if request is None or response is None:
            return await function(*args, **kwargs)
        session = get_session(request) or {}
        if not (session.get('health_user_id') or session.get('user_email')):
            return await function(*args, **kwargs)
        token = await _get_token(request, response)
        if not token:
            return await function(*args, **kwargs)
        client = _google_client(token, request)
        day, age = _client_day(request), _client_age(request)
        dynamic = await asyncio.to_thread(client.store.dynamic_status, client.account_key)
        daily_sleep = request.url.path.startswith(('/api/sleep', '/api/recovery'))
        parameters = inspect.signature(function).bind(*args, **kwargs)
        parameters.apply_defaults()
        effective = {k: v for k, v in parameters.arguments.items() if k not in ('request', 'response')}
        strain_revision = dynamic.get('revision', 0) if request.url.path.startswith('/api/strain') or request.url.path == '/api/dashboard' else 0
        key = hashlib.sha256(json.dumps(['page-v7', request.url.path, sorted(effective.items()) if daily_sleep else sorted(request.query_params.multi_items()),
            str(day), age, str(client.strain_timezone), client.strain_sex, client.strain_sex_defaulted,
            repr(STRAIN_CONFIG), strain_revision, dynamic.get('sleep_revision', 0)], default=str).encode()).hexdigest()
        frozen = daily_sleep and await asyncio.to_thread(client.store.sleep_day_prepared, client.account_key, day)
        return await cached_page_result(client, key, request.url.path, response, lambda: function(*args, **kwargs),
                                        frozen=frozen, prepare=getattr(request.state, 'prepare_sleep', False))
    return wrapped


def _demo_dashboard(request: Request, day: date | None = None):
    client = _google_client('demo', request)
    return get_mock_dashboard(day or _client_day(request), _client_age(request),
                              client.strain_timezone, client.strain_sex, STRAIN_CONFIG)


@app.get("/api/data/status")
async def data_status(request: Request, response: Response):
    token = await _get_token(request, response)
    if not token:
        raise HTTPException(401, "Connect Google Health to view sync status")
    client = _google_client(token, request)
    if not client.store:
        return {"last_synced_at": None, "stored_ranges": 0}
    return await asyncio.to_thread(client.store.status, client.account_key)


@app.post("/api/data/refresh")
async def refresh_data(request: Request, response: Response):
    """Expire recent reads; the next page read fetches corrections from Google."""
    token = await _get_token(request, response)
    if not token:
        raise HTTPException(401, "Connect Google Health to refresh data")
    client = _google_client(token, request)
    if client.store:
        await asyncio.to_thread(client.store.expire_recent, client.account_key)
    from google_health_client import _point_cache
    from strain_service import _daily_cache
    for cache in (_point_cache, _daily_cache):
        for key in list(cache):
            if key[0] == client.account_key:
                cache.pop(key, None)
    return {"refresh_requested": True}


@app.post('/api/data/sync')
async def sync_data(request: Request, response: Response, session: str, force: bool = False, home_visit: bool = False):
    if not 1 <= len(session) <= 128:
        raise HTTPException(400, 'Invalid app session')
    token = await _get_token(request, response)
    if not token:
        raise HTTPException(401, 'Connect Google Health to sync activities')
    client = _google_client(token, request)
    if client.store is None:
        raise HTTPException(401, 'Reconnect Google Health to establish your account identity')
    return await sync_dynamic(client, session, force, age=_client_age(request), config=STRAIN_CONFIG,
                              prepare_sleep=lambda: _prepare_sleep_pages(request), home_visit=home_visit)


async def _compute_real_strain(client: GoogleHealthClient, target_date: date, age: Optional[int] = None,
                               *, samples=None, sessions=None) -> StrainResponse:
    start = target_date - timedelta(days=27)
    if samples is None:
        values, _ = await load_strain_days(client, start, target_date, datetime.now(timezone.utc), age, STRAIN_CONFIG)
    else:
        values = calculate_days(start, target_date, datetime.now(timezone.utc), getattr(client, "strain_timezone", timezone.utc),
                            age, getattr(client, "strain_sex", "m"), getattr(client, "strain_sex_defaulted", True),
                            (samples, sessions or [], [], {}), STRAIN_CONFIG)
    return strain_response(values[target_date], values, "connected", age, config=STRAIN_CONFIG)


async def _load_sleep_need_inputs(client: GoogleHealthClient, today: date, age: Optional[int] = None, *, include_today: bool = True) -> SleepNeedInputs:
    first = today - timedelta(days=8)
    end = today if include_today else today - timedelta(days=1)
    sleep, naps, calculated = await asyncio.gather(client.get_sleep_need_history(today - timedelta(days=7), end),
        client.get_nap_minutes_history(today - timedelta(days=1), end),
        load_strain_days(client, first, end, datetime.now(timezone.utc), age, STRAIN_CONFIG))
    values, _ = calculated
    # Sleep's existing percent adapter converts this directly back to 0–21.
    # No personal-capacity normalization; its logistic formula/caps are unchanged.
    strain = {day: value["strain"] / 21 * 100 if value["strain"] is not None and value["coverage"] > 0 else None
              for day, value in values.items()}
    return SleepNeedInputs(sleep, strain, naps)


async def _compute_real_sleep(client: GoogleHealthClient, target_date: date, need: SleepNeedResult | None, age: Optional[int] = None) -> SleepResponse:
    raw = await client.get_sleep_session(target_date)
    if not raw or not raw['sleep_duration_available']:
        # Missing, pending or impossible summary durations cannot establish a score.
        return SleepResponse(
            score=None, sleep_need_hours=need.total_need_min / 60 if need else None, total_sleep_hours=0.0,
            sleep_need=asdict(need) if need else None,
            sleep_debt_hours=need.sleep_debt_min / 60 if need else None, efficiency_pct=None,
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

    sleep_need = need.total_need_min / 60 if need else None
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
    ) if sleep_need is not None else None

    total_h = sleep.total_duration / 3600.0
    dur_score = SleepCalculator.compute_duration_score(
        total_h + sleep.nap_duration_seconds / 3600, sleep_need) if sleep_need is not None else None

    efficiency = SleepEfficiencyCalculator.calculate_single_night(sleep.total_duration, sleep.in_bed_duration)
    stages = SleepStages(
        deep_minutes=round(sleep.deep_sleep_duration / 60, 1),
        rem_minutes=round(sleep.rem_sleep_duration / 60, 1),
        core_minutes=round(sleep.core_sleep_duration / 60, 1),
        awake_minutes=round(sleep.awake_duration / 60, 1),
        total_minutes=round(sleep.total_duration / 60, 1),
    )
    sleep_debt = need.sleep_debt_min / 60 if need else None
    restfulness = SleepCalculator.compute_restfulness_score(sleep)
    hr_dip = SleepCalculator.compute_hr_dip_score(sleeping_hr, waking_hr)
    sn_s = sleep_need * 3600 if sleep_need is not None else 0
    deep_tgt = SleepCalculator.optimal_deep_ratio(age if age is not None else USER_AGE)
    d_s = min(100.0, (sleep.deep_sleep_duration / sn_s / deep_tgt) * 100) if sn_s > 0 else 0
    r_s = min(100.0, (sleep.rem_sleep_duration  / sn_s / 0.20) * 100) if sn_s > 0 else 0
    c_s = min(100.0, (sleep.core_sleep_duration / sn_s / 0.50) * 100) if sn_s > 0 else 0
    stage_score = 0.40 * d_s + 0.40 * r_s + 0.20 * c_s if need else None
    # Seven consecutive nights are required for timing variability.
    history_nights = await client.get_sleep_history_nights(days=7, end_date=target_date)
    parsed_nights = [
        SleepNight(night_date=n["date"], bed_time=n["bed_time"], wake_time=n["wake_time"])
        for n in history_nights
    ]
    consistency_res = SleepConsistencyCalculator.calculate(parsed_nights)
    deep_sleep_hrv = await client.get_deep_sleep_hrv(target_date)

    return SleepResponse(
        score=round(score, 1) if score is not None else None,
        sleep_need_hours=sleep_need,
        sleep_need=asdict(need) if need else None,
        total_sleep_hours=round(total_h, 2),
        sleep_debt_hours=sleep_debt,
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
        duration_score=round(dur_score, 1) if dur_score is not None else None,
        stage_score=round(stage_score, 1) if stage_score is not None else None,
        restfulness_score=round(restfulness, 1),
        hr_dip_score=round(hr_dip, 1),
        is_mock=False,
    )


async def _compute_real_recovery(
    client: GoogleHealthClient,
    target_date: date,
    sleep_hours: Optional[float] = None,
    sleep_efficiency_pct: Optional[float] = None,
    *, history: Optional[dict] = None,
) -> RecoveryResponse:
    if history is None:
        history = await client.get_health_history(target_date - timedelta(days=14), target_date, ("hrv", "rhr"))
    comparison_start = (target_date - timedelta(days=14)).isoformat()
    today_key = target_date.isoformat()
    today_hrv_point = next((point for point in history["hrv"] if point["date"] == today_key), None)
    today_rhr_point = next((point for point in history["rhr"] if point["date"] == today_key), None)
    today_hrv = today_hrv_point["value"] if today_hrv_point else None
    today_rhr = today_rhr_point["value"] if today_rhr_point else None
    rhr_method = today_rhr_point.get("method") if today_rhr_point else None
    hrv_history = [point["value"] for point in history["hrv"] if comparison_start <= point["date"] < today_key and point["value"] > 0 and math.isfinite(point["value"])]
    rhr_history = [point["value"] for point in history["rhr"] if comparison_start <= point["date"] < today_key and point["value"] > 0 and math.isfinite(point["value"]) and point.get("method") == rhr_method]
    calibrating = (
        today_hrv is None or today_hrv <= 0 or today_rhr is None or today_rhr <= 0
        or len(hrv_history) < 7 or len(rhr_history) < 7
    )
    return RecoveryResponse(
        score=None, status="calibrating" if calibrating else "signals",
        today_hrv=today_hrv if today_hrv is not None and today_hrv > 0 and math.isfinite(today_hrv) else None,
        today_rhr=today_rhr if today_rhr is not None and today_rhr > 0 and math.isfinite(today_rhr) else None,
        hrv_baseline=round(median(hrv_history), 1) if len(hrv_history) >= 7 else None,
        rhr_baseline=round(median(rhr_history), 1) if len(rhr_history) >= 7 else None,
        hrv_reference_count=len(hrv_history), rhr_reference_count=len(rhr_history),
        rhr_method=rhr_method,
        sleep_hours=sleep_hours, sleep_efficiency_pct=sleep_efficiency_pct,
        training_recommendation="",
        is_calibrating=calibrating,
        is_mock=False,
    )


async def _recovery_sleep_need(client: GoogleHealthClient, today: date, age: Optional[int]) -> SleepNeedResult | None:
    """Share Sleep's fetched history, using only inputs before last night's sleep."""
    inputs = await _load_sleep_need_inputs(client, today, age, include_today=False)
    return inputs.for_tonight(today - timedelta(days=1))


async def _compute_connected_recovery(client: GoogleHealthClient, today: date,
                                      age: Optional[int] = None) -> RecoveryResponse:
    start, _ = baseline_bounds(today)
    history, sleep, need = await asyncio.gather(
        client.get_health_history(start, today, ("hrv", "rhr", "respiratory_rate", "skin_temperature")),
        client.get_sleep_session(today),
        _recovery_sleep_need(client, today, age),
    )
    return await _recovery_response(client, today, history, sleep, need)


async def _recovery_response(client, today: date, history: dict, sleep: dict | None,
                             need: SleepNeedResult | None) -> RecoveryResponse:
    sleep_min = (sleep["total_duration"] / 60
                 if sleep and sleep.get("sleep_duration_available") else None)
    estimate = recovery_from_history(history, today, sleep_min, need.total_need_min if need else None)
    sleep_hours = round(sleep_min / 60, 2) if sleep_min is not None else None
    efficiency = (SleepEfficiencyCalculator.calculate_single_night(sleep["total_duration"], sleep["in_bed_duration"])
                  if sleep_min is not None else None)
    # Retain the existing 14-day descriptive comparisons, separate from the
    # excluded-recent 60-day scoring reference; reuse the same fetched records.
    response = await _compute_real_recovery(client, today, sleep_hours, efficiency, history=history)
    reason = (f"Building reference: {estimate.baseline_days}/{MIN_BASELINE_DAYS} baseline HRV days; "
              f"{estimate.recent_nights}/{MIN_RECENT_NIGHTS} recent nights required."
              if estimate.status == "building_reference" else
              "Estimated baseline-relative recovery; above normal means higher than usual, not necessarily better.")
    if estimate.confidence == "low":
        reason += " Low confidence: zone only; percentage withheld."
    return response.model_copy(update={**asdict(estimate), "score": estimate.percent,
                                       "status_reason": reason,
                                       "training_recommendation": reason,
                                       "is_calibrating": estimate.status == "building_reference"})


async def _demo_recovery_analytics(end: date, timeframe: str, demo: str, request: Request | None = None) -> dict:
    previous_start = range_start(range_start(end, timeframe) - timedelta(days=1), timeframe)
    start, _ = baseline_bounds(previous_start)
    history = mock_recovery_history(start, end)
    sleep_start = min(previous_start, end - timedelta(days=30)) - timedelta(days=8)
    sleeps = sleep_observations(mock_stage_points(end, (end - sleep_start).days + 1), end, is_mock=True)
    night = next((s for s in sleeps if s["date"] == end.isoformat()), None)
    raw = ({"total_duration": (night["asleep_minutes"] or 0) * 60,
            "in_bed_duration": night["period_minutes"] * 60,
            "sleep_duration_available": night["asleep_minutes"] is not None} if night else None)
    need = demo_sleep_need_inputs(sleeps, end).for_tonight(end - timedelta(days=1))
    current = ((_demo_dashboard(request, end) if request else get_mock_dashboard(end)).recovery if demo == "legacy"
               else (await _recovery_response(None, end, history, raw, need)).model_copy(update={"is_mock": True}))
    return build_recovery_analytics(history, sleeps, end, timeframe, current.model_dump(), is_mock=True, demo_mode=demo)


# ──────────────────────────────────────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "message": "Ojas Fitness API is running"}


@app.get("/api/dashboard", response_model=DashboardResponse)
@_cached_data_page
async def dashboard(request: Request, response: Response):
    """
    Returns all three scores in one call.
    Mock mode if no Google token is present; real mode otherwise.
    """
    token = await _get_token(request, response)
    if not token:
        if get_session(request):
            raise HTTPException(401, "Reconnect Google Health to refresh dashboard data")
        return _demo_dashboard(request)

    client = _google_client(token, request)
    today = _client_day(request)
    age = _client_age(request)
    yesterday = today - timedelta(days=1)

    # Compute in dependency order: strain(yesterday) → sleep → recovery
    inputs = await _load_sleep_need_inputs(client, today, age)
    sleep   = await _compute_real_sleep(client, today, inputs.for_tonight(yesterday), age)
    tonight = inputs.for_tonight(today)
    sleep.tonight_sleep_need = asdict(tonight) if tonight else None
    strain  = await _compute_real_strain(client, today, age)
    recovery = await _compute_connected_recovery(client, today, age)

    return DashboardResponse(
        recovery=recovery,
        sleep=sleep,
        strain=strain,
        date=today.strftime("%Y-%m-%d"),
        is_mock=False,
    )


@app.get("/api/recovery", response_model=RecoveryResponse)
@_cached_data_page
async def recovery_endpoint(request: Request, response: Response, demo: Literal["legacy", "estimate"] = "legacy"):
    token = await _get_token(request, response)
    if not token:
        if get_session(request):
            raise HTTPException(401, "Reconnect Google Health to refresh recovery data")
        if demo == "estimate":
            return (await _demo_recovery_analytics(_client_day(request), "W", demo, request))["current"]
        mock = _demo_dashboard(request)
        return mock.recovery

    client = _google_client(token, request)
    today = _client_day(request)
    return await _compute_connected_recovery(client, today, _client_age(request))


@app.get("/api/recovery/analytics")
@_cached_data_page
async def recovery_analytics_endpoint(request: Request, response: Response,
                                      timeframe: Literal["W", "M", "6M"] = "W",
                                      end_date: date | None = None,
                                      demo: Literal["legacy", "estimate"] = "estimate"):
    today = _client_day(request)
    end = end_date or today
    if end > today:
        raise HTTPException(400, "Recovery history cannot end in the future")
    token = await _get_token(request, response)
    if not token:
        if get_session(request):
            raise HTTPException(401, "Reconnect Google Health to refresh recovery data")
        return await _demo_recovery_analytics(end, timeframe, demo, request)
    previous_start = range_start(range_start(end, timeframe) - timedelta(days=1), timeframe)
    start, _ = baseline_bounds(previous_start)
    client = _google_client(token, request)
    age = _client_age(request)
    sleep_start = min(previous_start, end - timedelta(days=30))
    history, records, need = await asyncio.gather(
        client.get_health_history(start, end, VITALS),
        client._sleep_records(sleep_start, end),
        _recovery_sleep_need(client, end, age),
    )
    night = next((record for record in records if record["date"] == end), None)
    current = await _recovery_response(client, end, history, night, need)
    sleeps = []
    for record in records:
        performance = None
        if record is night and need and record["sleep_duration_available"]:
            data = SleepData(record["total_duration"], record["deep_sleep_duration"], record["rem_sleep_duration"],
                             record["core_sleep_duration"], record["awake_duration"], record["in_bed_duration"],
                             record["sleep_start_time"], record["sleep_end_time"], record["interruption_count"],
                             sleep_latency_seconds=record.get("sleep_latency_seconds"))
            performance = round(SleepCalculator.calculate_score(data, need.total_need_min / 60,
                           hrv_baseline=_HRV_BASELINE, sleeping_hr_baseline=_RHR_BASELINE + 4,
                           age=age if age is not None else USER_AGE), 1)
        sleeps.append({"date": record["date"].isoformat(), "performance": performance,
                       "asleep_minutes": record["total_duration"] / 60 if record["sleep_duration_available"] else None,
                       "bed_time": record["sleep_start_time"].isoformat(), "wake_time": record["sleep_end_time"].isoformat()})
    return build_recovery_analytics(history, sleeps, end, timeframe, current.model_dump(), is_mock=False)


@app.get("/api/sleep", response_model=SleepResponse)
@_cached_data_page
async def sleep_endpoint(request: Request, response: Response):
    token = await _get_token(request, response)
    if not token:
        mock = _demo_dashboard(request)
        return mock.sleep

    client = _google_client(token, request)
    today = _client_day(request)
    age = _client_age(request)
    yesterday = today - timedelta(days=1)
    inputs = await _load_sleep_need_inputs(client, today, age)
    sleep = await _compute_real_sleep(client, today, inputs.for_tonight(yesterday), age)
    tonight = inputs.for_tonight(today)
    sleep.tonight_sleep_need = asdict(tonight) if tonight else None
    return sleep


@app.get("/api/sleep/need")
@_cached_data_page
async def sleep_need_endpoint(request: Request, response: Response):
    today = _client_day(request)
    token = await _get_token(request, response)
    if not token and get_session(request):
        raise HTTPException(401, "Reconnect Google Health to refresh sleep data")
    if token:
        inputs = await _load_sleep_need_inputs(_google_client(token, request), today, _client_age(request))
    else:
        nights = sleep_observations(mock_stage_points(today, 9), today, is_mock=True)
        inputs = demo_sleep_need_inputs(nights, today, _demo_dashboard(request).strain.score_100)
    tonight = inputs.for_tonight(today)
    last_night = inputs.for_tonight(today - timedelta(days=1))
    return {"date": today.isoformat(), "is_mock": not token,
            "status": "estimated" if tonight else "missing_strain",
            **(asdict(tonight) if tonight else {}),
            "formatted_total_need": format_sleep_minutes(tonight.total_need_min) if tonight else None,
            "last_night": asdict(last_night) if last_night else None}


@app.get("/api/sleep/analytics")
@_cached_data_page
async def sleep_analytics_endpoint(request: Request, response: Response, timeframe: Literal["W", "M", "6M"] = "W"):
    today = _client_day(request)
    start = range_start(today, timeframe)
    history_start = min(range_start(start - timedelta(days=1), timeframe) - timedelta(days=8), today - timedelta(days=34))
    session = get_session(request)
    token = await _get_token(request, response)
    if not token and session:
        raise HTTPException(401, "Reconnect Google Health to refresh sleep data")
    if not token:
        points = mock_stage_points(today, (today - history_start).days + 1)
    else:
        client = _google_client(token, request)
        points = await client.get_sleep_stage_points(history_start, today)
    nights = sleep_observations(points, today, is_mock=not token)
    inputs = (await _load_sleep_need_inputs(client, today, _client_age(request)) if token
              else demo_sleep_need_inputs(nights, today, _demo_dashboard(request).strain.score_100))
    need = inputs.for_tonight(today - timedelta(days=1))
    if token and need and nights and nights[-1]["date"] == today.isoformat() and nights[-1]["status"] == "ok":
        current = await _compute_real_sleep(client, today, need, _client_age(request))
        # Only attach the current algorithm result when its period matches this identified sleep.
        if (current.sleep_start == datetime.fromisoformat(nights[-1]["bed_time"]).strftime("%I:%M %p")
                and current.sleep_end == datetime.fromisoformat(nights[-1]["wake_time"]).strftime("%I:%M %p")
                and abs(current.stages.total_minutes - nights[-1]["asleep_minutes"]) < 1):
            nights[-1].update(performance=current.score, need_minutes=need.total_need_min,
                             need_components=need_components(need))
    result = build_sleep_analytics(nights, today, timeframe, not token)
    tonight = inputs.for_tonight(today)
    result["tonight_sleep_need"] = asdict(tonight) if tonight else None
    return result


@app.get("/api/sleep/heart-rate")
@_cached_data_page
async def sleep_heart_rate_endpoint(
    request: Request, response: Response, night_date: date | None = None, sleep_id: str | None = None,
):
    today = _client_day(request)
    end = night_date or today
    start = end if night_date else end - timedelta(days=9)
    session = get_session(request)
    token = await _get_token(request, response)
    if not token:
        if session:
            raise HTTPException(401, "Reconnect Google Health to refresh sleep data")
        points = mock_stage_points(end, (end - start).days + 1)
        # Demo nights represent completed sleeps even when viewed before their synthetic wake time.
        demo_now = datetime.fromisoformat(f"{today.isoformat()}T23:59:59+00:00")
        point = select_sleep(points, today, sleep_id, now=demo_now)
        return build_sleep_heart_rate(point, mock_sleep_heart_rate_points(point) if point else [], True)
    client = _google_client(token, request)
    try:
        point = select_sleep(await client.get_sleep_stage_points(start, end), today, sleep_id)
        if point is None:
            return build_sleep_heart_rate(None, [], False)
        interval = point["sleep"]["interval"]
        readings = await client.get_sleep_heart_rate_points(
            datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00")),
            datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00")),
        )
        return build_sleep_heart_rate(point, readings, False)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            raise HTTPException(401, "Reconnect Google Health to refresh sleep data") from error
        raise


@app.get("/api/sleep/stages/typical-ranges")
@_cached_data_page
async def sleep_stage_ranges_endpoint(request: Request, response: Response, days: int = 10):
    if not 1 <= days <= 366:
        raise HTTPException(400, "days must be between 1 and 366")
    today = _client_day(request)
    session = get_session(request)
    token = await _get_token(request, response)
    if not token:
        if session:
            raise HTTPException(401, "Reconnect Google Health to refresh sleep data")
        return {"is_mock": True, "nights": mock_stage_ranges(today, days)}
    client = _google_client(token, request)
    try:
        user_id = (session or {}).get('health_user_id') or client.account_key
        nights = await sync_stage_ranges(client, user_id, stage_store(), today - timedelta(days=days - 1), today)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            raise HTTPException(401, "Reconnect Google Health to refresh sleep data") from error
        raise
    return {"is_mock": False, "nights": nights}


@app.get("/api/sleep/stress", response_model=SleepStressHistoryResponse)
@_cached_data_page
async def sleep_stress_endpoint(
    request: Request, response: Response, days: int = 7,
    timeframe: Literal["W", "M", "6M"] | None = None,
):
    if not 1 <= days <= 31:
        raise HTTPException(status_code=400, detail="days must be between 1 and 31")
    today = _client_day(request)
    start = range_start(today, timeframe) if timeframe else today - timedelta(days=days - 1)
    requested_days = (today - start).days + 1
    had_session = get_session(request) is not None
    token = await _get_token(request, response)
    if not token:
        if had_session:
            raise HTTPException(status_code=401, detail="Reconnect Google Health to refresh sleep data")
        nights = mock_sleep_stress_history(today, requested_days)
        return {"is_mock": True, "range_start": start.isoformat(),
                "range_end": today.isoformat(),
                "nights": nights, "totals": summarize_nights(nights)}
    anchor = os.getenv("SLEEP_STRESS_HRV_ANCHOR")
    if anchor not in ("start", "end"):
        anchor = None
    store = SleepStressStore(os.getenv("SLEEP_STRESS_DB_PATH", os.path.join(
        os.path.dirname(__file__), "data", "sleep_stress.sqlite3")))
    try:
        nights = await compute_connected_sleep_stress(_google_client(token, request), start, today, anchor, store)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Reconnect Google Health to refresh sleep data") from error
        raise
    return {"is_mock": False, "range_start": start.isoformat(),
            "range_end": today.isoformat(), "nights": nights,
            "totals": summarize_nights(nights)}


@app.get("/api/strain/analytics")
@_cached_data_page
async def strain_analytics_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M"] = "W",
    metric: Literal["strain", "zones_1_3", "zones_4_5", "strength", "steps"] = "strain",
    end_date: Optional[date] = None, demo: bool = False,
):
    today = _client_day(request)
    end = end_date or today
    if end > today:
        raise HTTPException(400, "Cannot request a future Strain period.")
    start = strain_range_start(end, timeframe, metric)
    lower = min(strain_range_start(start - timedelta(days=1), timeframe, metric), end - timedelta(days=30))
    token = None if demo else await _get_token(request, response)
    if not token and not demo and get_session(request):
        raise HTTPException(401, "Reconnect Google Health to refresh Strain data.")
    client = _google_client(token or "demo", request)
    age, is_mock = _client_age(request), not token
    if is_mock:
        # Explicit synthetic profile, distinct from missing connected age.
        age = age if age is not None else 30
        inputs, steps = demo_inputs(lower, end, client.strain_timezone)
        now = datetime.combine(end, datetime.min.time(), tzinfo=client.strain_timezone) + timedelta(hours=22)
    else:
        now = datetime.now(timezone.utc)
        calculated, steps = await asyncio.gather(load_strain_days(client, lower, end, now, age, STRAIN_CONFIG), client.get_daily_steps(lower, end))
        values, sessions = calculated
    if is_mock:
        values = calculate_days(lower, end, now, client.strain_timezone, age, client.strain_sex,
                            False if is_mock else client.strain_sex_defaulted, inputs, STRAIN_CONFIG, client.account_key if token else None)
    recovery = 72 if is_mock else (await _compute_connected_recovery(client, end, age)).score
    current = strain_response(values[end], values, "demo" if is_mock else "connected", age, recovery, STRAIN_CONFIG)
    if is_mock:
        _, sessions, _, _ = inputs
    history = [strain_day(day, [], sessions, strain_response(value, values, current.mode, age, config=STRAIN_CONFIG), steps.get(day))
               for day, value in values.items()]
    return build_strain_analytics(history, current, start, end, timeframe, metric, is_mock, today)


@app.get("/api/strain", response_model=StrainResponse)
@_cached_data_page
async def strain_endpoint(request: Request, response: Response, date: Optional[date] = None, demo: bool = False):
    target = date or _client_day(request)
    if target > _client_day(request):
        raise HTTPException(400, "Cannot request a future Strain day.")
    token = None if demo else await _get_token(request, response)
    if not token and not demo and get_session(request):
        raise HTTPException(401, "Reconnect Google Health to refresh Strain data.")
    client = _google_client(token or "demo", request)
    age = _client_age(request)
    if not token:
        age = 30 if age is None else age
        start = target - timedelta(days=27)
        inputs, _ = demo_inputs(start, target, client.strain_timezone)
        now = datetime.combine(target, datetime.min.time(), tzinfo=client.strain_timezone) + timedelta(hours=22)
        values = calculate_days(start, target, now, client.strain_timezone, age, client.strain_sex, False, inputs, STRAIN_CONFIG)
        return strain_response(values[target], values, "demo", age, 72, STRAIN_CONFIG)
    current, recovery = await asyncio.gather(_compute_real_strain(client, target, age), _compute_connected_recovery(client, target, age))
    band = strain_analytics([], target, current.strain, recovery.score, STRAIN_CONFIG)["strain_target"]
    return current.model_copy(update={"analytics": {**current.analytics, "strain_target": band}})


@app.get("/api/health/heart-rate", response_model=HealthHeartRateResponse)
async def health_heart_rate_endpoint(request: Request, response: Response):
    token = await _get_token(request, response)
    if not token:
        mock = get_mock_health(today=_client_day(request))
        return HealthHeartRateResponse(
            date=mock.date, is_mock=True, heart_rate=mock.heart_rate,
            latest_heart_rate=mock.latest_heart_rate,
        )
    today = _client_day(request)
    client = _google_client(token, request)
    samples = await client.get_intraday_heart_rate(today, preserve_offset=True)
    return build_heart_rate_response(samples, today, False)


@app.get("/api/health", response_model=HealthResponse)
@_cached_data_page
async def health_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "1Y"] = "W"
):
    token = await _get_token(request, response)
    if not token:
        return get_mock_health(timeframe, _client_day(request))
    today = _client_day(request)
    start = range_start(today, timeframe)
    client = _google_client(token, request)
    previous_start = range_start(start - timedelta(days=1), timeframe)
    history = await client.get_health_history(previous_start - timedelta(days=14), today)
    return build_health_response(history, [], start, today, timeframe, False)


@app.get("/api/sleep/consistency", response_model=SleepTrendResponse)
@_cached_data_page
async def sleep_consistency_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "1Y"] = "W"
):
    token = await _get_token(request, response)
    if not token:
        return get_mock_sleep_consistency_trend(timeframe, _client_day(request))
    today = _client_day(request)
    start = range_start(today, timeframe)
    client = _google_client(token, request)
    history = await client.get_sleep_trend_history(start - timedelta(days=6), today)
    return build_sleep_trend(history, start, today, timeframe, "consistency", False)


@app.get("/api/sleep/consistency/score", response_model=SleepConsistencyScoreResponse)
@_cached_data_page
async def sleep_consistency_score_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "Y"] = "W"
):
    today = _client_day(request)
    token = await _get_token(request, response)
    if not token:
        start = range_start(today, timeframe)
        previous_start = range_start(start - timedelta(days=1), timeframe)
        points = mock_stage_points(today, (today - previous_start).days + 5)
        records = timing_records(sleep_observations(points, today, is_mock=True))
        return build_consistency_scores(records, today, timeframe, True)
    start = range_start(today, timeframe)
    previous_start = range_start(start - timedelta(days=1), timeframe)
    client = _google_client(token, request)
    history = await client.get_main_sleep_timing_history(previous_start - timedelta(days=4), today)
    return build_consistency_scores(history, today, timeframe, False)


@app.get("/api/sleep/efficiency", response_model=SleepTrendResponse)
@_cached_data_page
async def sleep_efficiency_endpoint(
    request: Request, response: Response, timeframe: Literal["W", "M", "6M", "1Y"] = "W"
):
    token = await _get_token(request, response)
    if not token:
        today = _client_day(request)
        start = range_start(today, timeframe)
        points = mock_stage_points(today, (today - start).days + 1)
        records = [r for r in timing_records(sleep_observations(points, today, is_mock=True)) if r["time_asleep_minutes"] is not None]
        return build_sleep_trend(records, start, today, timeframe, "efficiency", True)
    today = _client_day(request)
    start = range_start(today, timeframe)
    client = _google_client(token, request)
    history = await client.get_sleep_trend_history(start, today)
    return build_sleep_trend(history, start, today, timeframe, "efficiency", False)


async def _prepare_sleep_pages(request: Request):
    """Build the standard Sleep/Recovery views before freezing the daily results."""
    views = [
        ('/api/sleep', sleep_endpoint, {}),
        ('/api/sleep/need', sleep_need_endpoint, {}),
        ('/api/sleep/heart-rate', sleep_heart_rate_endpoint, {}),
        ('/api/sleep/stages/typical-ranges', sleep_stage_ranges_endpoint, {}),
        ('/api/recovery', recovery_endpoint, {'demo': 'estimate'}),
        ('/api/recovery', recovery_endpoint, {'demo': 'legacy'}),
        ('/api/sleep/stress', sleep_stress_endpoint, {}),
    ]
    for timeframe in ('W', 'M', '6M'):
        views.extend([
            ('/api/sleep/analytics', sleep_analytics_endpoint, {'timeframe': timeframe}),
            ('/api/sleep/stress', sleep_stress_endpoint, {'timeframe': timeframe}),
            ('/api/recovery/analytics', recovery_analytics_endpoint, {'timeframe': timeframe}),
        ])
    for timeframe in ('W', 'M', '6M', '1Y'):
        views.extend([
            ('/api/sleep/consistency', sleep_consistency_endpoint, {'timeframe': timeframe}),
            ('/api/sleep/efficiency', sleep_efficiency_endpoint, {'timeframe': timeframe}),
            ('/api/sleep/consistency/score', sleep_consistency_score_endpoint,
             {'timeframe': 'Y' if timeframe == '1Y' else timeframe}),
        ])
    token = await _get_token(request, Response())
    client = _google_client(token, request)
    today = _client_day(request)
    point = select_sleep(await client.get_sleep_stage_points(today, today), today)
    if point:
        views.append(('/api/sleep/heart-rate', sleep_heart_rate_endpoint,
                      {'night_date': today, 'sleep_id': point['name']}))
    for path, function, parameters in views:
        scope = {**request.scope, 'path': path, 'raw_path': path.encode(), 'query_string': b'',
                 'state': {**request.scope.get('state', {}), 'prepare_sleep': True}}
        await function(request=Request(scope), response=Response(), **parameters)
