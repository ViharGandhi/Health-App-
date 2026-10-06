'use client';

import Link from 'next/link';
import type { SleepAnalytics, SleepAnalyticsDay, SleepAnalyticsMetric, SleepStressNight } from '@/lib/types';
import Chart, { duration, type SleepChartKind } from './SleepAnalyticsChart';
import styles from './SleepAnalytics.module.css';

export const sleepMetrics: { slug: string; title: string; metric: SleepAnalyticsMetric; kind: SleepChartKind; unit: '%' | 'hr' }[] = [
  { slug: 'performance', title: 'SLEEP PERFORMANCE', metric: 'performance', kind: 'bars', unit: '%' },
  { slug: 'hours-needed', title: 'HOURS VS. NEEDED (HOURS)', metric: 'asleep_minutes', kind: 'hours', unit: 'hr' },
  { slug: 'hours-needed-percentage', title: 'HOURS VS. NEEDED (%)', metric: 'hours_percentage', kind: 'bars', unit: '%' },
  { slug: 'restorative', title: 'RESTORATIVE SLEEP (HOURS)', metric: 'restorative', kind: 'restorative', unit: 'hr' },
  { slug: 'consistency', title: 'SLEEP CONSISTENCY', metric: 'consistency', kind: 'bars', unit: '%' },
  { slug: 'time-in-bed', title: 'TIME IN BED', metric: 'period_minutes', kind: 'timing', unit: 'hr' },
];

export function ChartLegend({ kind }: { kind: SleepChartKind }) {
  return kind === 'hours' ? <div className={styles.legend}><span style={{ color: '#7BA1BB' }}><i />HOURS OF SLEEP</span><span style={{ color: '#00DCA0' }}><i />SLEEP NEEDED</span></div>
    : kind === 'restorative' ? <div className={styles.legend}><span><b className={styles.swatch} style={{ background: '#ED8EF5' }} />DEEP SLEEP</span><span><b className={styles.swatch} style={{ background: '#AF50EC' }} />REM SLEEP</span></div> : null;
}

function DailyScore({ value, baseline, unit = '%' }: { value: number | null | undefined; baseline: number | null; unit?: string }) {
  return <><div className={styles.score}>{value == null ? '—' : `${Math.round(value)}${unit}`}
    {value != null && baseline != null && value !== baseline && <span className={styles.delta} style={{ color: value > baseline ? '#00DCA0' : '#F59E0B' }}>{value > baseline ? '▲' : '▼'}</span>}</div>
    <div className={styles.baseline}>{baseline == null ? '—' : `${Math.round(baseline)}${unit}`}<span className={styles.note}> · prior 30 days</span></div></>;
}

function Timeline({ night, awake }: { night: SleepAnalyticsDay; awake: boolean }) {
  const start = night.bed_time ? Date.parse(night.bed_time) : NaN;
  const period = (night.period_minutes ?? 0) * 60000;
  return <div className={styles.track}>{period > 0 && night.segments?.filter(segment => (segment.stage === 'awake') === awake).map((segment, i) =>
    <span key={i} style={{ left: `${100 * (Date.parse(segment.start) - start) / period}%`, width: `${100 * (Date.parse(segment.end) - Date.parse(segment.start)) / period}%`, background: awake ? '#D2D3D6' : '#7BA1BB', borderRight: '1px solid #303840' }} />)}</div>;
}

