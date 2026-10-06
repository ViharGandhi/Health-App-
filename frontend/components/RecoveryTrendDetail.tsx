'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { RecoveryRange } from '@/lib/types';
import { useRecoveryAnalytics } from '@/lib/useRecoveryAnalytics';
import { changeColor, dateLabel, localDay, nextPeriod, recoveryMetrics, relativeChange } from '@/lib/recovery';
import RecoveryTrendChart, { type RecoveryChartSelection } from './RecoveryTrendChart';
import RecoveryDemoSwitch from './RecoveryDemoSwitch';
import RecoveryMetricIcon from './RecoveryMetricIcon';
import { RecoveryInfo, RecoveryLearnMore } from './RecoveryGuide';
import styles from '@/app/recovery/page.module.css';

export default function RecoveryTrendDetail({ slug }: { slug: string }) {
  const router = useRouter();
  const config = recoveryMetrics.find(item => item.slug === slug)!;
  const [range, setRange] = useState<RecoveryRange>('W');
  const [endDate, setEndDate] = useState<string>();
  const [forwardPeriods, setForwardPeriods] = useState<string[]>([]);
  const [selection, setSelection] = useState<RecoveryChartSelection | null>(null);
  const [info, setInfo] = useState(false);
  const closeInfo = useCallback(() => setInfo(false), []);
  const { data, error, demo, changeDemo } = useRecoveryAnalytics(range, endDate);
  const average = data?.averages[config.metric] ?? null;
  const previous = data?.previous_averages[config.metric] ?? null;
  const change = relativeChange(average, previous);
  const color = changeColor(config.metric, change);
  const value = selection ? selection.value : average;
  const prior = range === 'W' ? 'week' : range === 'M' ? 'month' : '6 months';
  const band = data?.typical_ranges[config.metric];
  const period = range === 'W' ? '7-day period' : range === 'M' ? '30-day period' : '6-month period';
  const description = average == null ? 'No recorded values are available for this period.'
    : `Your average ${config.title.toLowerCase()} during this ${period} was ${average.toFixed(config.digits)} ${config.unit}. `
      + (band ? `It was ${average < band.low ? 'below' : average > band.high ? 'above' : 'within'} your personal typical range (${band.low.toFixed(config.digits)}–${band.high.toFixed(config.digits)} ${config.unit}) at the end of this period.`
        : previous == null ? 'There are no recorded values for the previous period.' : `The previous period averaged ${previous.toFixed(config.digits)} ${config.unit}.`);
  const changePeriod = (day: string) => { setSelection(null); setEndDate(day); };
  return <div className={styles.page}><div className={styles.detailContainer}>
    <header className={styles.header}><Link href="/recovery" aria-label="Back to Recovery"><svg width="12" height="20" viewBox="0 0 12 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 2-7 8 7 8" /></svg></Link><span>TREND VIEW</span><button aria-label="About Recovery trends" onClick={() => setInfo(true)}><svg width="25" height="25" viewBox="0 0 25 25" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12.5" cy="12.5" r="11" /><path d="M12.5 11v7m0-11v1" /></svg></button></header>
    <div className={styles.selector}><RecoveryMetricIcon metric={config.metric} /><select aria-label="Recovery metric" value={slug} onChange={event => { setSelection(null); router.push(`/recovery/${event.target.value}`); }}>{recoveryMetrics.map(item => <option value={item.slug} key={item.slug}>{item.title}</option>)}</select></div>
    <div className={styles.stats}><div><div className={styles.eyebrow}>{selection?.label ?? 'AVERAGE'}</div><div className={styles.average} style={selection ? { color: '#67AEE6' } : undefined}>{value == null ? '—' : value.toFixed(config.digits)}<small>{config.unit}</small></div></div>
      <div className={styles.tabs} aria-label="Trend period">{(['W', 'M', '6M'] as const).map(item => <button key={item} aria-pressed={range === item} onClick={() => { setSelection(null); setForwardPeriods([]); setRange(item); }}>{item}</button>)}</div>
    </div>
    {data ? <><div className={styles.period}><span className={styles.change} style={{ color, background: `${color}20`, visibility: selection ? 'hidden' : undefined }}>{change == null ? 'No prior comparison' : `${Math.abs(change) < .5 ? '●' : change > 0 ? '▲' : '▼'} ${Math.abs(change).toFixed(0)}% vs. prior ${prior}`}</span>
      <div className={styles.periodNav}><button aria-label="Previous period" onClick={() => { setForwardPeriods([...forwardPeriods, data.range_end]); changePeriod(data.previous_range_end); }}><svg width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="currentColor" strokeWidth="3"><path d="m7 2-5 5.5L7 13" /></svg></button><span>{dateLabel(data.range_start, { month: 'short', day: 'numeric', ...(data.range_start.slice(0, 4) !== data.range_end.slice(0, 4) ? { year: '2-digit' } : {}) })} – {dateLabel(data.range_end, { month: 'short', day: 'numeric', year: '2-digit' })}</span><button aria-label="Next period" disabled={data.range_end >= localDay()} onClick={() => { changePeriod(forwardPeriods.at(-1) ?? nextPeriod(data.range_end, range)); setForwardPeriods(forwardPeriods.slice(0, -1)); }}><svg width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="currentColor" strokeWidth="3"><path d="m2 2 5 5.5L2 13" /></svg></button></div>
    </div><p className={styles.description} style={selection ? { opacity: .4 } : undefined}>{description}</p>
      <RecoveryTrendChart key={`${slug}-${range}-${data.range_end}-${demo}`} data={data} metric={config.metric} onSelect={setSelection} />
      {config.metric === 'recovery' && <p className={styles.note}>{data.is_mock && demo === 'legacy' ? 'Older prototype estimate. Historical prototype scores are not stored, so earlier bars remain blank.' : "Estimated Recovery. Historical readings use HRV/RHR only because historical sleep need isn't stored; confidence is reduced. Low-confidence percentages and missing data remain blank."}</p>}
      {config.metric === 'sleep_performance' && !data.is_mock && <p className={styles.note}>Historical sleep performance is unavailable without historical sleep need. Available values use the existing sleep calculation.</p>}
      <RecoveryLearnMore onOpen={() => setInfo(true)} />
      {data.is_mock && <RecoveryDemoSwitch value={demo} onChange={value => { setSelection(null); changeDemo(value); }} />}
    </> : <div className={styles.loading} role={error ? 'alert' : 'status'}>{error ?? 'Loading history…'}{error && <p><button onClick={() => window.location.reload()}>Retry</button></p>}</div>}
    <button className={styles.floating} aria-label="Open Recovery guide" onClick={() => setInfo(true)}><span>O</span></button>
    {info && <RecoveryInfo data={data?.current} onClose={closeInfo} />}
  </div></div>;
}
