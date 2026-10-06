"""
mock_data.py
============
Realistic mock fitness data returned when no Google Health API token exists.
All values mirror what the real API would return, so the frontend renders
identically — only the is_mock flag changes when a real device connects.
"""

from __future__ import annotations

import sys
import os
import math
import random
from dataclasses import asdict
from datetime import datetime, timedelta, date

# Allow importing the algo files from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strain import StrainCalculator, WorkoutInterval, HeartRateZone
from recovery import RecoveryCalculator, RecoveryInput
from sleepscore import SleepCalculator, SleepData
from sleep_consistency import SleepConsistencyCalculator, SleepNight
from sleep_trends import build_consistency_scores, build_sleep_trend, range_start
from health_trends import build_health_response

from models import (
    StrainResponse, RecoveryResponse, SleepResponse,
    DashboardResponse, ZoneMinutes, WorkoutDetail, SleepStages,
    SleepTrendResponse, HealthResponse
)



# ──────────────────────────────────────────────────────────────────────────────
# Mock raw data (what the Google Health API would return)
# ──────────────────────────────────────────────────────────────────────────────

def _build_mock_hr_samples() -> list[tuple[datetime, float]]:
    """
    Generates a realistic intraday HR timeline for a sample training day.
    Morning rest → workout (run) → afternoon walk → evening rest.
    """
    now = datetime(2026, 9, 28, 7, 0, 0)
    samples: list[tuple[datetime, float]] = []

    # 7:00 – 8:15: Morning resting (65–72 bpm)
    for m in range(75):
        samples.append((now + timedelta(minutes=m), 65.0 + (m % 7)))

    # 8:30 – 9:15: Outdoor run — Zone 3/4/5
    workout_start = now + timedelta(hours=1, minutes=30)
    for m in range(20):   # Zone 3 (143 bpm)
        samples.append((workout_start + timedelta(minutes=m), 143.0))
    for m in range(20, 38):  # Zone 4 (158 bpm)
        samples.append((workout_start + timedelta(minutes=m), 158.0))
    for m in range(38, 45):  # Zone 5 (172 bpm)
        samples.append((workout_start + timedelta(minutes=m), 172.0))
    workout_end = workout_start + timedelta(minutes=45)

    # 11:00 – 11:30: Afternoon walk — Zone 2 (118 bpm)
    walk_start = now + timedelta(hours=4)
    for m in range(30):
        samples.append((walk_start + timedelta(minutes=m), 118.0))

    return samples, workout_start, workout_end


def _build_mock_sleep_data() -> SleepData:
    """Use the same latest sample night as the sleep trend endpoints."""
    night = _build_sample_sleep_records(date.today(), date.today())[0]
    total_s = round(night["time_asleep_minutes"] * 60)
    in_bed_s = round(night["time_in_bed_minutes"] * 60)
    deep_s = round(total_s * 0.17)
    rem_s = round(total_s * 0.22)
    core_s = total_s - deep_s - rem_s
    awake_s = in_bed_s - total_s

    return SleepData(
        total_duration=total_s,
        deep_sleep_duration=deep_s,
        rem_sleep_duration=rem_s,
        core_sleep_duration=core_s,
        awake_duration=awake_s,
        in_bed_duration=in_bed_s,
        sleep_start_time=night["bed_time"],
        sleep_end_time=night["wake_time"],
        interruption_count=3,
        nap_duration_seconds=0.0,
        sleep_latency_seconds=12 * 60,  # 12 minutes
    )


# ──────────────────────────────────────────────────────────────────────────────
# Algo computation from mock data
# ──────────────────────────────────────────────────────────────────────────────

USER_AGE = 22
MAX_HR   = StrainCalculator.estimated_max_hr(USER_AGE)  # 192.6

# HRV history (last 14 days, oldest → newest)
HRV_HISTORY = [38.0, 41.0, 36.5, 40.2, 43.1, 39.8, 42.5, 44.0, 37.9, 41.3, 40.8, 43.6, 42.1, 44.8]
RHR_BASELINE = 56.0  # bpm
HRV_BASELINE = 41.2  # ms

# 14-day strain load history for capacity
STRAIN_LOAD_HISTORY = [310.0, 340.0, 295.0, 360.0, 320.0, 345.0, 330.0, 315.0, 355.0, 325.0, 340.0, 350.0, 320.0, 335.0]


