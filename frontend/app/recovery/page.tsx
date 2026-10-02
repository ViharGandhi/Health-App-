'use client';

/**
 * Recovery Detail Page (/recovery)
 * WHOOP-style deep dive into recovery score — HRV, RHR, component breakdown.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import CircleDial from '@/components/CircleDial';
import MetricCard from '@/components/MetricCard';
import MockBanner from '@/components/MockBanner';
import { api } from '@/lib/api';
import type { HealthData, HealthPoint, RecoveryData } from '@/lib/types';
import styles from './page.module.css';

const RECOVERY_COLOR: Record<string, string> = {
  green:  '#16EC06',
  yellow: '#FFDE00',
  red:    '#FF0026',
};

interface ComponentRowProps {
  label: string;
  value: number;
  weight: string;
  color: string;
}

function ComponentRow({ label, value, weight, color }: ComponentRowProps) {
  return (
    <div className={styles.compRow}>
      <div className={styles.compInfo}>
        <span className={styles.compLabel}>{label}</span>
        <span className={styles.compWeight}>{weight}</span>
      </div>
      <div className={styles.compBarWrap}>
        <div className="progress-track" style={{ flex: 1 }}>
          <div
            className="progress-fill"
            style={{ width: `${value}%`, background: color }}
          />
        </div>
        <span className={styles.compValue}>{Math.round(value)}</span>
      </div>
    </div>
  );
}

function VitalChart({ points, color, label }: { points: HealthPoint[]; color: string; label: string }) {
  const values = points.map((point) => point.value).filter((value): value is number => value !== null);
  if (!values.length) return <p className={styles.noTrend}>No recorded {label.toLowerCase()} in this range.</p>;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const pad = Math.max((high - low) * 0.2, 1);
  const x = (index: number) => 8 + index * 324 / Math.max(1, points.length - 1);
  const y = (value: number) => 110 - ((value - low + pad) / (high - low + 2 * pad)) * 95;
  const segments: { index: number; value: number }[][] = [];
  points.forEach((point, index) => {
    if (point.value === null) return;
    if (index === 0 || points[index - 1].value === null) segments.push([]);
    segments[segments.length - 1].push({ index, value: point.value });
  });
  const last = points.findLastIndex((point) => point.value !== null);
  return <svg className={styles.trendChart} viewBox="0 0 340 120" role="img" aria-label={`${label} trend; missing days are gaps`}>
    {segments.map((segment, index) => <path key={index} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round"
      d={segment.map((point, position) => `${position ? 'L' : 'M'} ${x(point.index)} ${y(point.value)}`).join(' ')} />)}
    {last >= 0 && points[last].value !== null && <circle cx={x(last)} cy={y(points[last].value!)} r="5" fill="#fff" stroke={color} strokeWidth="2" />}
  </svg>;
}

export default function RecoveryPage() {
  const [data, setData] = useState<RecoveryData | null>(null);
  const [history, setHistory] = useState<HealthData | null>(null);
  const [timeframe, setTimeframe] = useState<'W' | '6M' | '1Y'>('W');
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getRecovery()
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let active = true;
    api.getHealth(timeframe).then((result) => { if (active) setHistory(result); })
      .catch(() => { if (active) setHistory(null); });
    return () => { active = false; };
  }, [timeframe]);

  if (error) return <div className="page">Could not load recovery.</div>;
  if (loading || !data) {
    return (
      <div className="page" style={{ paddingTop: 24 }}>
        <div className="skeleton" style={{ height: 200, borderRadius: 24, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />
      </div>
    );
  }

  const color = RECOVERY_COLOR[data.status] ?? '#8E95A2';
  const statusLabel = data.is_calibrating ? 'Calibrating' : data.status === 'green' ? 'Recovered' : data.status === 'yellow' ? 'Moderate' : 'Low Recovery';

  return (
    <>
    <MockBanner isMock={data.is_mock} />
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">Recovery</h1>
        <span className="pill" style={{ color, background: `${color}22` }}>{statusLabel}</span>
      </div>

      <nav className={styles.sectionNav} aria-label="Daily metrics">
        <Link href="/">OVERVIEW</Link><Link href="/sleep">SLEEP</Link><span aria-current="page">RECOVERY</span><Link href="/strain">STRAIN</Link>
      </nav>

      {/* Hero score */}
      <div className={`${styles.heroCard} fade-in`}>
        <div className={styles.heroContent}>
          <CircleDial
            label="Recovery"
            value={data.score ?? 0}
            maxValue={100}
            color={color}
            unit="%"
            size={220}
            displayText={data.is_calibrating ? '—' : undefined}
          />
          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>HRV</span>
              <span className={styles.heroStatValue}>
                {data.today_hrv?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>ms</span>
              </span>
              <span className={styles.heroStatSub}>{data.hrv_baseline === null ? 'Building reference' : `14-day median ${data.hrv_baseline.toFixed(0)}`}</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Resting HR</span>
              <span className={styles.heroStatValue}>
                {data.today_rhr?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>bpm</span>
              </span>
              <span className={styles.heroStatSub}>{data.rhr_baseline === null ? 'Building reference' : `14-day median ${data.rhr_baseline.toFixed(0)}`}</span>
            </div>
          </div>
        </div>
      </div>

      {data.is_calibrating && <p className={styles.calibrationNote}>Recovery score is hidden until today’s HRV, resting heart rate, sleep, and seven earlier readings of each vital are available.</p>}

      <section className={styles.trendsCard}>
        <div className={styles.trendsHeading}><span>RECOVERY SIGNALS</span><span>{data.is_mock ? 'SAMPLE' : 'DEVICE'}</span></div>
        <div className={styles.rangeTabs} role="group" aria-label="Recovery signal range">
          {(['W', '6M', '1Y'] as const).map((range) => <button type="button" key={range} aria-pressed={timeframe === range}
            onClick={() => { setHistory(null); setTimeframe(range); }}>{range === 'W' ? '1W' : range}</button>)}
        </div>
        {history ? <>
          <div className={styles.trendBlock}><div><strong>HRV</strong><span>Daily RMSSD · ms</span></div><VitalChart points={history.metrics.hrv ?? []} color="#67AEE6" label="HRV" /></div>
          <div className={styles.trendBlock}><div><strong>RESTING HR</strong><span>Daily estimate · bpm</span></div><VitalChart points={history.metrics.rhr ?? []} color="#FFFFFF" label="resting heart rate" /></div>
          <p className={styles.trendNote}>These are measured inputs, not historical Recovery scores. Gaps mean no device reading. Compare repeated readings against your own history.</p>
        </> : <p className={styles.noTrend}>Loading signal history…</p>}
      </section>

      {/* Component breakdown */}
      {!data.is_calibrating && <div className={`${styles.compCard} fade-in fade-in-delay-1`}>
        <p className="section-title" style={{ marginBottom: 20 }}>Prototype score breakdown</p>
        <ComponentRow
          label="HRV Score"
          value={data.hrv_component ?? 0}
          weight="40%"
          color="#67AEE6"
        />
        <ComponentRow
          label="Resting HR"
          value={data.rhr_component ?? 0}
          weight="25%"
          color="#67AEE6"
        />
        <ComponentRow
          label="Sleep Quality"
          value={data.sleep_component ?? 0}
          weight="25%"
          color="#7BA1BB"
        />
        <ComponentRow
          label="Strain Recovery"
          value={data.strain_component ?? 0}
          weight="10%"
          color="#0093E7"
        />
        {(data.acr_penalty ?? 0) > 0 && (
          <div className={styles.penaltyRow}>
            <span className={styles.penaltyLabel}>ACR Penalty</span>
            <span className={styles.penaltyValue}>−{data.acr_penalty?.toFixed(1)} pts</span>
          </div>
        )}
      </div>}

      {/* Key metrics grid */}
      <div className={`${styles.metricsGrid} fade-in fade-in-delay-2`}>
        <MetricCard
          label="Today's HRV"
          value={data.today_hrv?.toFixed(0) ?? '—'}
          unit="ms"
          sublabel="Daily device RMSSD"
          accent="#67AEE6"
          icon="📈"
        />
        <MetricCard
          label="Resting HR"
          value={data.today_rhr?.toFixed(0) ?? '—'}
          unit="bpm"
          sublabel="Daily resting estimate"
          accent="#67AEE6"
          icon="❤️"
        />
      </div>

      {/* Training recommendation */}
      <div className={`${styles.recBox} fade-in fade-in-delay-3`} style={{ borderLeft: `3px solid ${color}` }}>
        <p className={styles.recLabel}>Experimental guidance</p>
        <p className={styles.recText}>Check your trend before you push.</p>
        <p className={styles.trendNote}>The 0–100 score formula is experimental and has not been validated for Fitbit Air. Interpret HRV and resting heart-rate trends separately.</p>
      </div>
    </div>
    </>
  );
}
