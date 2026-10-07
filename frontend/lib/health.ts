import type { HealthPoint } from './types';

export type HealthRange = 'W' | 'M' | '6M';
export const healthMetrics = [
  { key: 'hrv', slug: 'hrv', title: 'HEART RATE VARIABILITY', unit: 'ms', digits: 0,
    meaning: 'Daily RMSSD reflects beat-to-beat variation. Compare your own repeated readings; one value cannot establish readiness.' },
  { key: 'rhr', slug: 'resting-heart-rate', title: 'RESTING HEART RATE', unit: 'bpm', digits: 0,
    meaning: 'A daily resting estimate. Your own pattern is more informative than comparing one number with someone else’s.' },
  { key: 'respiratory_rate', slug: 'respiratory-rate', title: 'RESPIRATORY RATE', unit: 'rpm', digits: 1,
    meaning: 'Average breaths per minute during the main sleep period. Look for sustained changes alongside other context.' },
  { key: 'spo2', slug: 'oxygen-saturation', title: 'OXYGEN SATURATION', unit: '%', digits: 1,
    meaning: 'Average oxygen saturation during sleep. Wrist estimates can be affected by fit and motion; they cannot diagnose a breathing condition.' },
  { key: 'skin_temperature', slug: 'skin-temperature', title: 'NIGHTLY SKIN TEMPERATURE', unit: '°C', digits: 1,
    meaning: 'Mean skin temperature while asleep. This is not core body temperature or a fever measurement.' },
  { key: 'deep_sleep_hrv', slug: 'deep-sleep-hrv', title: 'DEEP-SLEEP HRV', unit: 'ms', digits: 0,
    meaning: 'Deep-sleep RMSSD is a separate, optional device value. It should not be interchanged with daily average RMSSD.' },
  { key: 'nrem_hr', slug: 'nrem-heart-rate', title: 'NON-REM HEART RATE', unit: 'bpm', digits: 0,
    meaning: 'Heart rate reported during non-REM sleep. It is not the same measure as all-day resting heart rate.' },
  { key: 'vo2_max', slug: 'cardio-fitness', title: 'CARDIO FITNESS ESTIMATE', unit: 'ml/kg/min', digits: 1,
    meaning: 'A device estimate of aerobic fitness, not a laboratory VO₂ max test. Estimates are not necessarily reported every day.' },
] as const;
export type HealthMetric = (typeof healthMetrics)[number];

export function monitorReading(metric: HealthMetric, point?: HealthPoint) {
  const temperature = metric.key === 'skin_temperature';
  const hasBaseline = point?.value != null && point.baseline != null;
  const temperatureChange = temperature && hasBaseline;
  const unit = temperatureChange ? '°F' : metric.unit;
  const value = point?.value == null ? null : temperatureChange
    ? (point.value - point.baseline!) * 1.8
    : point.value;
  const digits = metric.key === 'spo2' ? 0 : metric.digits;
  const formatted = value == null ? '—' : `${temperatureChange && Number(value.toFixed(digits)) > 0 ? '+' : ''}${Number(value.toFixed(digits)).toFixed(digits)}`;
  const comparison = point?.value == null ? 'No reading' : point.baseline == null ? 'Building baseline'
    : temperature ? 'vs. personal median' : `${healthChange(point.value, point.baseline, metric)!.replace('percentage points', 'pts')} vs. median`;
  return { formatted, unit, comparison, hasBaseline };
}

export function healthDate(day: string, options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }) {
  return new Date(`${day}T12:00:00`).toLocaleDateString('en-US', options);
}

export function healthChange(current: number | null, previous: number | null, metric: HealthMetric): string | null {
  if (current == null || previous == null) return null;
  const delta = current - previous;
  const magnitude = Math.abs(delta).toFixed(metric.digits);
  return `${Number(magnitude) === 0 ? '' : delta > 0 ? '+' : '−'}${magnitude} ${metric.key === 'spo2' ? 'percentage points' : metric.unit}`;
}

export function healthSegments(points: { value: number | null; baseline?: number | null }[], field: 'value' | 'baseline' = 'value') {
  const segments: { index: number; value: number }[][] = [];
  points.forEach((point, index) => {
    const value = point[field];
    if (value == null) return;
    if (!index || points[index - 1][field] == null) segments.push([]);
    segments.at(-1)!.push({ index, value });
  });
  return segments;
}

export function healthMonths(points: HealthPoint[]) {
  const groups = new Map<string, { start: number; end: number; values: number[] }>();
  points.forEach((point, index) => {
    const month = point.date.slice(0, 7);
    if (!groups.has(month)) groups.set(month, { start: index, end: index, values: [] });
    const group = groups.get(month)!;
    group.end = index;
    if (point.value != null) group.values.push(point.value);
  });
  return [...groups.entries()].map(([month, group]) => ({ month, start: group.start, end: group.end,
    value: group.values.length ? group.values.reduce((sum, value) => sum + value, 0) / group.values.length : null,
    count: group.values.length, days: group.end - group.start + 1 }));
}

export function healthBounds(values: number[], metric: string): [number, number] {
  const minimumPadding = metric === 'spo2' || metric === 'skin_temperature' ? .8 : metric === 'respiratory_rate' ? 1.5 : 6;
  const low = Math.min(...values), high = Math.max(...values);
  const padding = Math.max((high - low) * .6, minimumPadding);
  return [Math.max(0, low - padding), metric === 'spo2' ? Math.min(100, high + padding) : high + padding];
}
