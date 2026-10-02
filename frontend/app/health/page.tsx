'use client';

import { useEffect, useState } from 'react';
import MockBanner from '@/components/MockBanner';
import { api } from '@/lib/api';
import type { HealthData, HealthPoint, HeartRatePoint } from '@/lib/types';
import styles from './page.module.css';

const METRICS = [
  { key: 'hrv', label: 'Heart rate variability', short: 'HRV', unit: 'ms', digits: 0,
    meaning: 'Daily RMSSD reflects beat-to-beat variation. Compare your own repeated readings; a single value cannot establish readiness.' },
  { key: 'deep_sleep_hrv', label: 'Deep-sleep HRV', short: 'SLEEP HRV', unit: 'ms', digits: 0,
    meaning: 'Deep-sleep RMSSD is a separate, optional device value. It should not be interchanged with daily average RMSSD.' },
  { key: 'nrem_hr', label: 'Non-REM heart rate', short: 'NREM HR', unit: 'bpm', digits: 0,
    meaning: 'Heart rate reported during non-REM sleep. It is not the same measure as all-day resting heart rate.' },
  { key: 'rhr', label: 'Resting heart rate', short: 'RHR', unit: 'bpm', digits: 0,
    meaning: 'A daily resting estimate. Your own pattern is more informative than comparing one number with someone else’s.' },
  { key: 'spo2', label: 'Oxygen saturation', short: 'SpO₂', unit: '%', digits: 1,
    meaning: 'Average oxygen saturation during sleep. Wrist estimates can be affected by fit and motion and cannot diagnose a breathing condition.' },
  { key: 'respiratory_rate', label: 'Respiratory rate', short: 'BREATHING', unit: '/min', digits: 1,
    meaning: 'Average breaths per minute during the main sleep period. Look for sustained changes alongside other context.' },
  { key: 'skin_temperature', label: 'Nightly skin temperature', short: 'SKIN TEMP', unit: '°C', digits: 1,
    meaning: 'Mean skin temperature while asleep. This is not core body temperature or a fever measurement.' },
  { key: 'vo2_max', label: 'Cardio fitness estimate', short: 'VO₂ MAX', unit: 'ml/kg/min', digits: 1,
    meaning: 'A device estimate of aerobic fitness. It is not a laboratory VO₂ max test.' },
] as const;

type MetricKey = (typeof METRICS)[number]['key'];
type Timeframe = 'W' | '6M' | '1Y';

function fmtDate(value: string) {
  return new Date(`${value}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function DailyChart({ points, chosen, onChoose }: {
  points: HealthPoint[];
  chosen: number;
  onChoose: (index: number) => void;
}) {
  const valid = points.map((point) => point.value).filter((value): value is number => value !== null && Number.isFinite(value));
  if (!valid.length) return <div className={styles.emptyChart}>No measurements in this period.</div>;

  const low = Math.min(...valid);
  const high = Math.max(...valid);
  const padding = Math.max((high - low) * 0.2, Math.abs(high) * 0.005, 0.1);
  const lower = low - padding;
  const upper = high + padding;
  const xy = (index: number, value: number) => ({
    x: 16 + index * 318 / Math.max(1, points.length - 1),
    y: 146 - (value - lower) / (upper - lower) * 118,
  });
  const segments: { x: number; y: number }[][] = [];
  points.forEach((point, index) => {
    if (point.value === null) return;
    if (index === 0 || points[index - 1].value === null) segments.push([]);
    segments[segments.length - 1].push(xy(index, point.value));
  });

  return <div className={styles.chartWrap}>
    <svg viewBox="0 0 350 170" role="img" aria-label="Daily trend chart; select a dot for its reading">
      <defs><linearGradient id="health-fill" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#FFFFFF" stopOpacity="0.17" /><stop offset="1" stopColor="#FFFFFF" stopOpacity="0" /></linearGradient></defs>
      {segments.map((segment, index) => {
        const line = segment.map((point, i) => `${i ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
        const area = `${line} L ${segment[segment.length - 1].x} 154 L ${segment[0].x} 154 Z`;
        return <g key={index}><path d={area} fill="url(#health-fill)" /><path d={line} fill="none" stroke="#F1F1F1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></g>;
      })}
      {points.map((point, index) => point.value === null || (points.length > 31 && index !== chosen) ? null : <circle key={point.date}
        cx={xy(index, point.value).x} cy={xy(index, point.value).y}
        r={chosen === index ? 5 : 3} fill={chosen === index ? '#FFFFFF' : '#A6A8AA'}
        stroke="#0B0B0B" strokeWidth="2" role="button" tabIndex={0}
        aria-label={`${fmtDate(point.date)}: ${point.value}`}
        onClick={() => onChoose(index)}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onChoose(index); }} />)}
    </svg>
    <div className={styles.axis}><span>{points[0] ? fmtDate(points[0].date) : ''}</span><span>{points.at(-1) ? fmtDate(points.at(-1)!.date) : ''}</span></div>
  </div>;
}

