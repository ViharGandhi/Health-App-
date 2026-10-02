'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import MockBanner from './MockBanner';
import { api } from '@/lib/api';
import type { SleepTrend } from '@/lib/types';
import styles from './SleepTrendView.module.css';

type Timeframe = 'W' | '6M' | '1Y';
type Metric = 'efficiency' | 'consistency';

function dateLabel(value: string, year = false) {
  return new Date(`${value}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', ...(year ? { year: 'numeric' as const } : {}) });
}

function TrendChart({ trend, metric, selected, onSelect }: {
  trend: SleepTrend;
  metric: Metric;
  selected: number;
  onSelect: (index: number) => void;
}) {
  const values = trend.days.map((day) => day.value).filter((value): value is number => value !== null);
  if (!values.length) return <div className={styles.emptyChart}>No complete measurements in this range.</div>;
  const min = metric === 'efficiency' ? Math.max(0, Math.floor((Math.min(...values) - 5) / 5) * 5) : 0;
  const max = metric === 'efficiency' ? Math.min(100, Math.ceil((Math.max(...values) + 5) / 5) * 5) : Math.max(20, Math.ceil(Math.max(...values) * 1.2 / 10) * 10);
  const y = (value: number) => 148 - (value - min) / Math.max(1, max - min) * 120;
  const x = (index: number) => 12 + index * 336 / Math.max(1, trend.days.length - 1);
  const segments: { index: number; value: number }[][] = [];
  trend.days.forEach((day, index) => {
    if (day.value === null) return;
    if (index === 0 || trend.days[index - 1].value === null) segments.push([]);
    segments[segments.length - 1].push({ index, value: day.value });
  });
  const selectedDay = trend.days[selected];
  return <div className={styles.chartWrap}>
    <svg viewBox="0 0 360 166" role="img" aria-label={`${metric} trend with gaps for missing measurements`}
      onClick={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        onSelect(Math.min(trend.days.length - 1, Math.max(0, Math.round((event.clientX - rect.left) / rect.width * (trend.days.length - 1)))));
      }}>
      <defs><linearGradient id={`sleep-trend-${metric}`} x1="0" x2="0" y1="0" y2="1"><stop stopColor="#7DACC4" stopOpacity="0.27" /><stop offset="1" stopColor="#7DACC4" stopOpacity="0" /></linearGradient></defs>
      {[0, 0.5, 1].map((fraction) => <line key={fraction} x1="12" x2="348" y1={148 - 120 * fraction} y2={148 - 120 * fraction} stroke="#FFFFFF" strokeOpacity="0.09" strokeWidth="1" />)}
      {segments.map((segment, index) => {
        const line = segment.map((point, position) => `${position ? 'L' : 'M'} ${x(point.index)} ${y(point.value)}`).join(' ');
        const area = `${line} L ${x(segment[segment.length - 1].index)} 148 L ${x(segment[0].index)} 148 Z`;
        return <g key={index}><path d={area} fill={`url(#sleep-trend-${metric})`} /><path d={line} fill="none" stroke="#7DACC4" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></g>;
      })}
      {selectedDay?.value !== null && selectedDay?.value !== undefined && <circle cx={x(selected)} cy={y(selectedDay.value)} r="5" fill="#FFFFFF" stroke="#7DACC4" strokeWidth="2" />}
    </svg>
    <div className={styles.axis}><span>{dateLabel(trend.range_start)}</span><span>{dateLabel(trend.days[Math.floor((trend.days.length - 1) / 2)].date)}</span><span>{dateLabel(trend.range_end)}</span></div>
  </div>;
}

