'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRecoveryAnalytics } from '@/lib/useRecoveryAnalytics';
import { changeColor, dateLabel, localDay, recoveryColor, recoveryLabel, recoveryMetrics, relativeChange } from '@/lib/recovery';
import RecoveryDemoSwitch from '@/components/RecoveryDemoSwitch';
import RecoveryMetricIcon from '@/components/RecoveryMetricIcon';
import RecoveryTrendChart from '@/components/RecoveryTrendChart';
import { RecoveryInfo } from '@/components/RecoveryGuide';
import styles from './page.module.css';

export default function RecoveryPage() {
  const [day, setDay] = useState<string>();
  useEffect(() => {
    const date = new URLSearchParams(window.location.search).get('date');
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date) && date <= localDay()) setDay(date);
  }, []);
  const { data, error, demo, changeDemo } = useRecoveryAnalytics('W', day);
  const [info, setInfo] = useState(false);
  const closeInfo = useCallback(() => setInfo(false), []);
  const current = data?.current;
  const score = current?.score ?? null;
  const color = current ? recoveryColor(current.zone, current.status) : '#77818B';
  const radius = 122, circumference = 2 * Math.PI * radius;
  const latest = data?.days.at(-1);
  const range = data?.typical_ranges.rhr;
  return <div className={styles.page}><div className={styles.container}>
    <header className={styles.header}><Link href="/" aria-label="Back to overview"><svg width="12" height="20" viewBox="0 0 12 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 2-7 8 7 8" /></svg></Link><span>{day && day !== localDay() ? dateLabel(day).toUpperCase() : 'TODAY'}</span>
      <button aria-label="About Recovery" onClick={() => setInfo(true)}><svg width="25" height="25" viewBox="0 0 25 25" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12.5" cy="12.5" r="11" /><path d="M12.5 11v7m0-11v1" /></svg></button></header>
    {!data ? <p className={styles.loading} role={error ? 'alert' : 'status'}>{error ? 'Recovery unavailable. Please try again.' : 'Loading Recovery…'}</p> : <>
      <section className={styles.hero} aria-label="Recovery estimate"><div className={styles.ring}>
        <svg width="260" height="260" viewBox="0 0 260 260" aria-hidden="true"><circle cx="130" cy="130" r={radius} fill="none" stroke="#FFFFFF1A" strokeWidth="16" /><circle cx="130" cy="130" r={radius} fill="none" stroke={color} strokeWidth="16" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - (score ?? 0) / 100)} transform="rotate(-90 130 130)" style={{ transition: 'stroke-dashoffset 700ms ease' }} /></svg>
        <div className={styles.ringContent}><span className={styles.brand}>OJAS</span><div className={styles.score}>{score == null ? '—' : Math.round(score)}{score != null && <small>%</small>}</div><span className={styles.ringLabel}>RECOVERY</span></div>
      </div><div className={styles.estimateLabel}>{demo === 'legacy' && data.is_mock ? 'PROTOTYPE ESTIMATE' : `ESTIMATED${current?.confidence ? ` · ${current.confidence} confidence` : ''}`}</div>
      <div className={styles.zone}>{current && recoveryLabel(current)}</div></section>
      <section className={styles.metrics} aria-label="Recovery measurements">
        {recoveryMetrics.slice(1).map(item => {
          const value = latest?.[item.metric] ?? null;
          const previous = data.prior_30_day_averages[item.metric as 'hrv' | 'rhr' | 'respiratory_rate' | 'sleep_performance'];
          const change = relativeChange(value, previous);
          return <Link key={item.metric} href={`/recovery/${item.slug}`} className={styles.metricRow}>
            <RecoveryMetricIcon metric={item.metric} /><span className={styles.metricName}>{item.title}</span>
            <span className={styles.metricValues}><strong>{value == null ? '—' : value.toFixed(item.digits)}{value != null && item.unit === '%' ? '%' : ''}</strong><small>{previous == null ? '—' : previous.toFixed(item.digits)}{previous != null && item.unit === '%' ? '%' : ''}</small></span>
            <span className={styles.arrow} style={{ color: changeColor(item.metric, change) }}>{change == null ? '›' : Math.abs(change) < .5 ? '•' : change > 0 ? '▲' : '▼'}</span>
          </Link>;
        })}
        <div className={styles.comparisonLegend}><i>▲</i><i style={{ color: '#F5AC22' }}>▼</i>{day ? 'Selected day' : 'Today'} vs. last 30 days</div>
      </section>
      <section className={styles.insight}><p>{current?.status === 'building_reference' ? current.status_reason
        : range && current?.today_rhr != null ? `Your RHR (${current.today_rhr.toFixed(0)} bpm) is ${current.today_rhr >= range.low && current.today_rhr <= range.high ? 'within' : 'outside'} your personal typical range of ${range.low.toFixed(0)}–${range.high.toFixed(0)} bpm. Your Recovery estimate is ${recoveryLabel(current)}. Look at the pattern over several days.`
        : `Your Recovery estimate is ${current ? recoveryLabel(current) : 'unavailable'}. ${current?.confidence === 'low' ? 'The percentage is withheld at low confidence.' : 'Compare your trends and consider how you feel.'}`}</p>
        {current?.illness_flag && <p className={styles.note}>A breathing-rate or skin-temperature deviation capped this estimate.</p>}
        <Link href="/recovery/recovery">EXPLORE YOUR RECOVERY INSIGHTS →</Link>
      </section>
      <section className={styles.behavior}><div className={styles.cardHeader}><span><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9CA5AD" strokeWidth="1.5"><circle cx="12" cy="10" r="5" /><path d="M9 16h6M10 20h4M12 1V0M3 5l-2-1m20 1 2-1M3 12H0m21 0h3" /></svg>BEHAVIOR INSIGHTS</span><span aria-label="Unavailable">›</span></div>
        <p>Behavior insights aren&apos;t available yet. Recorded vitals alone cannot identify which behavior caused a change in Recovery.</p><div className={styles.chips}><span>No behavior history</span><span>No causal analysis</span></div>
      </section>
      <h2 className={styles.weeklyTitle}>Weekly Trends</h2><div className={styles.trendCards}>
        {recoveryMetrics.map(item => <section className={styles.trendCard} key={item.metric}><Link href={`/recovery/${item.slug}`} className={styles.cardHeader} style={{ color: 'inherit', textDecoration: 'none' }}><span>{item.title}</span><svg width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m2 2 5 5.5-5 5.5" /></svg></Link>
          <RecoveryTrendChart data={data} metric={item.metric} embedded />
        </section>)}
      </div><p className={styles.note}>{data.notes}</p>
      {data.is_mock && <RecoveryDemoSwitch value={demo} onChange={changeDemo} />}
    </>}
    <button className={styles.floating} aria-label="Open Recovery guide" onClick={() => setInfo(true)}><span>O</span></button>
    {info && <RecoveryInfo data={current} onClose={closeInfo} />}
  </div></div>;
}
