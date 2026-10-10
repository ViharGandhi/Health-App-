'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useStrainAnalytics } from '@/lib/useStrainAnalytics';
import { relativeChange } from '@/lib/recovery';
import { strainFormat, strainMetrics, strainValue, STRAIN_BLUE } from '@/lib/strain';
import StrainMetricIcon from '@/components/StrainMetricIcon';
import StrainTrendChart from '@/components/StrainTrendChart';
import StrainGuide from '@/components/StrainGuide';
import MockBanner from '@/components/MockBanner';
import { activityHref } from '@/lib/activity';
import ActivityIcon from '@/components/ActivityIcon';
import shared from '@/app/recovery/page.module.css';
import styles from './page.module.css';

export default function StrainPage() {
  const { data, error, demo, retry } = useStrainAnalytics();
  const [info, setInfo] = useState(false), closeInfo = useCallback(() => setInfo(false), []);
  const latest = data?.days.at(-1), score = data?.current.strain ?? null, target = data?.current.analytics.strain_target;
  const radius = 122, circumference = 2 * Math.PI * radius, suffix = demo ? '?demo=true' : '';
  return <div className={shared.page}><MockBanner isMock={data?.is_mock ?? false} /><div className={shared.container}>
    <header className={shared.header}><Link href="/" aria-label="Back to overview"><svg width="12" height="20" viewBox="0 0 12 20" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 2-7 8 7 8" /></svg></Link><span>TODAY</span><button aria-label="About Strain" onClick={() => setInfo(true)}><svg width="25" height="25" viewBox="0 0 25 25" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12.5" cy="12.5" r="11" /><path d="M12.5 11v7m0-11v1" /></svg></button></header>
    {!data ? <div className={shared.loading} role={error ? 'alert' : 'status'}>{error ?? 'Loading Strain…'}{error && <p><button onClick={retry}>Retry</button></p>}</div> : <>
      <section className={shared.hero} aria-label="Estimated day strain"><div className={shared.ring}>
        <svg width="260" height="260" viewBox="0 0 260 260" aria-hidden="true"><circle cx="130" cy="130" r={radius} fill="none" stroke="#FFFFFF1A" strokeWidth="16" /><circle cx="130" cy="130" r={radius} fill="none" stroke={STRAIN_BLUE} strokeWidth="16" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - (score ?? 0) / 21)} transform="rotate(-90 130 130)" /></svg>
        <div className={shared.ringContent}><span className={shared.brand}>OJAS</span><div className={shared.score}>{strainFormat(score, 'strain')}</div><span className={shared.ringLabel}>STRAIN</span></div>
      </div><div className={shared.estimateLabel}>{data.is_mock ? 'SAMPLE DATA' : 'ESTIMATED'}</div></section>
      <section className={shared.metrics} aria-label="Strain measurements">{strainMetrics.slice(1).map(item => {
        const value = latest ? strainValue(latest, item.key) : null, previous = data.prior_30_day_averages[item.key];
        const change = value != null && value === previous ? 0 : relativeChange(value, previous);
        return <Link key={item.key} href={`/strain/${item.slug}${suffix}`} className={shared.metricRow}><StrainMetricIcon metric={item.key} /><span className={shared.metricName}>{item.title}</span><span className={shared.metricValues}><strong>{strainFormat(value, item.key)}</strong><small>{strainFormat(previous, item.key)}</small></span><span className={shared.arrow} style={{ color: change == null || Math.abs(change) < .5 ? '#959DA5' : change > 0 ? '#00DCA0' : '#F5AC22' }}>{change == null ? '›' : Math.abs(change) < .5 ? '•' : change > 0 ? '▲' : '▼'}</span></Link>;
      })}<div className={shared.comparisonLegend}><i>▲</i><i style={{ color: '#F5AC22' }}>▼</i>Today vs. last 30 days</div></section>
      <p className={shared.note}>{data.current.age_missing ? 'Add your age in Connection settings to calculate cardio Strain.' : `HR coverage: ${Math.round(data.current.coverage * 100)}%${data.current.low_coverage ? ' · Low coverage — effort may be underestimated.' : ''} · ${data.current.label} cardio effort.`} {data.current.day_window.source === 'midnight_fallback' ? 'No main sleep found; day starts at local midnight.' : 'Day starts at your last main wake time.'}{data.current.calibrating && !data.current.age_missing ? ` Using default ${data.current.params.hr_rest_source === 'default' ? 'resting HR' : 'male coefficients'}.` : ''}</p>
      <section className={shared.insight}><p>{data.current.age_missing ? 'Your age is needed to calculate Strain and personal heart-rate zones.' : target ? `Your cardio Day Strain is ${strainFormat(score, 'strain')}. Your Recovery-based target is ${target.low.toFixed(1)}–${target.high.toFixed(1)} (${target.status} target).` : `Your cardio Day Strain is ${strainFormat(score, 'strain')}. A Recovery-based target is unavailable until a Recovery score is available.`}</p><Link href={`/strain/day-strain${suffix}`}>EXPLORE YOUR STRAIN INSIGHTS →</Link></section>
      <h2 className={shared.weeklyTitle}>Today&apos;s Activities</h2>
      <section className={styles.activities} aria-label="Today's activities">{latest?.activities.length ? latest.activities.map(activity => <Link href={`${activityHref(activity.id, latest.date, demo)}&source=strain`} key={activity.id} className={styles.activityRow}>
        <div className={styles.activityBadge} title={activity.strain == null ? 'Activity Strain unavailable' : 'Estimated cardio Strain'}><ActivityIcon name={activity.name} type={activity.exercise_type} /><strong aria-label={activity.strain == null ? 'Activity Strain unavailable' : `Cardio Strain ${activity.strain.toFixed(1)}`}>{activity.strain?.toFixed(1) ?? '—'}</strong></div><span className={styles.activityName}>{activity.name.replaceAll('_', ' ')}</span><div className={styles.activityTimes}><span>{activity.start.slice(11, 16)}</span><span>{activity.end.slice(11, 16)}</span></div>
      </Link>) : <p className={shared.note}>No logged activities for today.</p>}{!!latest?.activities.length && <p className={shared.note}>Activity badges show estimated cardio Strain. Muscular Load is not included.</p>}</section>
      <h2 className={shared.weeklyTitle}>Weekly Trends</h2><div className={shared.trendCards}>{strainMetrics.map(item => <section className={shared.trendCard} key={item.key}>
        <Link href={`/strain/${item.slug}${suffix}`} className={`${shared.cardHeader} ${styles.cardLink}`}><span>{item.key === 'strain' ? 'STRAIN' : item.title.replace('HEART RATE', 'HR')}</span><svg width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m2 2 5 5.5-5 5.5" /></svg></Link><StrainTrendChart data={data} metric={item.key} embedded />
      </section>)}</div>
      <p className={shared.note}>Cardio Strain uses heart-rate-reserve TRIMP and the 0–21 curve. Activity zone times use logged activities only. Missing heart-rate and step readings remain blank.</p>
      <p className={shared.note}>7-day average: {strainFormat(data.current.analytics.avg_strain_7d, 'strain')} · 28-day average: {strainFormat(data.current.analytics.avg_strain_28d, 'strain')} · Acute/chronic load ratio: {data.current.analytics.acute_chronic_ratio?.toFixed(2) ?? 'Needs 21 recorded days'}</p>
      {data.current.suggested_workouts.length > 0 && <p className={shared.note}>{data.current.suggested_workouts.length} unlogged effort period(s) detected. Their load is already included in Day Strain.</p>}
      {data.is_mock && <p className={shared.note}>Synthetic replay · age {data.current.age_used} · RHR {data.current.params.hr_rest} bpm · {data.current.params.sex === 'm' ? 'male' : 'female'} coefficients · Recovery 72%. Scores are calculated from raw sample readings.</p>}
      <div className={styles.previewLinks}><a href={demo ? '/strain' : '/strain?demo=true'}>{demo ? 'Return to connected data' : 'Preview sample data'}</a></div>
    </>}
    <button className={shared.floating} aria-label="Open Strain guide" onClick={() => setInfo(true)}><span>O</span></button>{info && <StrainGuide onClose={closeInfo} />}
  </div></div>;
}
