"""
models.py
=========
Pydantic request/response models for all API endpoints.
Shared between main.py, google_health_client.py, and mock_data.py.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
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
    is_calibrating: bool = False
    is_mock: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Recovery
# ──────────────────────────────────────────────────────────────────────────────

class RecoveryResponse(BaseModel):
    score: float = Field(description="Recovery score 0–100")
    status: str = Field(description="'green' (67-100) | 'yellow' (34-66) | 'red' (0-33)")
    hrv_component: float
    rhr_component: float
    sleep_component: float
    strain_component: float
    acr_penalty: float
    today_hrv: Optional[float] = None       # ms
    today_rhr: Optional[float] = None       # bpm
    hrv_baseline: Optional[float] = None    # ms
    rhr_baseline: Optional[float] = None    # bpm
    training_recommendation: str
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
    efficiency_pct: float
    stages: SleepStages
    sleeping_hrv: Optional[float] = None
    sleeping_hr: Optional[float] = None
    consistency_score: Optional[float] = None
    average_bed_time: Optional[str] = None
    average_wake_time: Optional[str] = None
    consistency_status: Optional[str] = None
    sleep_start: Optional[str] = None
    sleep_end: Optional[str] = None
    duration_score: float
    stage_score: float
    restfulness_score: float
    hr_dip_score: float
    is_mock: bool = True


class SleepConsistencyDay(BaseModel):
    day_name: str
    day_num: int
    date: str
    score: float
    status: str


class SleepConsistencyBreakdown(BaseModel):
    optimal_days: int
    sufficient_days: int
    poor_days: int
    total_days: int


class SleepConsistencyTrendResponse(BaseModel):
    average_score: float
    prior_week_change: float
    range_label: str
    insight: str
    days: List[SleepConsistencyDay]
    breakdown: SleepConsistencyBreakdown


class SleepEfficiencyDay(BaseModel):
    day_name: str
    day_num: int
    date: str
    score: float
    status: str
    asleep_hours: float
    in_bed_hours: float
    awake_minutes: float


class SleepEfficiencyBreakdown(BaseModel):
    optimal_days: int
    sufficient_days: int
    poor_days: int
    total_days: int


class SleepEfficiencyTrendResponse(BaseModel):
    average_score: float
    status: str
    average_time_asleep_hours: float
    average_time_in_bed_hours: float
    average_awake_minutes: float
    prior_week_change: float
    range_label: str
    insight: str
    days: List[SleepEfficiencyDay]
    breakdown: SleepEfficiencyBreakdown



# ──────────────────────────────────────────────────────────────────────────────
# Dashboard (all three in one call)
# ──────────────────────────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    recovery: RecoveryResponse
    sleep: SleepResponse
    strain: StrainResponse
    date: str
    is_mock: bool = True
