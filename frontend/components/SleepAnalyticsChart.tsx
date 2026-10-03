'use client';

import type { SleepAnalyticsDay, SleepAnalyticsMetric } from '@/lib/types';
import styles from './SleepAnalytics.module.css';

export const duration = (minutes: number | null | undefined) => minutes == null ? '—' : `${Math.floor(Math.round(minutes) / 60)}:${String(Math.round(minutes) % 60).padStart(2, '0')}`;
export const clockMinutes = (value?: string) => value ? Number(value.slice(11, 13)) * 60 + Number(value.slice(14, 16)) : null;
const clock = (value: number) => `${String(Math.floor(value / 60) % 24).padStart(2, '0')}:${String(Math.round(value % 60)).padStart(2, '0')}`;
export type SleepChartKind = 'bars' | 'hours' | 'restorative' | 'timing';

export default function SleepAnalyticsChart({ days, kind = 'bars', metric = 'performance', guides = false, daily = false }: {
  days: SleepAnalyticsDay[]; kind?: SleepChartKind; metric?: SleepAnalyticsMetric; guides?: boolean; daily?: boolean;
}) {
  const timing = kind === 'timing';
  const percent = kind === 'bars';
  const step = 310 / Math.max(1, days.length);
  const x = (i: number) => 38 + (i + .5) * step;
  const timingValues = days.map(day => {
    const bed = clockMinutes(daily ? day.onset_time : day.bed_time);
    const wake = clockMinutes(daily ? day.sleep_wake_time : day.wake_time);
    if (bed == null || wake == null) return null;
    const left = bed < 720 ? bed + 1440 : bed;
    const right = wake + (left >= 1440 ? 1440 : 0) + (wake <= bed ? 1440 : 0);
    return { bed: left, wake: right };
  });
  const maxValue = percent ? 100 : timing ? Math.max(2220, ...timingValues.map(v => v?.wake ?? 0)) : kind === 'restorative' ? Math.max(240, ...days.map(d => d.restorative ?? 0)) : Math.max(600, ...days.flatMap(d => [d.asleep_minutes ?? 0, d.need_minutes ?? 0]));
  const minValue = timing ? Math.min(1260, ...timingValues.map(v => v?.bed ?? 1260)) : 0;
  const y = (v: number) => 26 + 184 * (timing ? (v - minValue) / (maxValue - minValue) : 1 - (v - minValue) / (maxValue - minValue));
  const guideValues = timingValues.slice(0, -1).filter(v => v != null);
  const guide = (key: 'bed' | 'wake') => guideValues.reduce((sum, v) => sum + v[key], 0) / guideValues.length;
  const grid = timing ? [1260, 1500, 1740, 1980, 2220] : percent ? [0, 25, 50, 75, 100] : [0, maxValue / 3, maxValue * 2 / 3, maxValue];
  return <svg viewBox="0 0 360 255" className={styles.chart} role="img" aria-label={`${timing ? 'Bed and wake times' : kind === 'hours' ? 'Hours asleep and needed' : kind === 'restorative' ? 'Deep and REM sleep' : metric} history`}>
    {grid.map(v => <g key={v}><line x1="38" x2="352" y1={y(v)} y2={y(v)} stroke="white" opacity=".09" />
      {(timing || percent) && <text x="30" y={y(v) + 3} textAnchor="end" fill="#92979D" fontSize="9">{timing ? clock(v) : `${Math.round(v)}%`}</text>}</g>)}
    {guides && guideValues.length > 1 && ['bed', 'wake'].map(key => <line key={key} x1="38" x2="352" y1={y(guide(key as 'bed' | 'wake'))} y2={y(guide(key as 'bed' | 'wake'))} stroke="#B5BCC3" strokeDasharray="3 3" />)}
    {days.length > 0 && <rect x={x(days.length - 1) - step * .43} y="12" width={step * .86} height="237" fill="white" opacity=".055" rx="3" />}
    {days.map((day, i) => {
      const value = day[metric];
      const time = timingValues[i];
      const width = Math.min(15, step * .42);
      const display = timing ? `${(daily ? day.onset_time : day.bed_time)?.slice(11, 16) ?? '—'}–${(daily ? day.sleep_wake_time : day.wake_time)?.slice(11, 16) ?? '—'}` : percent ? value == null ? 'No reading' : `${Math.round(value)}%` : kind === 'hours' ? `${duration(day.asleep_minutes)} asleep / ${duration(day.need_minutes)} needed` : duration(day.restorative);
      const label = `${day.bucket_start ? `${day.bucket_start} – ` : ''}${day.date}: ${display}`;
      return <g key={day.date} tabIndex={0} aria-label={label}><title>{label}</title>
        {timing && time && <><rect x={x(i) - width / 2} y={y(time.bed)} width={width} height={Math.max(1, y(time.wake) - y(time.bed))} rx="1.5" fill={daily && i < days.length - 1 ? '#73777C' : '#7BA1BB'} />
          {(days.length <= 7 || i % Math.ceil(days.length / 7) === 0) && <><text x={x(i)} y={y(time.bed) - 5} textAnchor="middle" fill="#7BA1BB" fontSize="11">{clock(time.bed)}</text><text x={x(i)} y={y(time.wake) + 13} textAnchor="middle" fill="#7BA1BB" fontSize="11">{clock(time.wake)}</text></>}</>}
        {kind === 'restorative' && day.deep_minutes != null && day.rem_minutes != null && <><rect x={x(i) - width / 2} y={y(day.rem_minutes)} width={width} height={210 - y(day.rem_minutes)} fill="#AF50EC" />
          <rect x={x(i) - width / 2} y={y(day.rem_minutes + day.deep_minutes)} width={width} height={y(day.rem_minutes) - y(day.rem_minutes + day.deep_minutes)} fill="#ED8EF5" />
          {days.length <= 7 && <text x={x(i)} y={y(day.rem_minutes + day.deep_minutes) - 6} textAnchor="middle" fill="white" fontSize="11">{duration(day.rem_minutes + day.deep_minutes)}</text>}</>}
        {percent && value != null && <><rect x={x(i) - width / 2} y={y(value)} width={width} height={210 - y(value)} rx="1.5" fill="#7BA1BB" />
          {days.length <= 7 && <text x={x(i)} y={y(value) - 6} textAnchor="middle" fill="#7BA1BB" fontSize="11">{Math.round(value)}%</text>}</>}
        {(days.length <= 7 || i % Math.ceil(days.length / 7) === 0) && <text x={x(i)} y="230" textAnchor="middle" fill="#A0A5AA" fontSize="9"><tspan>{new Date(`${day.date}T12:00:00`).toLocaleDateString('en', { weekday: 'short' })}</tspan><tspan x={x(i)} dy="12">{Number(day.date.slice(8))}</tspan></text>}
      </g>;
    })}
    {kind === 'hours' && (['asleep_minutes', 'need_minutes'] as const).map(key => {
      const color = key === 'asleep_minutes' ? '#7BA1BB' : '#00DCA0';
      return <g key={key}>{days.slice(1).map((day, i) => day[key] != null && days[i][key] != null && <line key={i} x1={x(i)} x2={x(i + 1)} y1={y(days[i][key]!)} y2={y(day[key]!)} stroke={color} strokeWidth="1.5" />)}
        {days.map((day, i) => day[key] != null && <g key={i}><title>{day.date}: {key === 'asleep_minutes' ? 'Hours asleep' : 'Sleep needed'} {duration(day[key])}</title><circle cx={x(i)} cy={y(day[key]!)} r="3.5" fill="#252B30" stroke={color} strokeWidth="1.5" />
          {days.length <= 7 && <text x={x(i)} y={y(day[key]!) + (key === 'asleep_minutes' ? 18 : -12)} textAnchor="middle" fill={color} fontSize="10">{duration(day[key])}</text>}</g>)}</g>;
    })}
  </svg>;
}