function HeartRateChart({ points }: { points: HeartRatePoint[] }) {
  if (!points.length) return <div className={styles.emptyChart}>No heart-rate samples today.</div>;
  const minute = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
  const values = points.map((point) => point.value);
  const low = Math.min(...values) - 8;
  const high = Math.max(...values) + 8;
  const firstMinute = minute(points[0].time);
  const lastMinute = minute(points[points.length - 1].time);
  const xy = (point: HeartRatePoint) => ({ x: 16 + (minute(point.time) - firstMinute) / Math.max(1, lastMinute - firstMinute) * 318, y: 146 - (point.value - low) / (high - low) * 118 });
  const segments: HeartRatePoint[][] = [];
  points.forEach((point, index) => {
    if (index === 0 || minute(point.time) - minute(points[index - 1].time) > 30) segments.push([]);
    segments[segments.length - 1].push(point);
  });
  const last = xy(points[points.length - 1]);
  return <div className={styles.chartWrap}>
    <svg viewBox="0 0 350 170" role="img" aria-label="Today’s 15-minute median heart-rate samples">
      {segments.map((segment, index) => <path key={index} d={segment.map((point, i) => {
        const coord = xy(point);
        return `${i ? 'L' : 'M'} ${coord.x} ${coord.y}`;
      }).join(' ')} fill="none" stroke="#F1F1F1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />)}
      <circle cx={last.x} cy={last.y} r="5" fill="#FFFFFF" stroke="#0B0B0B" strokeWidth="2" />
    </svg>
    <div className={styles.axis}><span>{points[0].time}</span><span>{points[points.length - 1].time}</span></div>
  </div>;
}

export default function HealthPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>('W');
  const [data, setData] = useState<HealthData | null>(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState<MetricKey>('hrv');
  const [pointIndex, setPointIndex] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    api.getHealth(timeframe).then((result) => { if (active) { setData(result); setError(false); setPointIndex(null); } })
      .catch(() => { if (active) { setError(true); setData(null); } });
    return () => { active = false; };
  }, [timeframe]);
  if (error) return <div className="page" style={{ paddingTop: 32 }}>Could not load health measurements.</div>;
  if (!data) return <div className="page" style={{ paddingTop: 32 }}><div className="skeleton" style={{ height: 260, borderRadius: 18 }} /></div>;

  const metric = METRICS.find((item) => item.key === selected)!;
  const series = data.metrics[selected] ?? [];
  const latestIndex = series.findLastIndex((point) => point.value !== null);
  const chosen = pointIndex ?? latestIndex;
  const reading = chosen >= 0 ? series[chosen] : null;
  const comparison = reading?.value != null && reading.baseline != null ? reading.value - reading.baseline : null;
  const lastHr = data.heart_rate.at(-1);

  return <>
    <MockBanner isMock={data.is_mock} />
    <div className={`page ${styles.page}`}>
      <header className={styles.header}>
        <span className={styles.eyebrow}>OJAS / BIOLOGY</span>
        <h1>HEALTH</h1>
        <p>Your measurements, in context.</p>
      </header>

      <div className={styles.period}><span>{fmtDate(data.range_start)} – {fmtDate(data.range_end)}</span><span>{data.is_mock ? 'SAMPLE HISTORY' : 'DEVICE HISTORY'}</span></div>
      <div className={styles.rangeTabs} role="group" aria-label="Health history range">
        {(['W', '6M', '1Y'] as const).map((range) => <button key={range} type="button" aria-pressed={timeframe === range}
          onClick={() => { setData(null); setTimeframe(range); }}>{range === 'W' ? '1W' : range}</button>)}
      </div>

      <section className={styles.hrCard}>
        <div className={styles.sectionHeading}><div><span className={styles.eyebrow}>TODAY’S SAMPLED HEART RATE</span><h2>{lastHr ? `${Math.round(lastHr.value)} bpm` : 'No reading'}</h2></div><span className={styles.smallValue}>{lastHr ? `Last sample ${lastHr.time}` : '—'}</span></div>
        <HeartRateChart points={data.heart_rate} />
        <p className={styles.caption}>15-minute median over the sampled window. Gaps are not filled.</p>
      </section>

      <h2 className={styles.sectionTitle}>VITAL SIGNS</h2>
      <div className={styles.metricGrid}>
        {METRICS.map((item) => {
          const values = data.metrics[item.key] ?? [];
          const last = [...values].reverse().find((point) => point.value !== null);
          return <button key={item.key} type="button" className={`${styles.metricCard} ${selected === item.key ? styles.selected : ''}`}
            onClick={() => { setSelected(item.key); setPointIndex(null); }} aria-pressed={selected === item.key}>
            <span>{item.short}</span>
            <strong>{last?.value == null ? '—' : last.value.toFixed(item.digits)}<small>{last?.value == null ? '' : item.unit}</small></strong>
            <em>{last ? fmtDate(last.date) : 'NO DATA'}</em>
            <em>{last?.baseline == null ? 'BUILDING PERSONAL REFERENCE' : `14-DAY MEDIAN ${last.baseline.toFixed(item.digits)} ${item.unit}`}</em>
          </button>;
        })}
      </div>

      <section className={styles.detailCard}>
        <div className={styles.sectionHeading}><div><span className={styles.eyebrow}>{timeframe === 'W' ? '1-WEEK' : timeframe === '6M' ? '6-MONTH' : '1-YEAR'} TREND</span><h2>{metric.label}</h2></div><span className={styles.smallValue}>{reading ? fmtDate(reading.date) : '—'}</span></div>
        <div className={styles.selectedValue}>{reading?.value == null ? '—' : reading.value.toFixed(metric.digits)}<small>{reading?.value == null ? '' : metric.unit}</small></div>
        <DailyChart points={series} chosen={chosen} onChoose={setPointIndex} />
        <label className={styles.scrubberLabel} htmlFor="health-day">Explore dates</label>
        <input id="health-day" className={styles.scrubber} type="range" min="0" max={Math.max(0, series.length - 1)} value={Math.max(0, chosen)} onChange={(event) => setPointIndex(Number(event.target.value))} />
        <p className={styles.caption}>{reading?.value == null ? 'No measurement was returned for this date.' : comparison === null ? 'At least seven earlier readings within 14 days are needed for a personal comparison.' : `${Math.abs(comparison).toFixed(1)} ${selected === 'spo2' ? 'percentage points' : metric.unit} ${comparison >= 0 ? 'above' : 'below'} the median of the prior 14 calendar days.`}{reading?.estimated ? ' Device marked this VO₂ max value as estimated.' : ''}{reading?.method ? ` RHR method: ${reading.method === 'WITH_SLEEP' ? 'includes sleep data' : reading.method === 'ONLY_WITH_AWAKE_DATA' ? 'awake data only' : 'unspecified'}.` : ''}</p>
      </section>

      <section className={styles.interpretation}>
        <span className={styles.eyebrow}>HOW TO READ THIS</span>
        <h2>{metric.short}</h2>
        <p>{metric.meaning}</p>
        <p className={styles.caveat}>{data.is_mock ? 'All values on this screen are illustrative sample data.' : 'A wearable trend is context, not a diagnosis. Missing values mean no measurement was returned.'}</p>
      </section>
      <p className={styles.sources}>Research: <a href="https://pubmed.ncbi.nlm.nih.gov/32023264/" target="_blank" rel="noreferrer">RHR variability</a> · <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC8507742/" target="_blank" rel="noreferrer">HRV and training</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/31107835/" target="_blank" rel="noreferrer">Fitbit fitness estimate</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/35947876/" target="_blank" rel="noreferrer">wearable vital accuracy</a>.</p>
    </div>
  </>;
}