def compute_mock_strain() -> StrainResponse:
    samples, workout_start, workout_end = _build_mock_hr_samples()
    intervals = [WorkoutInterval(start=workout_start, end=workout_end, activity_name="Outdoor Run")]

    result = StrainCalculator.calculate_workout_aware(intervals, samples, MAX_HR)
    capacity = StrainCalculator.capacity(STRAIN_LOAD_HISTORY)
    calibrating = StrainCalculator.is_calibrating(STRAIN_LOAD_HISTORY)
    score_100 = StrainCalculator.score(result.total, capacity)
    score_21 = StrainCalculator.score_to_whoop_scale(score_100)

    # Aggregate zone minutes across all samples
    _, all_zone_mins = StrainCalculator.calculate(samples, MAX_HR)

    # Build workouts list
    workouts = []
    for detail in result.details:
        zm = ZoneMinutes(
            zone1=detail.zone_minutes.get(HeartRateZone.ZONE1, 0.0),
            zone2=detail.zone_minutes.get(HeartRateZone.ZONE2, 0.0),
            zone3=detail.zone_minutes.get(HeartRateZone.ZONE3, 0.0),
            zone4=detail.zone_minutes.get(HeartRateZone.ZONE4, 0.0),
            zone5=detail.zone_minutes.get(HeartRateZone.ZONE5, 0.0),
        )
        workouts.append(WorkoutDetail(
            activity_name=detail.activity_name,
            strain=detail.strain,
            zone_minutes=zm,
        ))

    total_zone_mins = ZoneMinutes(
        zone1=all_zone_mins.get(HeartRateZone.ZONE1, 0.0),
        zone2=all_zone_mins.get(HeartRateZone.ZONE2, 0.0),
        zone3=all_zone_mins.get(HeartRateZone.ZONE3, 0.0),
        zone4=all_zone_mins.get(HeartRateZone.ZONE4, 0.0),
        zone5=all_zone_mins.get(HeartRateZone.ZONE5, 0.0),
    )

    # Compute avg HR from samples
    hr_values = [hr for _, hr in samples]
    avg_hr = sum(hr_values) / len(hr_values) if hr_values else None

    return StrainResponse(
        score_21=round(score_21, 1),
        score_100=round(score_100, 1),
        workout_strain=round(result.workout_strain, 1),
        incidental_strain=round(result.incidental_strain, 1),
        zone_minutes=total_zone_mins,
        workouts=workouts,
        max_hr=round(MAX_HR, 1),
        avg_hr=round(avg_hr, 1) if avg_hr else None,
        is_calibrating=calibrating,
        is_mock=True,
    )


