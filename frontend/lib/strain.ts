import type { StrainDay, StrainMetric, StrainRange, ZoneMinutes } from './types';

export const STRAIN_BLUE = '#0099E6';
export const strainMetrics: { key: StrainMetric; slug: string; title: string }[] = [
  { key: 'strain', slug: 'day-strain', title: 'DAY STRAIN' },
  { key: 'zones_1_3', slug: 'heart-rate-zones-1-3', title: 'HEART RATE ZONES 1-3' },
  { key: 'zones_4_5', slug: 'heart-rate-zones-4-5', title: 'HEART RATE ZONES 4-5' },
  { key: 'strength', slug: 'strength-activity-time', title: 'STRENGTH ACTIVITY TIME' },
  { key: 'steps', slug: 'steps', title: 'STEPS' },
];
export const zoneColors = ['#B1C8D2', '#439FC3', '#56BB9E', '#FFAE5B', '#FF661D'];
export const zoneKeys: (keyof ZoneMinutes)[] = ['zone1', 'zone2', 'zone3', 'zone4', 'zone5'];
export function durationMetric(metric: StrainMetric) { return metric !== 'strain' && metric !== 'steps'; }
export function strainValue(day: StrainDay, metric: StrainMetric): number | null {
  if (metric === 'strain') return day.score;
  if (metric === 'steps') return day.steps;
  if (metric === 'strength') return day.strength_minutes;
  if (day.zones == null) return null;
  return (metric === 'zones_1_3' ? zoneKeys.slice(0, 3) : zoneKeys.slice(3)).reduce((total, key) => total + day.zones![key], 0);
}
export function strainFormat(value: number | null, metric: StrainMetric) {
  if (value == null) return '—';
  if (metric === 'strain') return value.toFixed(1);
  if (metric === 'steps') return Math.round(value).toLocaleString('en-US');
  const minutes = Math.round(value);
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}
export interface StrainBucket { start: string; end: string; value: number | null; zones: ZoneMinutes | null; days: number }
export function weekBuckets(days: StrainDay[], metric: StrainMetric): StrainBucket[] {
  const buckets: StrainBucket[] = [];
  for (let i = 0; i < days.length; i += 7) {
    const group = days.slice(i, i + 7), values = group.map(day => strainValue(day, metric));
    const complete = values.every(value => value != null);
    const zones = group.every(day => day.zones != null) ? Object.fromEntries(zoneKeys.map(key => [key, group.reduce((sum, day) => sum + day.zones![key], 0)])) as unknown as ZoneMinutes : null;
    buckets.push({ start: group[0].date, end: group.at(-1)!.date,
      value: complete ? values.reduce<number>((sum, value) => sum + value!, 0) : null, zones, days: group.length });
  }
  return buckets;
}
export function strainSummary(days: StrainDay[], metric: StrainMetric, range: StrainRange, today: string): number | null {
  const filtered = metric === 'strain' ? days.filter(day => day.date !== today) : days;
  if (durationMetric(metric)) {
    const weeks = weekBuckets(filtered, metric).filter(bucket => range === 'W' || bucket.days === 7).map(bucket => bucket.value);
    const valid = weeks.filter((value): value is number => value != null);
    if (range === 'W') return weeks.length && valid.length === weeks.length ? valid.reduce((a, b) => a + b, 0) : null;
    return valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : null;
  }
  const values = filtered.map(day => strainValue(day, metric)).filter((value): value is number => value != null);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}
export function strainMonths(days: StrainDay[], metric: StrainMetric): StrainBucket[] {
  const weeks = durationMetric(metric) ? weekBuckets(days, metric).filter(bucket => bucket.days === 7) : days.map(day => ({ start: day.date, end: day.date, value: strainValue(day, metric), zones: day.zones, days: 1 }));
  const groups = new Map<string, StrainBucket[]>();
  weeks.forEach(bucket => { const key = bucket.end.slice(0, 7); groups.set(key, [...(groups.get(key) ?? []), bucket]); });
  return [...groups.values()].map(group => {
    const valid = group.map(bucket => bucket.value).filter((value): value is number => value != null);
    return { start: group[0].start, end: group.at(-1)!.end, value: valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : null, zones: null, days: group.reduce((sum, bucket) => sum + bucket.days, 0) };
  });
}
export function strainBreakdown(days: StrainDay[]) {
  const counts = [0, 0, 0, 0];
  days.forEach(day => { if (day.score != null) counts[day.score >= 18 ? 0 : day.score >= 14 ? 1 : day.score >= 10 ? 2 : 3]++; });
  return counts;
}
