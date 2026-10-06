import type { RecoveryDay, RecoveryData, RecoveryMetric, RecoveryRange } from './types';

export const recoveryMetrics: { metric: RecoveryMetric; slug: string; title: string; unit: string; digits: number; kind: 'line' | 'bar' }[] = [
  { metric: 'recovery', slug: 'recovery', title: 'RECOVERY', unit: '%', digits: 0, kind: 'bar' },
  { metric: 'hrv', slug: 'hrv', title: 'HEART RATE VARIABILITY', unit: 'ms', digits: 0, kind: 'line' },
  { metric: 'rhr', slug: 'resting-heart-rate', title: 'RESTING HEART RATE', unit: 'bpm', digits: 0, kind: 'line' },
  { metric: 'respiratory_rate', slug: 'respiratory-rate', title: 'RESPIRATORY RATE', unit: 'rpm', digits: 1, kind: 'line' },
  { metric: 'sleep_performance', slug: 'sleep-performance', title: 'SLEEP PERFORMANCE', unit: '%', digits: 0, kind: 'bar' },
];
export const BLUE = '#7BA1BB';
export const LINE_BLUE = '#67AEE6';
export const AMBER = '#F5AC22';
export const TEAL = '#00DCA0';

export function recoveryColor(zone: RecoveryData['zone'], status?: string): string {
  if (zone === 'above_normal' || status === 'green') return '#16EC06';
  if (zone === 'normal' || status === 'yellow') return '#FFDE00';
  if (zone === 'below_normal' || status === 'red') return '#FF0026';
  return '#77818B';
}
export function recoveryLabel(data: RecoveryData): string {
  if (data.zone) return data.zone.replaceAll('_', ' ');
  if (data.is_calibrating) return 'Building reference';
  return data.is_mock ? 'Prototype estimate' : 'Reference unavailable';
}
export function localDay(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}
export function shiftDay(day: string, count: number): string {
  const value = new Date(`${day}T12:00:00`);
  value.setDate(value.getDate() + count);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}
export function nextPeriod(day: string, range: RecoveryRange, today = localDay()): string {
  if (range !== '6M') return [shiftDay(day, range === 'W' ? 7 : 30), today].sort()[0];
  const current = new Date(`${day}T12:00:00`);
  const target = new Date(current.getFullYear(), current.getMonth() + 7, 0, 12);
  target.setDate(Math.min(current.getDate(), target.getDate()));
  const result = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}-${String(target.getDate()).padStart(2, '0')}`;
  return [result, today].sort()[0];
}
export function dateLabel(day: string, options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }): string {
  return new Date(`${day}T12:00:00`).toLocaleDateString('en-US', options);
}
export function relativeChange(value: number | null, previous: number | null): number | null {
  return value == null || previous == null || previous === 0 ? null : (value / previous - 1) * 100;
}
export function changeColor(metric: RecoveryMetric, change: number | null): string {
  if (change == null || Math.abs(change) < .5) return '#B6BCC2';
  return (metric === 'rhr' || metric === 'respiratory_rate' ? change < 0 : change > 0) ? TEAL : AMBER;
}
export function lineSegments(days: RecoveryDay[], metric: RecoveryMetric): { index: number; value: number }[][] {
  const segments: { index: number; value: number }[][] = [];
  days.forEach((day, index) => {
    const value = day[metric];
    if (value == null) return;
    if (!index || days[index - 1][metric] == null) segments.push([]);
    segments.at(-1)!.push({ index, value });
  });
  return segments;
}
export function axisBounds(values: number[], metric: RecoveryMetric, band?: { low: number; high: number } | null): [number, number] {
  if (metric === 'recovery' || metric === 'sleep_performance') return [0, 100];
  const all = band ? [...values, band.low, band.high] : values;
  if (!all.length) return metric === 'respiratory_rate' ? [10, 20] : [30, 70];
  const low = Math.min(...all), high = Math.max(...all);
  const padding = Math.max((high - low) * .7, metric === 'respiratory_rate' ? 1.5 : 6);
  const unit = metric === 'respiratory_rate' ? .5 : 1;
  return [Math.max(0, Math.floor((low - padding) / unit) * unit), Math.ceil((high + padding) / unit) * unit];
}
