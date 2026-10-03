"""
models.py
=========
Pydantic request/response models for all API endpoints.
Shared between main.py, google_health_client.py, and mock_data.py.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


# ──────────────────────────────────────────────────────────────────────────────
# Auth / Connection
# ──────────────────────────────────────────────────────────────────────────────

class AuthStatus(BaseModel):
    connected: bool
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    is_mock: bool = True  # True when no real device is connected


# ──────────────────────────────────────────────────────────────────────────────
# Strain
# ──────────────────────────────────────────────────────────────────────────────

class ZoneMinutes(BaseModel):
    zone1: float = Field(0.0, description="Minutes in Zone 1 (50-60% MaxHR)")
    zone2: float = Field(0.0, description="Minutes in Zone 2 (60-70% MaxHR)")
    zone3: float = Field(0.0, description="Minutes in Zone 3 (70-80% MaxHR)")
    zone4: float = Field(0.0, description="Minutes in Zone 4 (80-90% MaxHR)")
    zone5: float = Field(0.0, description="Minutes in Zone 5 (90-100% MaxHR)")


class WorkoutDetail(BaseModel):
    activity_name: str
    strain: float = Field(description="Strain load units for this workout")
    zone_minutes: ZoneMinutes


class StrainResponse(BaseModel):
    score_21: float = Field(description="Strain score on WHOOP 0–21 scale")
    score_100: float = Field(description="Strain score on 0–100 scale")
    workout_strain: float
    incidental_strain: float
    zone_minutes: ZoneMinutes
    workouts: List[WorkoutDetail] = []
    max_hr: float
    avg_hr: Optional[float] = None
    age_used: Optional[int] = None
    age_is_default: bool = False
    is_calibrating: bool = False
    is_mock: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Recovery
# ──────────────────────────────────────────────────────────────────────────────

class RecoveryResponse(BaseModel):
    score: Optional[float] = Field(description="Demo-only recovery score 0–100; absent for connected data")
    status: str = Field(description="'green' | 'yellow' | 'red' (demo) | 'signals' | 'calibrating' (connected)")
    hrv_component: Optional[float] = None
    rhr_component: Optional[float] = None
    sleep_component: Optional[float] = None
    strain_component: Optional[float] = None
    acr_penalty: Optional[float] = None
    today_hrv: Optional[float] = None       # ms
    today_rhr: Optional[float] = None       # bpm
    hrv_baseline: Optional[float] = None    # ms
    rhr_baseline: Optional[float] = None    # bpm
    hrv_reference_count: int = 0
    rhr_reference_count: int = 0
    rhr_method: Optional[str] = None
    sleep_hours: Optional[float] = None
    sleep_efficiency_pct: Optional[float] = None
    training_recommendation: str
    is_calibrating: bool = False
    is_mock: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Sleep
# ──────────────────────────────────────────────────────────────────────────────

class SleepStages(BaseModel):
    deep_minutes: float
    rem_minutes: float
    core_minutes: float
    awake_minutes: float
    total_minutes: float


class SleepResponse(BaseModel):
    score: float = Field(description="Sleep score 0–100")
    sleep_need_hours: float
    total_sleep_hours: float
    sleep_debt_hours: float
    efficiency_pct: Optional[float]
    stages: SleepStages
    sleeping_hrv: Optional[float] = None
    deep_sleep_hrv: Optional[float] = None
    sleeping_hr: Optional[float] = None
    consistency_minutes: Optional[float] = None
    average_bed_time: Optional[str] = None
    average_wake_time: Optional[str] = None
    sleep_start: Optional[str] = None
    sleep_end: Optional[str] = None
    duration_score: float
    stage_score: float
    restfulness_score: float
    hr_dip_score: float
    is_mock: bool = True


class SleepTrendDay(BaseModel):
    date: str
    value: Optional[float] = None
    bed_time: Optional[str] = None
    wake_time: Optional[str] = None
    asleep_hours: Optional[float] = None
    in_bed_hours: Optional[float] = None
    bed_variability_minutes: Optional[float] = None
    wake_variability_minutes: Optional[float] = None


class SleepTrendResponse(BaseModel):
    is_mock: bool
    timeframe: str
    range_start: str
    range_end: str
    average_value: Optional[float] = None
    recorded_nights: int
    scored_days: int
    days: List[SleepTrendDay]


class SleepConsistencyScorePoint(BaseModel):
    start_date: str
    end_date: str
    score: Optional[float] = None
    label: Optional[str] = None
    scored_days: int = 0
    drift_minutes: Optional[float] = Field(default=None, description="Weighted mean of available onset/wake drifts; weekly daily points only")


class SleepConsistencyScoreResponse(BaseModel):
    is_mock: bool
    timeframe: str
    range_start: str
    range_end: str
    latest_sleep_date: Optional[str] = None
    latest_score: Optional[float] = None
    latest_label: Optional[str] = None
    latest_drift_minutes: Optional[float] = Field(default=None, description="Weighted mean drift, not the inverse of the nonlinear score")
    average_score: Optional[float] = None
    average_label: Optional[str] = None
    scored_days: int
    total_days: int
    previous_average_score: Optional[float] = None
    change_percentage_points: Optional[float] = None
    band_counts: Dict[str, int] = Field(default_factory=dict)
    y_axis_min: int = 0
    y_axis_max: int = 100
    guide_lines: List[int] = Field(default_factory=lambda: [90, 75, 50])
    points: List[SleepConsistencyScorePoint]


class SleepStressNightResponse(BaseModel):
    sleep_id: str
    night_date: str
    main_sleep: bool
    computed_at: str
    algo_version: str
    stressed_minutes: Optional[float] = None
    stressed_hours: Optional[float] = None
    stress_pct: Optional[float] = None
    valid_minutes: float
    asleep_minutes: float
    coverage: float
    confidence: str
    status: str
    nights_available: int
    baseline: dict
    peak_level: Optional[float] = None
    mean_level: Optional[float] = None
    hrv_only_minutes: Optional[float] = None
    episodes: list[dict]
    type_fallback: bool
    config_snapshot: dict


class SleepStressHistoryResponse(BaseModel):
    is_mock: bool
    range_start: str
    range_end: str
    nights: List[SleepStressNightResponse]
    totals: List[dict]




# ──────────────────────────────────────────────────────────────────────────────
# Dashboard (all three in one call)
# ──────────────────────────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    recovery: RecoveryResponse
    sleep: SleepResponse
    strain: StrainResponse
    date: str
    is_mock: bool = True


class HealthPoint(BaseModel):
    date: str
    value: Optional[float] = None
    baseline: Optional[float] = None
    estimated: Optional[bool] = None
    method: Optional[str] = None


class HeartRatePoint(BaseModel):
    time: str
    value: float


class HealthResponse(BaseModel):
    date: str
    timeframe: str
    range_start: str
    range_end: str
    is_mock: bool
    metrics: dict[str, List[HealthPoint]]
    heart_rate: List[HeartRatePoint]
