'use client';

/**
 * Sleep Detail Page (/sleep)
 * Deep dive: score dial, sleep stages bar, duration vs need,
 * efficiency, HRV & HR during sleep, restfulness.
 */

import { useEffect, useState } from 'react';
import CircleDial from '@/components/CircleDial';
import SleepStagesBar from '@/components/SleepStagesBar';
import MetricCard from '@/components/MetricCard';
import { api } from '@/lib/api';
import type { SleepData } from '@/lib/types';
import styles from './page.module.css';

function ScoreRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={styles.scoreRow}>
      <span className={styles.scoreRowLabel}>{label}</span>
      <div className={styles.scoreRowBar}>
        <div className="progress-track" style={{ flex: 1 }}>
          <div className="progress-fill" style={{ width: `${value}%`, background: color }} />
        </div>
        <span className={styles.scoreRowVal}>{Math.round(value)}</span>
      </div>
    </div>
  );
}

export default function SleepPage() {
  const [data, setData] = useState<SleepData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSleep()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div className="page" style={{ paddingTop: 24 }}>
        <div className="skeleton" style={{ height: 200, borderRadius: 24, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />
      </div>
    );
  }

  const performancePct = Math.min(100, (data.total_sleep_hours / data.sleep_need_hours) * 100);

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">Sleep</h1>
        <span className="pill pill-purple">
          {data.sleep_start ?? '—'} – {data.sleep_end ?? '—'}
        </span>
      </div>

      {/* Hero */}
      <div className={`card ${styles.heroCard} fade-in`}>
        <div className={styles.heroTop}>
          <CircleDial
            label="Sleep"
            value={data.score}
            maxValue={100}
            color="#9B6DFF"
            sublabel={`${data.total_sleep_hours.toFixed(1)}h`}
            size={170}
          />
          <div className={styles.heroRight}>
            <div className={styles.needBlock}>
              <span className={styles.needLabel}>Sleep Need</span>
              <span className={styles.needValue}>{data.sleep_need_hours.toFixed(1)}h</span>
            </div>
            <div className={styles.needBlock}>
              <span className={styles.needLabel}>Performance</span>
              <span className={styles.needValue} style={{ color: '#9B6DFF' }}>
                {Math.round(performancePct)}%
              </span>
            </div>
            <div className={styles.needBlock}>
              <span className={styles.needLabel}>Efficiency</span>
              <span className={styles.needValue}>{data.efficiency_pct.toFixed(0)}%</span>
            </div>
            {data.sleep_debt_hours > 0 && (
              <div className={styles.needBlock}>
                <span className={styles.needLabel}>Sleep Debt</span>
                <span className={styles.needValue} style={{ color: '#FF3B3B' }}>
                  {data.sleep_debt_hours.toFixed(1)}h
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Stages */}
      <div className={`card fade-in fade-in-delay-1`}>
        <p className="section-title" style={{ marginBottom: 16 }}>Sleep Stages</p>
        <SleepStagesBar stages={data.stages} />
      </div>

      {/* Score breakdown */}
      <div className={`card fade-in fade-in-delay-2`}>
        <p className="section-title" style={{ marginBottom: 20 }}>Score Breakdown</p>
        <ScoreRow label="Duration"    value={data.duration_score}    color="#9B6DFF" />
        <ScoreRow label="Stage Mix"   value={data.stage_score}       color="#7B52FF" />
        <ScoreRow label="HR Dip"      value={data.hr_dip_score}      color="#48CFAD" />
        <ScoreRow label="Restfulness" value={data.restfulness_score} color="#4A9EFF" />
      </div>

      {/* Biometric grid */}
      <div className={`grid-2 fade-in fade-in-delay-3`}>
        <MetricCard
          label="Sleeping HRV"
          value={data.sleeping_hrv?.toFixed(0) ?? '—'}
          unit="ms"
          sublabel="Avg during sleep"
          accent="#9B6DFF"
          icon="💜"
        />
        <MetricCard
          label="Sleeping HR"
          value={data.sleeping_hr?.toFixed(0) ?? '—'}
          unit="bpm"
          sublabel="Avg during sleep"
          accent="#FF6B6B"
          icon="❤️"
        />
        <MetricCard
          label="Deep Sleep"
          value={data.stages.deep_minutes.toFixed(0)}
          unit="min"
          sublabel="Target ≥ 20% of need"
          accent="#4A9EFF"
          icon="🌊"
        />
        <MetricCard
          label="REM Sleep"
          value={data.stages.rem_minutes.toFixed(0)}
          unit="min"
          sublabel="Target ≥ 20% of need"
          accent="#A78BFF"
          icon="🌀"
        />
      </div>
    </div>
  );
}
