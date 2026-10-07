import type { StrainAnalytics, StrainMetric } from '@/lib/types';
import { durationMetric, strainBreakdown, strainFormat, weekBuckets, zoneColors, zoneKeys, STRAIN_BLUE } from '@/lib/strain';
import shared from '@/app/recovery/page.module.css';
import styles from '@/app/strain/page.module.css';

export default function StrainBreakdown({ data, metric }: { data: StrainAnalytics; metric: StrainMetric }) {
  if (metric === 'steps') return null;
  const weekly = data.timeframe === 'W';
  let labels: string[], colors: string[], values: (number | null)[];
  if (metric === 'strain') {
    labels = ['All Out (18.0+)', 'High (14.0–<18.0)', 'Moderate (10.0–<14.0)', 'Light (<10.0)'];
    colors = ['#0099E6', '#0585BF', '#086C9C', '#075782']; values = strainBreakdown(data.days);
  } else if (metric === 'strength') {
    const totals = new Map<string, number>();
    const completeWeeks = Math.floor(data.days.length / 7);
    const days = weekly ? data.days : data.days.slice(0, completeWeeks * 7);
    days.forEach(day => Object.entries(day.strength_activities).forEach(([name, value]) => totals.set(name, (totals.get(name) ?? 0) + value)));
    labels = [...totals.keys()]; colors = labels.map(() => STRAIN_BLUE);
    values = [...totals.values()].map(value => weekly ? value : completeWeeks ? value / completeWeeks : null);
  } else {
    const indices = metric === 'zones_1_3' ? [0, 1, 2] : [3, 4];
    const weeks = weekBuckets(data.days, metric).filter(bucket => bucket.zones != null && (weekly || bucket.days === 7));
    labels = indices.map(i => `Zone ${i + 1}`); colors = indices.map(i => zoneColors[i]);
    values = indices.map(i => weeks.length ? weeks.reduce((sum, week) => sum + week.zones![zoneKeys[i]], 0) / (weekly ? 1 : weeks.length) : null);
  }
  const total = values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  return <section className={styles.breakdown} aria-label="Trend breakdown">
    <h2>{metric === 'strain' ? 'STRAIN BREAKDOWN (DAYS)' : `${metric === 'strength' ? 'STRENGTH ACTIVITY' : 'HR ZONES'} BREAKDOWN (${weekly ? 'WEEKLY TOTAL' : 'AVG. WEEKLY TOTAL'})`}</h2>
    <div className={styles.breakdownBar}>{total > 0 && values.map((value, index) => value == null || !value ? null : <span key={index} style={{ width: `${value / total * 100}%`, background: colors[index] }} />)}</div>
    {labels.map((label, index) => <div className={styles.breakdownRow} key={label}><i style={{ background: colors[index] }} /><strong>{durationMetric(metric) ? strainFormat(values[index], metric) : `${values[index]}x`}</strong><span>{label}</span></div>)}
    {!labels.length && <p className={shared.note}>No logged strength activities in this period.</p>}
  </section>;
}
