'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepAnalytics, SleepAnalyticsDay } from '@/lib/types';
import Chart, { clockMinutes, duration } from './SleepAnalyticsChart';
import { ChartLegend, sleepMetrics } from './SleepAnalyticsCards';
import styles from './SleepAnalytics.module.css';

function weeklyBuckets(days: SleepAnalyticsDay[]): SleepAnalyticsDay[] {
  const buckets = [];
  for (let end = days.length; end > 0; end -= 7) {
    const values = days.slice(Math.max(0, end - 7), end);
    const result: SleepAnalyticsDay = { date: values.at(-1)!.date, bucket_start: values[0].date, status: 'aggregate' };
    for (const key of ['performance', 'hours_percentage', 'asleep_minutes', 'need_minutes', 'restorative', 'consistency', 'period_minutes', 'efficiency', 'deep_minutes', 'rem_minutes'] as const) {
      const readings = values.map(d => d[key]).filter((v): v is number => v != null);
      result[key] = readings.length ? readings.reduce((a, b) => a + b, 0) / readings.length : null;
    }
    for (const key of ['bed_time', 'wake_time'] as const) {
      const readings = values.map(d => clockMinutes(d[key])).filter((v): v is number => v != null).map(v => key === 'bed_time' && v < 720 ? v + 1440 : v);
      if (readings.length) {
        const average = Math.round(readings.reduce((a, b) => a + b, 0) / readings.length) % 1440;
        result[key] = `${result.date}T${String(Math.floor(average / 60)).padStart(2, '0')}:${String(average % 60).padStart(2, '0')}:00`;
      }
    }
    buckets.unshift(result);
  }
  return buckets;
}

export default function SleepAnalyticsDetail({ slug }: { slug: string }) {
  const item = sleepMetrics.find(m => m.slug === slug)!;
  const router = useRouter();
  const [range, setRange] = useState<'W' | 'M' | '6M'>('W');
  const [data, setData] = useState<SleepAnalytics | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setData(null); setError(false);
    api.getSleepAnalytics(range).then(value => { if (active) setData(value); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [range]);
  const average = data?.averages[item.metric];
  const previous = data?.previous_averages[item.metric];
  const delta = average != null && previous != null ? average - previous : null;
  const period = range === 'W' ? 'week' : range === 'M' ? 'month' : 'six months';
  const display = (value: number | null | undefined) => value == null ? '—' : item.unit === 'hr' ? duration(value) : value.toFixed(1);
  const dates = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('en', { month: 'short', day: 'numeric' });
  const chartDays = data ? range === '6M' ? weeklyBuckets(data.days) : data.days : [];
  const recorded = data?.days.filter(day => day[item.metric] != null).length ?? 0;
  return <div className={styles.detail}><div className={styles.detailInner}>
    <header className={styles.detailHeader}><Link href="/sleep" aria-label="Back to sleep"><svg width="10" height="18" viewBox="0 0 10 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M8 2 2 9l6 7" /></svg></Link><span>TREND VIEW</span><span style={{ width: 28 }} /></header>
    <div className={styles.selector}><svg width="23" height="25" viewBox="0 0 24 26" fill="none" stroke="#A2ABB2" strokeWidth="1.5" aria-hidden="true" style={{ flexShrink: 0 }}><circle cx="12" cy="15" r="8" /><path d="M9 2h6M12 2v5m7 1 2-2M12 15l4-4" /></svg><select aria-label="Sleep metric" value={slug} onChange={event => router.push(`/sleep/${event.target.value}`)}>
      {sleepMetrics.map(metric => <option value={metric.slug} key={metric.slug}>{metric.title}</option>)}
      <option value="efficiency">SLEEP EFFICIENCY</option><option value="stress">SLEEP STRESS</option>
    </select></div>
    <section className={styles.stats}><div><div className={styles.eyebrow}>AVERAGE</div><div className={styles.average}>{display(average)}<small>{item.unit}</small></div></div>
      <div className={styles.tabs}>{(['W', 'M', '6M'] as const).map(value => <button key={value} aria-pressed={range === value} onClick={() => setRange(value)}>{value}</button>)}</div></section>
    <div className={styles.period}><span className={styles.change} style={delta != null && delta < 0 ? { color: '#F59E0B', background: '#F59E0B15' } : undefined} title={item.unit === '%' ? 'Absolute difference in percentage points.' : 'Difference in average duration.'}>
      {delta == null ? '—' : `${delta >= 0 ? '+' : '−'}${item.unit === 'hr' ? duration(Math.abs(delta)) : Math.abs(delta).toFixed(1)}`} vs. prior {period}</span>
      <span>{data ? `${dates(data.range_start)} – ${dates(data.range_end)}, ${data.range_end.slice(2, 4)}` : 'Loading…'}</span></div>
    {error ? <p role="alert">Sleep analytics unavailable. Try again later.</p> : !data ? <p className={styles.description}>Loading sleep history…</p> : <>
      <p className={styles.description}>{item.metric === 'period_minutes' ? 'Your recorded sleep period runs from the start to the end of the Fitbit sleep session. It includes recorded awake time.'
        : item.metric === 'restorative' ? 'Restorative sleep combines device-estimated deep and REM sleep. Stage estimates describe patterns and are not a diagnosis.'
        : item.kind === 'hours' || item.metric === 'hours_percentage' ? 'Hours asleep compared with the app’s sleep-need estimate. Missing estimates are left blank.' : 'Your app-calculated sleep performance across recorded main sleeps.'}</p>
      <ChartLegend kind={item.kind} /><Chart days={chartDays} kind={item.kind} metric={item.metric} />
      <p className={styles.note}>{recorded} of {data.days.length} days · {range === '6M' ? 'Weekly averages' : 'Daily readings'} · Missing readings are gaps.</p>
      <p className={styles.note}>{item.metric === 'period_minutes' ? data.notes.period : item.metric === 'restorative' ? 'Deep + REM durations; naps excluded.' : data.notes.need}</p>
      {data.is_mock && <div className={styles.demo}>DEMO · SYNTHETIC HISTORY</div>}
    </>}
  </div></div>;
}