def compute_mock_sleep() -> SleepResponse:
    sleep = _build_mock_sleep_data()
    from mock_sleep_stage_ranges import mock_stage_points
    from sleep_analytics import sleep_observations, demo_sleep_need_inputs
    today = date.today()
    nights = sleep_observations(mock_stage_points(today, 9), today, is_mock=True)
    inputs = demo_sleep_need_inputs(nights, today, compute_mock_strain().score_100)
    need = inputs.for_tonight(today - timedelta(days=1))
    sleep_need = need.total_need_min / 60

    sleeping_hrv = 47.2   # ms (above baseline — good)
    sleeping_hr  = 58.0   # bpm
    waking_hr    = 72.0   # bpm
    sleeping_hr_baseline = 60.5

    score = SleepCalculator.calculate_score(
        sleep=sleep,
        sleep_need=sleep_need,
        sleeping_hrv=sleeping_hrv,
        sleeping_hr=sleeping_hr,
        waking_hr=waking_hr,
        hrv_baseline=HRV_BASELINE,
        sleeping_hr_baseline=sleeping_hr_baseline,
        age=USER_AGE,
    )

    # Compute sub-scores for frontend display
    total_h = sleep.total_duration / 3600.0
    ratio = total_h / sleep_need
    if ratio <= 1.0:
        x = 8.0 * (ratio - 0.75)
        dur_score = 100.0 / (1.0 + math.exp(-x))
    elif ratio <= 1.10:
        dur_score = 100.0
    else:
        dur_score = max(30.0, 100.0 - (ratio - 1.10) * 75.0)

    efficiency = sleep.total_duration / sleep.in_bed_duration * 100
    stages = SleepStages(
        deep_minutes=round(sleep.deep_sleep_duration / 60, 1),
        rem_minutes=round(sleep.rem_sleep_duration / 60, 1),
        core_minutes=round(sleep.core_sleep_duration / 60, 1),
        awake_minutes=round(sleep.awake_duration / 60, 1),
        total_minutes=round(sleep.total_duration / 60, 1),
    )

    sleep_debt = need.sleep_debt_min / 60
    restfulness = SleepCalculator.compute_restfulness_score(sleep)
    hr_dip = SleepCalculator.compute_hr_dip_score(sleeping_hr, waking_hr)

    # Stage score
    sn_s = sleep_need * 3600
    deep_tgt = SleepCalculator.optimal_deep_ratio(USER_AGE)
    d_s = min(100.0, (sleep.deep_sleep_duration / sn_s / deep_tgt) * 100)
    r_s = min(100.0, (sleep.rem_sleep_duration  / sn_s / 0.20) * 100)
    c_s = min(100.0, (sleep.core_sleep_duration / sn_s / 0.50) * 100)
    stage_score = 0.40 * d_s + 0.40 * r_s + 0.20 * c_s

    # Seven sample nights for sleep timing variability.
    today_dt = date.today()
    mock_nights = _build_sample_sleep_records(today_dt - timedelta(days=6), today_dt)
    consistency_res = SleepConsistencyCalculator.calculate([
        SleepNight(n["date"], n["bed_time"], n["wake_time"]) for n in mock_nights
    ])

    return SleepResponse(
        score=round(score, 1),
        sleep_need_hours=sleep_need,
        sleep_need=asdict(need),
        tonight_sleep_need=asdict(inputs.for_tonight(today)),
        total_sleep_hours=round(total_h, 2),
        sleep_debt_hours=sleep_debt,
        efficiency_pct=round(efficiency, 1),
        stages=stages,
        sleeping_hrv=sleeping_hrv,
        deep_sleep_hrv=49.2,
        sleeping_hr=sleeping_hr,
        consistency_minutes=consistency_res.timing_variability_minutes,
        average_bed_time=consistency_res.average_bed_time_str,
        average_wake_time=consistency_res.average_wake_time_str,
        sleep_start=sleep.sleep_start_time.strftime("%I:%M %p") if sleep.sleep_start_time else None,
        sleep_end=sleep.sleep_end_time.strftime("%I:%M %p") if sleep.sleep_end_time else None,
        duration_score=round(dur_score, 1),
        stage_score=round(stage_score, 1),
        restfulness_score=round(restfulness, 1),
        hr_dip_score=round(hr_dip, 1),
        is_mock=True,
    )


def compute_mock_recovery(sleep_score: float, strain_21: float) -> RecoveryResponse:
    today_hrv = 44.8   # ms — slightly above baseline (good day)
    today_rhr = 53.0   # bpm — below baseline (recovered)

    inp = RecoveryInput(
        today_hrv=today_hrv,
        hrv_baseline=HRV_BASELINE,
        today_rhr=today_rhr,
        rhr_baseline=RHR_BASELINE,
        sleep_score=sleep_score,
        yesterday_strain=strain_21,
        acr=None,
        hrv_history=HRV_HISTORY,
        recovery_adjustment=0.0,
    )
    r = RecoveryCalculator.calculate(inp)
    score = r["score"]

    if score >= 67:
        status = "green"
    elif score >= 34:
        status = "yellow"
    else:
        status = "red"

    recommendation = RecoveryCalculator.training_recommendation(
        recovery=score,
        last_3day_strain_avg=strain_21 * 0.9,
        sleep_debt_hours=0.3,
    )

    return RecoveryResponse(
        score=round(score, 1),
        status=status,
        hrv_component=round(r["hrv_component"], 1),
        rhr_component=round(r["rhr_component"], 1),
        sleep_component=round(r["sleep_component"], 1),
        strain_component=round(r["strain_component"], 1),
        acr_penalty=round(r["acr_penalty"], 1),
        today_hrv=today_hrv,
        today_rhr=today_rhr,
        hrv_baseline=HRV_BASELINE,
        rhr_baseline=RHR_BASELINE,
        training_recommendation=recommendation,
        is_mock=True,
    )


