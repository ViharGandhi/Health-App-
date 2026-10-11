export type StressLevel = 'low' | 'medium' | 'high';
export type StressPoint = { start: string; end: string; score: number | null; state: string; reason: 'exercise_recovery' | 'missing_hr' | 'baseline_building' | null; source: string; hr: number | null };
export type StressDay = {
  date: string; start: string; end: string; calendar_end: string; points: StressPoint[];
  overlays: { kind: 'sleep' | 'activity'; name: string; start: string; end: string }[];
  average: number | null; minutes: Record<StressLevel, number>; unscored_minutes: number;
  scored_minutes: number; elapsed_minutes: number; coverage: number;
  latest_score: number | null; latest_level: StressLevel | null; latest_at: string | null;
  stale: boolean; hrv_samples: number; awake_hrv_samples: number;
  status: 'synthetic' | 'estimated' | 'baseline_building' | 'no_hr';
  baseline_days: number; baseline_mode: string; baseline_leaks: boolean; low_confidence: boolean;
  hrv_quality_verified: boolean; hrv_quality_rejected: number; sleep_hrv_enabled: boolean; night_context_enabled: boolean;
  sleep_stress: number | null; non_activity_stress: number | null;
};
export type StressData = {
  is_mock: boolean; validated: false; timezone: string; current: StressDay; days: StressDay[];
  model: string; limitations: string; data_source: string;
};
export const stressColors = { low: '#7BA9BD', medium: '#51C49F', high: '#EDD45B', missing: '#828B93' };
export const stressLevel = (score: number): StressLevel => score < 1 ? 'low' : score < 2 ? 'medium' : 'high';
export function stressUnavailable(reason: StressPoint['reason']) {
  return reason === 'exercise_recovery' ? 'Exercise / recovery masked' : reason === 'baseline_building' ? 'Building personal baseline' : 'Missing usable HR';
}
export function stressNote(day: StressDay) {
  if (day.status === 'baseline_building') return `Building baseline · ${day.baseline_days} reference days`;
  if (day.status === 'no_hr') return 'No usable HR readings';
  return `Estimated${day.low_confidence ? ' · low confidence' : ''} · ${day.baseline_days} baseline days`;
}
export function stressTime(value: string, timezone: string) {
  const offset = /^UTC([+-])(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(timezone);
  if (offset) {
    const seconds = (Number(offset[2]) * 3600 + Number(offset[3]) * 60 + Number(offset[4] ?? 0)) * (offset[1] === '+' ? 1 : -1);
    return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' }).format(new Date(Date.parse(value) + seconds * 1000));
  }
  return new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}
export function stressDuration(minutes: number) {
  const rounded = Math.round(minutes);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}