export default function SleepAnalyticsCards({ analytics, stress, stressError }: { analytics: SleepAnalytics; stress?: SleepStressNight; stressError?: string }) {
  const night = analytics.days.filter(day => day.sleep_id).at(-1);
  if (!night) return <p className={styles.note}>No completed main sleep recorded.</p>;
  const need = night.need_minutes;
  const max = Math.max(night.asleep_minutes ?? 0, need ?? 0, 1);
  const components = night.need_components;
  const grossNeed = components ? components.baseline + components.strain + components.debt : 0;
  const limitAdjustment = components && need != null ? need - (grossNeed - components.nap_credit) : 0;
  const high = stress?.status === 'ok' ? stress.stressed_minutes : null;
  const other = high != null ? Math.max(0, stress!.valid_minutes - high) : null;
  return <div className={styles.stack}>
    {analytics.is_mock && <div className={styles.demo}>DEMO · SYNTHETIC SLEEP HISTORY</div>}
    <Link href="/sleep/hours-needed" className={`${styles.card} ${styles.cardLink}`}>
      <div className={styles.heading}>HOURS VS. NEEDED<span className={styles.info} title={analytics.notes.need}>i</span></div>
      <DailyScore value={night.hours_percentage} baseline={analytics.prior_30_averages.hours_percentage} />
      <div className={styles.row}><span>HOURS OF SLEEP</span><strong>{duration(night.asleep_minutes)}</strong></div>
      <div className={styles.track}><span style={{ width: `${100 * (night.asleep_minutes ?? 0) / max}%` }} /></div>
      <div className={styles.needTrack} style={{ width: `${100 * (need ?? 0) / max}%` }}>{components && (['baseline', 'strain', 'debt'] as const).map((key, i) => <span key={key} style={{ width: `${100 * components[key] / Math.max(grossNeed, 1)}%`, background: ['#55585E', '#0093E7', '#D2D3D6'][i] }} />)}</div>
      <div className={styles.row}><span>SLEEP NEEDED</span><strong>{duration(need)}</strong></div>
      {night.need_components && <div className={styles.components}>{(['baseline', 'strain', 'debt'] as const).map((key, i) => <div className={styles.component} key={key}>
        <span className={styles.swatch} style={{ background: ['#55585E', '#0093E7', '#D2D3D6'][i] }} />{['Baseline sleep', 'Recent strain', 'Sleep debt added'][i]}<strong>{key !== 'baseline' ? '+' : ''}{duration(night.need_components![key])}</strong>
      </div>)}
        {components && components.nap_credit > 0 && <div className={styles.component}><span className={styles.swatch} style={{ background: '#7BA1BB' }} />Nap credit<strong>−{duration(components.nap_credit)}</strong></div>}
        {Math.abs(limitAdjustment) > .01 && <div className={styles.component}><span className={styles.swatch} style={{ background: '#979FA8' }} />Sleep-need limit adjustment<strong>{limitAdjustment >= 0 ? '+' : '−'}{duration(Math.abs(limitAdjustment))}</strong></div>}
      </div>}
      <p className={styles.note}>{need == null ? 'Sleep-need estimate unavailable for this night.' : 'App estimate · Includes weighted sleep debt and nap credit.'}</p>
    </Link>
    <Link href="/sleep/consistency" className={`${styles.card} ${styles.cardLink}`}>
      <div className={styles.heading}>SLEEP CONSISTENCY<span className={styles.info} title="Timing score compared with the four preceding nights; not a clinical measure.">i</span></div>
      <DailyScore value={night.consistency} baseline={analytics.prior_30_averages.consistency} />
      <div className={styles.guide}>USUAL BED / WAKE TIME</div>
      <Chart days={analytics.days.slice(-5)} kind="timing" guides daily />
    </Link>
    <Link href="/sleep/efficiency" className={`${styles.card} ${styles.cardLink}`}>
      <div className={styles.heading}>SLEEP EFFICIENCY<span className={styles.info} title="Asleep minutes divided by the recorded sleep period.">i</span></div>
      <DailyScore value={night.efficiency} baseline={analytics.prior_30_averages.efficiency} />
      <div className={styles.row}><span>ASLEEP</span><strong>{duration(night.asleep_minutes)}</strong></div><Timeline night={night} awake={false} />
      <div style={{ marginTop: 15 }}><Timeline night={night} awake /></div><div className={styles.row}><span>AWAKE</span><strong>{duration(night.awake_minutes)}</strong></div>
      <div className={`${styles.row} ${styles.separator}`}><span><b className={styles.swatch} style={{ background: '#D2D3D6', marginRight: 8 }} />WAKE EVENTS</span><strong>{night.wake_events ?? '—'}</strong></div>
    </Link>
    <Link href="/sleep/stress" className={`${styles.card} ${styles.cardLink}`}>
      <div className={styles.heading}>SLEEP STRESS<span className={styles.info} title="High-stress detection from eligible HR/HRV windows. Not a WHOOP stress score.">i</span></div>
      <div className={styles.score}>{stress?.status === 'ok' && stress.stress_pct != null ? `${Math.round(stress.stress_pct)}%` : '—'}</div>
      <div className={styles.row}><span>HIGH STRESS</span><strong>{duration(high)}</strong></div><div className={styles.track}><span style={{ width: `${stress?.valid_minutes ? 100 * (high ?? 0) / stress.valid_minutes : 0}%`, background: '#F59E0B' }} /></div>
      <div className={styles.row}><span>NO HIGH STRESS DETECTED</span><strong>{duration(other)}</strong></div><div className={styles.track}><span style={{ width: `${stress?.valid_minutes ? 100 * (other ?? 0) / stress.valid_minutes : 0}%` }} /></div>
      <p className={styles.note}>{stress ? `${stress.night_date} · ${duration(stress.valid_minutes)} analyzed · ${stress.confidence} confidence` : stressError || 'No analysis for this night.'} · Unmeasured time is excluded.</p>
      {analytics.is_mock && stress && stress.sleep_id !== night.sleep_id && <p className={styles.note}>Separate synthetic stress sample for this date.</p>}
    </Link>
    <h2 className={styles.weeklyHeading}>Weekly Trends</h2>
    {sleepMetrics.map(item => <Link href={`/sleep/${item.slug}`} key={item.slug} className={`${styles.card} ${styles.cardLink}`}>
      <div className={styles.heading}>{item.title}<span style={{ fontSize: 24, color: '#A5ABB1', lineHeight: .5 }}>›</span></div>
      <ChartLegend kind={item.kind} /><Chart days={analytics.days} kind={item.kind} metric={item.metric} />
      {analytics.days.every(d => d[item.metric] == null) && <p className={styles.note}>No recorded values in this period.</p>}
    </Link>)}
  </div>;
}