def get_mock_dashboard() -> DashboardResponse:
    """
    Computes all three scores using real algorithm code against mock data.
    This is what the frontend sees until the user connects their Fitbit.
    """
    strain  = compute_mock_strain()
    sleep   = compute_mock_sleep()
    recovery = compute_mock_recovery(sleep_score=sleep.score, strain_21=strain.score_21)

    return DashboardResponse(
        recovery=recovery,
        sleep=sleep,
        strain=strain,
        date=datetime.now().strftime("%Y-%m-%d"),
        is_mock=True,
    )


def _build_sample_sleep_records(start: date, end: date) -> list[dict]:
    """Date-seeded sample nights with routine, weekend shifts, and occasional gaps."""
    records = []
    current = start
    while current <= end:
        rng = random.Random(current.toordinal() + 9173)
        if current != end and rng.random() < 0.025:
            current += timedelta(days=1)
            continue
        weekend = current.weekday() in (5, 6)
        bed_shift = rng.gauss(0, 16) + (rng.uniform(30, 70) if weekend else 0)
        if rng.random() < 0.18:
            bed_shift += rng.choice((-1, 1)) * rng.uniform(45, 95)
        bedtime = datetime.combine(current - timedelta(days=1), datetime.min.time()).replace(hour=23, minute=12)
        bedtime += timedelta(minutes=round(bed_shift))
        period_minutes = max(390, min(600, round(rng.gauss(495, 28) + (10 if weekend else 0))))
        wake_time = bedtime + timedelta(minutes=period_minutes)
        period = (wake_time - bedtime).total_seconds() / 60
        target_eff = round(max(77.0, min(96.0, rng.gauss(88.0, 5.0))), 1)
        asleep = round(period * (target_eff / 100.0), 1)
        records.append({
            "date": current,
            "bed_time": bedtime,
            "wake_time": wake_time,
            "time_asleep_minutes": asleep,
            "time_in_bed_minutes": period,
        })
        current += timedelta(days=1)
    return records


def get_mock_sleep_consistency_trend(timeframe: str = "W") -> SleepTrendResponse:
    today = date.today()
    start = range_start(today, timeframe)
    records = _build_sample_sleep_records(start - timedelta(days=6), today)
    return build_sleep_trend(records, start, today, timeframe, "consistency", True)


def get_mock_sleep_consistency_score(timeframe: str, today: date):
    start = range_start(today, timeframe)
    previous_start = range_start(start - timedelta(days=1), timeframe)
    records = _build_sample_sleep_records(previous_start - timedelta(days=4), today)
    return build_consistency_scores(records, today, timeframe, True)


def get_mock_sleep_efficiency_trend(timeframe: str = "W") -> SleepTrendResponse:
    today = date.today()
    start = range_start(today, timeframe)
    records = _build_sample_sleep_records(start, today)
    return build_sleep_trend(records, start, today, timeframe, "efficiency", True)


def get_mock_health(timeframe: str = "W") -> HealthResponse:
    """Illustrative daily vitals, including occasional unmeasured dates."""
    today = date.today()
    start = range_start(today, timeframe)
    history: dict[str, list[dict]] = {key: [] for key in (
        "hrv", "deep_sleep_hrv", "nrem_hr", "rhr", "spo2",
        "respiratory_rate", "skin_temperature", "vo2_max",
    )}
    values = {
        "hrv": (44.8, 4.0), "deep_sleep_hrv": (49.2, 5.0),
        "nrem_hr": (57.0, 2.0), "rhr": (53.0, 2.0),
        "spo2": (97.2, 0.4), "respiratory_rate": (14.1, 0.4),
        "skin_temperature": (32.6, 0.3), "vo2_max": (44.5, 0.5),
    }
    day = range_start(start - timedelta(days=1), timeframe) - timedelta(days=14)
    while day <= today:
        age = (today - day).days
        if age == 0 or age % 29 != 0:
            for key, (base, amplitude) in values.items():
                if key == "vo2_max" and age % 5:
                    continue
                history[key].append({
                    "date": day.isoformat(),
                    "value": round(base + amplitude * math.sin(age * 0.83), 1),
                    "estimated": True if key == "vo2_max" else None,
                    "method": "WITH_SLEEP" if key == "rhr" else None,
                })
        day += timedelta(days=1)
    samples, _, _ = _build_mock_hr_samples()
    samples = [(timestamp.replace(year=today.year, month=today.month, day=today.day), value)
               for timestamp, value in samples]
    return build_health_response(history, samples, start, today, timeframe, True)