export default function SleepTrendView({ metric }: { metric: Metric }) {
  const [timeframe, setTimeframe] = useState<Timeframe>('W');
  const [trend, setTrend] = useState<SleepTrend | null>(null);
  const [error, setError] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    const load = metric === 'efficiency' ? api.getSleepEfficiencyTrend(timeframe) : api.getSleepConsistencyTrend(timeframe);
    load.then((result) => { if (active) { setTrend(result); setError(false); setSelectedIndex(null); } })
      .catch(() => { if (active) { setError(true); setTrend(null); } });
    return () => { active = false; };
  }, [metric, timeframe]);

  const title = metric === 'efficiency' ? 'SLEEP EFFICIENCY' : 'SLEEP CONSISTENCY';
  const unit = metric === 'efficiency' ? '%' : 'min';
  const latestIndex = trend?.days.findLastIndex((day) => day.value !== null) ?? -1;
  const selected = selectedIndex ?? Math.max(0, latestIndex);
  const selectedDay = trend?.days[selected];
  const displayValue = selectedIndex === null ? trend?.average_value : selectedDay?.value;
  const summaryLabel = selectedIndex === null ? 'RANGE AVERAGE' : dateLabel(selectedDay?.date ?? '');

  return <>
    <MockBanner isMock={trend?.is_mock ?? false} />
    <main className={styles.page}>
      <header className={styles.header}><Link href="/sleep" aria-label="Back to sleep">‹</Link><span>SLEEP / TREND</span><div /></header>
      <nav className={styles.metricNav} aria-label="Sleep trends">
        <Link href="/sleep/efficiency" aria-current={metric === 'efficiency' ? 'page' : undefined}>EFFICIENCY</Link>
        <Link href="/sleep/consistency" aria-current={metric === 'consistency' ? 'page' : undefined}>CONSISTENCY</Link>
      </nav>
      <div className={styles.intro}><span className={styles.eyebrow}>SLEEP ANALYTICS</span><h1>{title}</h1><p>{metric === 'efficiency' ? 'How much of your sleep period was spent asleep.' : 'How steady your sleep timing has been.'}</p></div>
      <div className={styles.rangeTabs} role="group" aria-label="Time range">
        {(['W', '6M', '1Y'] as const).map((range) => <button type="button" key={range} aria-pressed={timeframe === range} onClick={() => { setTrend(null); setTimeframe(range); }}>{range === 'W' ? '1W' : range}</button>)}
      </div>
      {error ? <div className={styles.message}>Could not load sleep history.</div> : !trend ? <div className={styles.loading}>Loading sleep history…</div> : <>
        <section className={styles.hero}>
          <span className={styles.eyebrow}>{summaryLabel}</span>
          <div className={styles.heroNumber}>{displayValue == null ? '—' : Math.round(displayValue)}<small>{displayValue == null ? '' : unit}</small></div>
          <p>{trend.recorded_nights} recorded nights{metric === 'consistency' ? ` · ${trend.scored_days} complete 7-night windows` : ''} · {dateLabel(trend.range_start, timeframe === '1Y')} – {dateLabel(trend.range_end, timeframe === '1Y')}</p>
        </section>
        <section className={styles.chartCard}>
          <div className={styles.cardHeading}><h2>{metric === 'efficiency' ? 'NIGHTLY EFFICIENCY' : '7-NIGHT SLEEP-PERIOD TIMING'}</h2><span>{trend.is_mock ? 'SAMPLE' : 'DEVICE'}</span></div>
          <TrendChart trend={trend} metric={metric} selected={selected} onSelect={setSelectedIndex} />
          <label className={styles.scrubberLabel} htmlFor="sleep-trend-day">Explore dates</label>
          <input id="sleep-trend-day" className={styles.scrubber} type="range" min="0" max={Math.max(0, trend.days.length - 1)} value={selected} onChange={(event) => setSelectedIndex(Number(event.target.value))} />
          <div className={styles.reading}><span>{selectedDay ? dateLabel(selectedDay.date) : '—'}</span><strong>{selectedDay?.value == null ? 'No measurement' : `${selectedDay.value.toFixed(1)} ${unit}`}</strong></div>
          {metric === 'consistency' && selectedDay?.value != null && <p className={styles.detail}>Bedtime variation {selectedDay.bed_variability_minutes?.toFixed(1)} min · Wake-time variation {selectedDay.wake_variability_minutes?.toFixed(1)} min</p>}
          {metric === 'efficiency' && selectedDay?.value != null && <p className={styles.detail}>{selectedDay.asleep_hours?.toFixed(1)} h asleep / {selectedDay.in_bed_hours?.toFixed(1)} h sleep period</p>}
        </section>
        <section className={styles.explain}><span className={styles.eyebrow}>HOW TO READ THIS</span><p>{metric === 'efficiency' ? 'Efficiency is sleep time divided by the recorded sleep period. About 85% or more is a published adult sleep-quality reference; a wearable estimate is not a diagnosis.' : 'Each point is the standard deviation of the midpoint between device-reported bedtime and wake time across seven consecutive nights. Lower values mean steadier timing. This is not the Sleep Regularity Index.'}</p><p>{metric === 'consistency' && 'Missing nights leave gaps; seven consecutive nights are required. '}{trend.is_mock ? 'Illustrative sample history; no device measurements are shown.' : 'These are device-derived estimates. Missing sleep records are not filled with sample data.'}</p></section>
        <p className={styles.sources}>Research: {metric === 'efficiency' ? <><a href="https://pubmed.ncbi.nlm.nih.gov/26194727/">Reed & Sacco, 2016</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/28346153/">Ohayon et al., 2017</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/31778122/">Fitbit validation review, 2019</a></> : <><a href="https://pubmed.ncbi.nlm.nih.gov/33864369/">Fischer et al., 2021</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/28607474/">Phillips et al., 2017</a></>}</p>
      </>}
    </main>
  </>;
}
