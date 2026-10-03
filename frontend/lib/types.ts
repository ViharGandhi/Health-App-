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
  age_used: number | null;
  age_is_default: boolean;
  is_calibrating: boolean;
  is_mock: boolean;
}

export interface RecoveryData {
  score: number | null;
  status: 'green' | 'yellow' | 'red' | 'signals' | 'calibrating';
  hrv_component: number | null;
  rhr_component: number | null;
  sleep_component: number | null;
  strain_component: number | null;
  acr_penalty: number | null;
  today_hrv: number | null;
  today_rhr: number | null;
  hrv_baseline: number | null;
  rhr_baseline: number | null;
  hrv_reference_count: number;
  rhr_reference_count: number;
  rhr_method: string | null;
  sleep_hours: number | null;
  sleep_efficiency_pct: number | null;
  training_recommendation: string;
  is_calibrating: boolean;
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
  efficiency_pct: number | null;
  stages: SleepStages;
  sleeping_hrv: number | null;
  deep_sleep_hrv: number | null;
  sleeping_hr: number | null;
  consistency_minutes: number | null;
  average_bed_time?: string | null;
  average_wake_time?: string | null;
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

export interface SleepTrendDay {
  date: string;
  value: number | null;
  bed_time: string | null;
  wake_time: string | null;
  asleep_hours: number | null;
  in_bed_hours: number | null;
  bed_variability_minutes: number | null;
  wake_variability_minutes: number | null;
}

export interface SleepTrend {
  is_mock: boolean;
  timeframe: 'W' | '6M' | '1Y';
  range_start: string;
  range_end: string;
  average_value: number | null;
  recorded_nights: number;
  scored_days: number;
  days: SleepTrendDay[];
}

export interface SleepConsistencyScorePoint {
  start_date: string;
  end_date: string;
  score: number | null;
  label: string | null;
  scored_days: number;
  drift_minutes: number | null;
}

export interface SleepConsistencyScore {
  is_mock: boolean;
  timeframe: 'W' | 'M' | 'Y';
  range_start: string;
  range_end: string;
  latest_sleep_date: string | null;
  latest_score: number | null;
  latest_label: string | null;
  latest_drift_minutes: number | null;
  average_score: number | null;
  average_label: string | null;
  scored_days: number;
  total_days: number;
  previous_average_score: number | null;
  change_percentage_points: number | null;
  band_counts: Record<'Optimal' | 'Good' | 'Fair' | 'Poor', number>;
  y_axis_min: number;
  y_axis_max: number;
  guide_lines: number[];
  points: SleepConsistencyScorePoint[];
}

export interface SleepStressNight {
  sleep_id: string;
  night_date: string;
  main_sleep: boolean;
  stressed_minutes: number | null;
  stress_pct: number | null;
  valid_minutes: number;
  confidence: 'high' | 'medium' | 'low';
  status: string;
}

export interface SleepStressHistory {
  is_mock: boolean;
  range_start: string;
  range_end: string;
  nights: SleepStressNight[];
}

export interface SleepStageRangeMetric {
  minutes: number;
  pct: number | null;
  range: { low: number; high: number; center: number; spread: number; n: number } | null;
  range_minutes: { low: number; high: number } | null;
  status: 'below' | 'within' | 'above' | null;
  delta_vs_center_pct: number | null;
  source: 'personal' | 'population' | null;
}

export interface SleepStageRangeNight {
  sleep_id: string;
  night_date: string;
  status: string;
  total_minutes?: number;
  nights_used?: number;
  nights_available?: number;
  config_snapshot?: { min_nights: number };
  stages: Partial<Record<'awake' | 'light' | 'deep' | 'rem' | 'restorative', SleepStageRangeMetric>>;
}

export interface SleepStageRangeHistory {
  is_mock: boolean;
  nights: SleepStageRangeNight[];
}

export interface SleepHeartRate {
  is_mock: boolean;
  status: 'ok' | 'no_sleep' | 'no_readings';
  sleep_id?: string;
  night_date?: string;
  start?: string;
  end?: string;
  start_local?: string;
  end_local?: string;
  samples: { timestamp: string; local_time: string; bpm: number }[];
}

export interface HealthPoint {
  date: string;
  value: number | null;
  baseline: number | null;
  estimated: boolean | null;
  method: string | null;
}

export interface HeartRatePoint {
  time: string;
  value: number;
}

export interface HealthData {
  date: string;
  timeframe: 'W' | '6M' | '1Y';
  range_start: string;
  range_end: string;
  is_mock: boolean;
  metrics: Record<string, HealthPoint[]>;
  heart_rate: HeartRatePoint[];
}


export interface AuthStatus {
  connected: boolean;
  is_mock: boolean;
  can_connect: boolean;
  user_email: string | null;
  user_name: string | null;
}
