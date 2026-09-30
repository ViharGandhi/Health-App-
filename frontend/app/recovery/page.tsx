'use client';

/**
 * Recovery Detail Page (/recovery)
 * WHOOP-style deep dive into recovery score — HRV, RHR, component breakdown.
 */

import { useEffect, useState } from 'react';
import CircleDial from '@/components/CircleDial';
import MetricCard from '@/components/MetricCard';
import { api } from '@/lib/api';
import type { RecoveryData } from '@/lib/types';
import styles from './page.module.css';

const RECOVERY_COLOR: Record<string, string> = {
  green:  '#04d98b',
  yellow: '#f5c518',
  red:    '#ff3b3b',
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

export default function RecoveryPage() {
  const [data, setData] = useState<RecoveryData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getRecovery()
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

  const color = RECOVERY_COLOR[data.status] ?? '#04d98b';
  const statusLabel = data.status === 'green' ? 'Recovered' : data.status === 'yellow' ? 'Moderate' : 'Low Recovery';

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">Recovery</h1>
        <span className={`pill pill-${data.status}`}>{statusLabel}</span>
      </div>

      {/* Hero score */}
      <div className={`${styles.heroCard} fade-in`}>
        <div className={styles.heroContent}>
          <CircleDial
            label="Recovery"
            value={data.score}
            maxValue={100}
            color={color}
            unit="%"
            size={160}
          />
          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>HRV</span>
              <span className={styles.heroStatValue} style={{ color: '#04d98b' }}>
                {data.today_hrv?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>ms</span>
              </span>
              <span className={styles.heroStatSub}>Baseline {data.hrv_baseline?.toFixed(0) ?? '—'}</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Resting HR</span>
              <span className={styles.heroStatValue} style={{ color: '#ff3b3b' }}>
                {data.today_rhr?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>bpm</span>
              </span>
              <span className={styles.heroStatSub}>Baseline {data.rhr_baseline?.toFixed(0) ?? '—'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Component breakdown */}
      <div className={`${styles.compCard} fade-in fade-in-delay-1`}>
        <p className="section-title" style={{ marginBottom: 20 }}>Score Breakdown</p>
        <ComponentRow
          label="HRV Score"
          value={data.hrv_component}
          weight="40%"
          color="#04d98b"
        />
        <ComponentRow
          label="Resting HR"
          value={data.rhr_component}
          weight="25%"
          color="#ff3b3b"
        />
        <ComponentRow
          label="Sleep Quality"
          value={data.sleep_component}
          weight="25%"
          color="#9B6DFF"
        />
        <ComponentRow
          label="Strain Recovery"
          value={data.strain_component}
          weight="10%"
          color="#00a1e4"
        />
        {data.acr_penalty > 0 && (
          <div className={styles.penaltyRow}>
            <span className={styles.penaltyLabel}>ACR Penalty</span>
            <span className={styles.penaltyValue}>−{data.acr_penalty.toFixed(1)} pts</span>
          </div>
        )}
      </div>

      {/* Key metrics grid */}
      <div className={`${styles.metricsGrid} fade-in fade-in-delay-2`}>
        <MetricCard
          label="Today's HRV"
          value={data.today_hrv?.toFixed(0) ?? '—'}
          unit="ms"
          sublabel="rMSSD overnight"
          accent="#04d98b"
          icon="📈"
        />
        <MetricCard
          label="Resting HR"
          value={data.today_rhr?.toFixed(0) ?? '—'}
          unit="bpm"
          sublabel="Morning resting"
          accent="#ff3b3b"
          icon="❤️"
        />
      </div>

      {/* Training recommendation */}
      <div className={`${styles.recBox} fade-in fade-in-delay-3`} style={{ borderLeft: `3px solid ${color}` }}>
        <p className={styles.recLabel}>Training Recommendation</p>
        <p className={styles.recText}>{data.training_recommendation}</p>
      </div>
    </div>
  );
}
