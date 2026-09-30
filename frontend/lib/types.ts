/**
 * types.ts
 * TypeScript interfaces matching the FastAPI response models exactly.
 */

export interface ZoneMinutes {
  zone1: number;
  zone2: number;
  zone3: number;
  zone4: number;
  zone5: number;
}

export interface WorkoutDetail {
  activity_name: string;
  strain: number;
  zone_minutes: ZoneMinutes;
}

export interface StrainData {
  score_21: number;
  score_100: number;
  workout_strain: number;
  incidental_strain: number;
  zone_minutes: ZoneMinutes;
  workouts: WorkoutDetail[];
  max_hr: number;
  avg_hr: number | null;
  is_calibrating: boolean;
  is_mock: boolean;
}

export interface RecoveryData {
  score: number;
  status: 'green' | 'yellow' | 'red';
  hrv_component: number;
  rhr_component: number;
  sleep_component: number;
  strain_component: number;
  acr_penalty: number;
  today_hrv: number | null;
  today_rhr: number | null;
  hrv_baseline: number | null;
  rhr_baseline: number | null;
  training_recommendation: string;
  is_mock: boolean;
}

export interface SleepStages {
  deep_minutes: number;
  rem_minutes: number;
  core_minutes: number;
  awake_minutes: number;
  total_minutes: number;
}

export interface SleepData {
  score: number;
  sleep_need_hours: number;
  total_sleep_hours: number;
  sleep_debt_hours: number;
  efficiency_pct: number;
  stages: SleepStages;
  sleeping_hrv: number | null;
  sleeping_hr: number | null;
  consistency_score: number | null;
  average_bed_time?: string | null;
  average_wake_time?: string | null;
  consistency_status?: string | null;
  sleep_start: string | null;
  sleep_end: string | null;
  duration_score: number;
  stage_score: number;
  restfulness_score: number;
  hr_dip_score: number;
  is_mock: boolean;
}

export interface DashboardData {
  recovery: RecoveryData;
  sleep: SleepData;
  strain: StrainData;
  date: string;
  is_mock: boolean;
}

export interface SleepConsistencyDay {
  day_name: string;
  day_num: number;
  date: string;
  score: number;
  status: string;
}

export interface SleepConsistencyBreakdown {
  optimal_days: number;
  sufficient_days: number;
  poor_days: number;
  total_days: number;
}

export interface SleepConsistencyTrend {
  average_score: number;
  prior_week_change: number;
  range_label: string;
  insight: string;
  days: SleepConsistencyDay[];
  breakdown: SleepConsistencyBreakdown;
}

export interface SleepEfficiencyDay {
  day_name: string;
  day_num: number;
  date: string;
  score: number;
  status: string;
  asleep_hours: number;
  in_bed_hours: number;
  awake_minutes: number;
}

export interface SleepEfficiencyBreakdown {
  optimal_days: number;
  sufficient_days: number;
  poor_days: number;
  total_days: number;
}

export interface SleepEfficiencyTrend {
  average_score: number;
  status: string;
  average_time_asleep_hours: number;
  average_time_in_bed_hours: number;
  average_awake_minutes: number;
  prior_week_change: number;
  range_label: string;
  insight: string;
  days: SleepEfficiencyDay[];
  breakdown: SleepEfficiencyBreakdown;
}

export interface AuthStatus {
  connected: boolean;
  is_mock: boolean;
  user_email: string | null;
  user_name: string | null;
}

