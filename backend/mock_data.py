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
from datetime import datetime, timedelta, date

# Allow importing the algo files from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strain import StrainCalculator, WorkoutInterval, HeartRateZone
from recovery import RecoveryCalculator, RecoveryInput
from sleepscore import SleepCalculator, SleepData
from sleep_consistency import SleepConsistencyCalculator, SleepNight
from sleep_efficiency import SleepEfficiencyCalculator, SleepEfficiencyNight

from models import (
    StrainResponse, RecoveryResponse, SleepResponse,
    DashboardResponse, ZoneMinutes, WorkoutDetail, SleepStages,
    SleepConsistencyDay, SleepConsistencyBreakdown, SleepConsistencyTrendResponse,
    SleepEfficiencyDay, SleepEfficiencyBreakdown, SleepEfficiencyTrendResponse
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
    """Last night's realistic sleep: 7h 22m total with good stages."""
    rem_s   = int((1 * 3600) + (38 * 60))   # 1h 38m
    deep_s  = int((1 * 3600) + (12 * 60))   # 1h 12m
    core_s  = int((4 * 3600) + (32 * 60))   # 4h 32m
    awake_s = int((47 * 60))                  # 47 min
    total_s = rem_s + deep_s + core_s        # 7h 22m
    in_bed_s = total_s + awake_s + (10 * 60) # in bed ~8h 19m

    sleep_start = datetime(2026, 9, 27, 23, 12, 0)
    sleep_end   = datetime(2026, 9, 28, 7, 31, 0)

    return SleepData(
        total_duration=total_s,
        deep_sleep_duration=deep_s,
        rem_sleep_duration=rem_s,
        core_sleep_duration=core_s,
        awake_duration=awake_s,
        in_bed_duration=in_bed_s,
        sleep_start_time=sleep_start,
        sleep_end_time=sleep_end,
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

    # Mock yesterday's strain (0-21 scale)
    yesterday_strain_21 = 12.8

    sleep_need = SleepCalculator.calculate_sleep_need(
        baseline_sleep=7.5,
        yesterday_strain=yesterday_strain_21,
    )

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

    sleep_debt = SleepCalculator.compute_sleep_debt([(sleep_need, total_h)])
    restfulness = SleepCalculator.compute_restfulness_score(sleep)
    hr_dip = SleepCalculator.compute_hr_dip_score(sleeping_hr, waking_hr)

    # Stage score
    sn_s = sleep_need * 3600
    deep_tgt = SleepCalculator.optimal_deep_ratio(USER_AGE)
    d_s = min(100.0, (sleep.deep_sleep_duration / sn_s / deep_tgt) * 100)
    r_s = min(100.0, (sleep.rem_sleep_duration  / sn_s / 0.20) * 100)
    c_s = min(100.0, (sleep.core_sleep_duration / sn_s / 0.50) * 100)
    stage_score = 0.40 * d_s + 0.40 * r_s + 0.20 * c_s

    # 4-Day Sleep Consistency calculation
    today_dt = date.today()
    mock_4day_nights = [
        SleepNight(
            night_date=today_dt - timedelta(days=3),
            bed_time=datetime.combine(today_dt - timedelta(days=4), datetime.min.time()).replace(hour=23, minute=15),
            wake_time=datetime.combine(today_dt - timedelta(days=3), datetime.min.time()).replace(hour=7, minute=18),
        ),
        SleepNight(
            night_date=today_dt - timedelta(days=2),
            bed_time=datetime.combine(today_dt - timedelta(days=3), datetime.min.time()).replace(hour=23, minute=30),
            wake_time=datetime.combine(today_dt - timedelta(days=2), datetime.min.time()).replace(hour=7, minute=25),
        ),
        SleepNight(
            night_date=today_dt - timedelta(days=1),
            bed_time=datetime.combine(today_dt - timedelta(days=2), datetime.min.time()).replace(hour=23, minute=10),
            wake_time=datetime.combine(today_dt - timedelta(days=1), datetime.min.time()).replace(hour=7, minute=12),
        ),
        SleepNight(
            night_date=today_dt,
            bed_time=sleep.sleep_start_time if sleep.sleep_start_time else datetime.combine(today_dt - timedelta(days=1), datetime.min.time()).replace(hour=23, minute=20),
            wake_time=sleep.sleep_end_time if sleep.sleep_end_time else datetime.combine(today_dt, datetime.min.time()).replace(hour=7, minute=20),
        ),
    ]
    consistency_res = SleepConsistencyCalculator.calculate(mock_4day_nights)

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


def get_mock_sleep_consistency_trend() -> SleepConsistencyTrendResponse:
    """
    Returns 7-day sleep consistency trend data matching WHOOP trend view.
    """
    days_data = [
        SleepConsistencyDay(day_name="Thu", day_num=9, date="2026-04-09", score=85.0, status="Optimal"),
        SleepConsistencyDay(day_name="Fri", day_num=10, date="2026-04-10", score=92.0, status="Optimal"),
        SleepConsistencyDay(day_name="Sat", day_num=11, date="2026-04-11", score=86.0, status="Optimal"),
        SleepConsistencyDay(day_name="Sun", day_num=12, date="2026-04-12", score=79.0, status="Sufficient"),
        SleepConsistencyDay(day_name="Mon", day_num=13, date="2026-04-13", score=82.0, status="Optimal"),
        SleepConsistencyDay(day_name="Tue", day_num=14, date="2026-04-14", score=88.0, status="Optimal"),
        SleepConsistencyDay(day_name="Wed", day_num=15, date="2026-04-15", score=80.0, status="Optimal"),
    ]

    avg_score = round(sum(d.score for d in days_data) / len(days_data), 1)

    return SleepConsistencyTrendResponse(
        average_score=85.0,
        prior_week_change=6.0,
        range_label="APR 9 - APR 15, 26",
        insight="Your average Sleep Consistency (85%) this week was above your previous 7-day average of 80%. Keep up this trend for positive results!",
        days=days_data,
        breakdown=SleepConsistencyBreakdown(
            optimal_days=6,
            sufficient_days=1,
            poor_days=0,
            total_days=7,
        ),
    )


def get_mock_sleep_efficiency_trend() -> SleepEfficiencyTrendResponse:
    """
    Returns 7-day sleep efficiency trend data matching WHOOP trend view.
    """
    days_data = [
        SleepEfficiencyDay(day_name="Thu", day_num=9, date="2026-04-09", score=91.0, status="Optimal", asleep_hours=7.2, in_bed_hours=7.9, awake_minutes=42.0),
        SleepEfficiencyDay(day_name="Fri", day_num=10, date="2026-04-10", score=94.0, status="Optimal", asleep_hours=7.5, in_bed_hours=8.0, awake_minutes=30.0),
        SleepEfficiencyDay(day_name="Sat", day_num=11, date="2026-04-11", score=88.0, status="Sufficient", asleep_hours=7.0, in_bed_hours=7.95, awake_minutes=57.0),
        SleepEfficiencyDay(day_name="Sun", day_num=12, date="2026-04-12", score=85.0, status="Sufficient", asleep_hours=6.8, in_bed_hours=8.0, awake_minutes=72.0),
        SleepEfficiencyDay(day_name="Mon", day_num=13, date="2026-04-13", score=92.0, status="Optimal", asleep_hours=7.4, in_bed_hours=8.05, awake_minutes=39.0),
        SleepEfficiencyDay(day_name="Tue", day_num=14, date="2026-04-14", score=95.0, status="Optimal", asleep_hours=7.8, in_bed_hours=8.2, awake_minutes=24.0),
        SleepEfficiencyDay(day_name="Wed", day_num=15, date="2026-04-15", score=96.0, status="Optimal", asleep_hours=7.5, in_bed_hours=7.8, awake_minutes=18.0),
    ]

    avg_score = round(sum(d.score for d in days_data) / len(days_data), 1)

    return SleepEfficiencyTrendResponse(
        average_score=avg_score,
        status="Optimal" if avg_score >= 90.0 else ("Sufficient" if avg_score >= 80.0 else "Poor"),
        average_time_asleep_hours=7.3,
        average_time_in_bed_hours=8.0,
        average_awake_minutes=40.3,
        prior_week_change=3.0,
        range_label="APR 9 - APR 15, 26",
        insight=f"Your average Sleep Efficiency ({avg_score}%) this week was optimal. You spent an average of 40 minutes awake in bed each night.",
        days=days_data,
        breakdown=SleepEfficiencyBreakdown(
            optimal_days=5,
            sufficient_days=2,
            poor_days=0,
            total_days=7,
        ),
    )


