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
  status: 'green' | 'yellow' | 'red' | 'signals' | 'calibrating' | 'building_reference' | 'ok';
  z: number | null;
  percent: number | null;
  zone: 'below_normal' | 'normal' | 'above_normal' | null;
  confidence: 'low' | 'medium' | 'high' | null;
  estimated: boolean | null;
  components: { z_hrv: number | null; z_rhr: number | null; sleep_adj: number } | null;
  sleep_context: { sleep_min: number | null; need_min: number | null; performance: number | null } | null;
  baseline_days: number | null;
  recent_nights: number | null;
  rhr_baseline_days: number | null;
  illness_flag: boolean | null;
  status_reason: string | null;
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
  score: number | null;
  sleep_need_hours: number | null;
  total_sleep_hours: number;
  sleep_debt_hours: number | null;
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
  duration_score: number | null;
  stage_score: number | null;
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

export type RecoveryMetric = 'recovery' | 'hrv' | 'rhr' | 'respiratory_rate' | 'sleep_performance';
export type RecoveryRange = 'W' | 'M' | '6M';
export type RecoveryDemo = 'estimate' | 'legacy';
export interface RecoveryDay {
  date: string;
  recovery: number | null;
  zone: RecoveryData['zone'];
  confidence: RecoveryData['confidence'];
  sleep_context_missing: boolean;
  hrv: number | null;
  rhr: number | null;
  respiratory_rate: number | null;
  sleep_performance: number | null;
}
export interface RecoveryAnalytics {
  is_mock: boolean;
  demo_mode: RecoveryDemo | null;
  timeframe: RecoveryRange;
  range_start: string;
  range_end: string;
  previous_range_end: string;
  days: RecoveryDay[];
  averages: Record<RecoveryMetric, number | null>;
  previous_averages: Record<RecoveryMetric, number | null>;
  prior_30_day_averages: Record<Exclude<RecoveryMetric, 'recovery'>, number | null>;
  typical_ranges: Record<string, { low: number; high: number; days: number } | null>;
  monthly_buckets: { start_date: string; end_date: string; averages: Record<RecoveryMetric, number | null>; counts: Record<RecoveryMetric, number> }[];
  current: RecoveryData;
  sleep: { date: string; performance: number | null; asleep_minutes: number | null; bed_time: string; wake_time: string } | null;
  health_monitor: { within: number; assessed: number; expected: number };
  notes: string;
}

export type SleepAnalyticsMetric = 'performance' | 'hours_percentage' | 'asleep_minutes' | 'need_minutes' | 'restorative' | 'consistency' | 'period_minutes' | 'efficiency';
export interface SleepAnalyticsDay {
  date: string;
  bucket_start?: string;
  status: string;
  sleep_id?: string;
  bed_time?: string;
  wake_time?: string;
  onset_time?: string;
  sleep_wake_time?: string;
  period_minutes?: number | null;
  asleep_minutes?: number | null;
  awake_minutes?: number | null;
  deep_minutes?: number | null;
  rem_minutes?: number | null;
  restorative?: number | null;
  consistency?: number | null;
  efficiency?: number | null;
  performance?: number | null;
  need_minutes?: number | null;
  hours_percentage?: number | null;
  wake_events?: number | null;
  need_components?: { baseline: number; strain: number; debt: number; nap_credit: number } | null;
  segments?: { stage: SleepStage; start: string; end: string }[];
}
export interface SleepAnalytics {
  is_mock: boolean;
  timeframe: 'W' | 'M' | '6M';
  range_start: string;
  range_end: string;
  days: SleepAnalyticsDay[];
  averages: Record<SleepAnalyticsMetric, number | null>;
  previous_averages: Record<SleepAnalyticsMetric, number | null>;
  prior_30_averages: Record<SleepAnalyticsMetric, number | null>;
  notes: { period: string; need: string; timing: string };
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
  timeframe: 'W' | 'M' | '6M' | 'Y';
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

export type SleepStage = 'awake' | 'light' | 'deep' | 'rem';

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
  stage_intervals: { stage: SleepStage; start: string; end: string }[];
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

export interface LatestHeartRate {
  sample_time: string;
  value: number;
}

export interface HealthHeartRateData {
  date: string;
  is_mock: boolean;
  heart_rate: HeartRatePoint[];
  latest_heart_rate: LatestHeartRate | null;
}

export interface HealthData {
  date: string;
  timeframe: 'W' | 'M' | '6M' | '1Y';
  range_start: string;
  range_end: string;
  previous_range_start: string;
  previous_range_end: string;
  averages: Record<string, number | null>;
  previous_averages: Record<string, number | null>;
  is_mock: boolean;
  metrics: Record<string, HealthPoint[]>;
  heart_rate: HeartRatePoint[];
  latest_heart_rate: LatestHeartRate | null;
}


export interface AuthStatus {
  connected: boolean;
  is_mock: boolean;
  can_connect: boolean;
  user_email: string | null;
  user_name: string | null;
}
