'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { StrainRange } from '@/lib/types';
import { useStrainAnalytics } from '@/lib/useStrainAnalytics';
import { dateLabel, localDay, nextPeriod, relativeChange, shiftDay } from '@/lib/recovery';
import { durationMetric, strainFormat, strainMetrics, strainSummary, STRAIN_BLUE } from '@/lib/strain';
import StrainMetricIcon from './StrainMetricIcon';
import StrainTrendChart, { StrainSelection } from './StrainTrendChart';
import StrainBreakdown from './StrainBreakdown';
import StrainGuide from './StrainGuide';
import MockBanner from './MockBanner';
import shared from '@/app/recovery/page.module.css';
import styles from '@/app/strain/page.module.css';

export default function StrainTrendDetail({ slug }: { slug: string }) {
  const router = useRouter(), metric = strainMetrics.find(item => item.slug === slug)!;
  const [range, setRange] = useState<StrainRange>('W'), [endDate, setEndDate] = useState<string>();
  const [forward, setForward] = useState<string[]>([]), [selected, setSelected] = useState<StrainSelection | null>(null);
  const { data, error, demo, retry } = useStrainAnalytics(range, metric.key, endDate);
  const [info, setInfo] = useState(false), closeInfo = useCallback(() => setInfo(false), []);
  const average = data ? strainSummary(data.days, metric.key, range, data.today) : null;
  const previous = data ? strainSummary(data.previous_days, metric.key, range, data.today) : null;
  const difference = average == null || previous == null ? null : metric.key === 'strain' ? average - previous : relativeChange(average, previous);
  const color = metric.key === 'strain' || difference == null || Math.abs(difference) < .05 ? '#B6BCC2' : difference > 0 ? '#00DCA0' : '#F5AC22';
  const suffix = demo ? '?demo=true' : '', prior = range === 'W' ? 'week' : range === 'M' ? 'month' : '6 months';
  const navigate = (end: string) => { setSelected(null); setEndDate(end); };
  const unit = durationMetric(metric.key) ? 'hr' : '';
  return <div className={shared.page}><MockBanner isMock={data?.is_mock ?? false} /><div className={shared.detailContainer}>
    <header className={shared.header}><Link href={`/strain${suffix}`} aria-label="Back to Strain"><svg width="12" height="20" viewBox="0 0 12 20" fill="none" stroke="currentColor" strokeWidth="2"><path d="m9 2-7 8 7 8" /></svg></Link><span>TREND VIEW</span><span className={styles.headerSpacer} /></header>
    <div className={`${shared.selector} ${styles.selector}`}><StrainMetricIcon metric={metric.key} /><select aria-label="Strain metric" value={slug} onChange={event => router.push(`/strain/${event.target.value}${suffix}`)}>{strainMetrics.map(item => <option key={item.key} value={item.slug}>{item.title}</option>)}</select></div>
    <div className={shared.stats}><div aria-live="polite"><div className={shared.eyebrow}>{selected?.label ?? (durationMetric(metric.key) ? range === 'W' ? 'WEEKLY TOTAL' : 'AVG. WEEKLY TOTAL' : 'AVERAGE')}</div>
      {selected?.zones && metric.key.startsWith('zones') ? (metric.key === 'zones_1_3' ? [2, 1, 0] : [4, 3]).map(i => <div className={styles.zoneReading} key={i} style={{ color: ['#B1C8D2', '#439FC3', '#56BB9E', '#FFAE5B', '#FF661D'][i] }}><strong>{strainFormat(selected.zones![`zone${i + 1}` as keyof typeof selected.zones], metric.key)}<small>hr</small></strong><span>ZONE {i + 1}</span></div>)
        : <div className={shared.average} style={selected ? { color: STRAIN_BLUE } : undefined}>{strainFormat(selected ? selected.value : average, metric.key)}<small>{unit}</small></div>}</div>
      <div className={shared.tabs} aria-label="Trend period">{(['W', 'M', '6M'] as const).map(item => <button key={item} aria-pressed={range === item} onClick={() => { setSelected(null); setRange(item); setEndDate(undefined); setForward([]); }}>{item}</button>)}</div>
    </div>
    {data ? <><div className={`${shared.period} ${styles.period}`}><span className={shared.change} style={{ color, background: `${color}20`, visibility: selected ? 'hidden' : undefined }}>{difference == null ? previous === 0 && average != null ? 'Prior value is zero' : 'No prior comparison' : `${difference > 0 ? '▲' : difference < 0 ? '▼' : '●'} ${Math.abs(difference).toFixed(metric.key === 'strain' ? 1 : 0)}${metric.key === 'strain' ? '' : '%'} vs. prior ${prior}`}</span>
      <div className={shared.periodNav}><button aria-label="Previous period" onClick={() => { setForward([...forward, data.range_end]); navigate(data.previous_range_end); }}>❮</button><span>{dateLabel(data.range_start)} – {dateLabel(data.range_end, { month: 'short', day: 'numeric', year: '2-digit' })}</span><button aria-label="Next period" disabled={data.range_end >= localDay()} onClick={() => { navigate(forward.at(-1) ?? (range === 'M' && durationMetric(metric.key) ? [shiftDay(data.range_end, 28), localDay()].sort()[0] : nextPeriod(data.range_end, range))); setForward(forward.slice(0, -1)); }}>❯</button></div>
    </div>
      <p className={shared.description} style={selected?.zones ? { display: 'none' } : selected ? { opacity: .35 } : undefined}>{average == null ? 'There are not enough recorded readings to calculate this period’s summary.' : durationMetric(metric.key) && range === 'M' ? `You spent ${strainFormat(strainSummary(data.days.slice(-7), metric.key, 'W', data.today), metric.key)} in ${metric.key === 'strength' ? 'strength activities' : metric.key === 'zones_1_3' ? 'zones 1-3' : 'zones 4-5'} in the last 7 days. Your weekly average from the last four weeks was ${strainFormat(average, metric.key)}.` : durationMetric(metric.key) ? `${range === 'W' ? 'During this 7-day period, your total time' : 'Your average weekly total'} in ${metric.title.toLowerCase()} was ${strainFormat(average, metric.key)}.${previous == null ? ' A prior comparison is unavailable.' : ` This was ${average > previous ? 'above' : average < previous ? 'below' : 'the same as'} the prior period (${strainFormat(previous, metric.key)}).`}` : `Your average ${metric.key === 'strain' ? 'estimated Day Strain' : 'steps'} ${range === 'W' ? 'this week' : 'over this period'} was ${strainFormat(average, metric.key)}.${previous == null ? ' A prior comparison is unavailable.' : ` The prior period averaged ${strainFormat(previous, metric.key)}.`}`}</p>
      <StrainTrendChart key={`${slug}-${range}-${data.range_end}-${demo}`} data={data} metric={metric.key} onSelect={setSelected} />
      {metric.key === 'strain' && data.days.some(day => day.low_coverage && day.score != null) && <p className={shared.note}>Some days have low heart-rate coverage. Their cardio estimates may undercount effort.</p>}
      <p className={`${shared.note} ${styles.sourceNote}`}>ⓘ {metric.key === 'strain' ? `Experimental app estimate.${data.days.some(day => day.date === data.today) ? ` Average excludes today (${dateLabel(data.today)}).` : ''}` : metric.key === 'steps' ? 'Steps come from synced wearable daily totals. Missing readings remain blank.' : `${metric.key === 'strength' ? 'Strength activity' : 'Zone'} time is derived from logged activities.${range !== 'W' ? ' Averages use complete weeks with recorded data.' : ''}`}</p>
      <StrainBreakdown data={data} metric={metric.key} />
      {metric.key === 'steps' || durationMetric(metric.key) ? <><button className={styles.unavailableAction} disabled><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">{metric.key === 'steps' ? <><path d="M8 4H5v17h14V4h-3M9 3h6v4H9zM8 11h8M8 15h5" /></> : <path d="M12 3v18M3 12h18" />}</svg>{metric.key === 'steps' ? 'UPDATE YOUR DAILY STEP GOAL' : 'ADD ACTIVITY'}</button><p className={shared.note}>{metric.key === 'steps' ? 'Step-goal settings are' : 'Activity logging is'} unavailable.</p></> : <section className={shared.learnMore}><div className={shared.learnHeader}><span>LEARN MORE</span><button onClick={() => setInfo(true)}>VIEW ALL →</button></div><div className={shared.learnCards}><button className={shared.learnCard} onClick={() => setInfo(true)}><div className={shared.learnVisual}><StrainMetricIcon metric="strain" size={40} /><span>GUIDE</span></div><strong>How Strain is estimated</strong></button><button className={shared.learnCard} onClick={() => setInfo(true)}><div className={shared.learnVisual}><StrainMetricIcon metric="zones_1_3" size={40} /><span>GUIDE</span></div><strong>Understanding heart-rate zones</strong></button></div></section>}
    </> : <div className={shared.loading} role={error ? 'alert' : 'status'}>{error ?? 'Loading Strain history…'}{error && <p><button onClick={retry}>Retry</button></p>}</div>}
    <button className={shared.floating} aria-label="Open Strain guide" onClick={() => setInfo(true)}><span>O</span></button>{info && <StrainGuide onClose={closeInfo} />}
  </div></div>;
}
