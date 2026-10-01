'use client';

/**
 * Recovery Detail Page (/recovery)
 * WHOOP-style deep dive into recovery score — HRV, RHR, component breakdown.
 */

import { useEffect, useState } from 'react';
import CircleDial from '@/components/CircleDial';
import MetricCard from '@/components/MetricCard';
import MetricNav from '@/components/MetricNav';
import MockBanner from '@/components/MockBanner';
import ShareButton from '@/components/ShareButton';
import { api } from '@/lib/api';
import type { RecoveryData } from '@/lib/types';
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

export default function RecoveryPage() {
  const [data, setData] = useState<RecoveryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getRecovery()
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (error) return <div className="page" style={{ paddingTop: 24 }}>Could not load recovery data.</div>;
  if (loading || !data) {
    return (
      <div className="page" style={{ paddingTop: 24 }}>
        <div className="skeleton" style={{ height: 200, borderRadius: 24, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />
      </div>
    );
  }

  const color = RECOVERY_COLOR[data.status] ?? '#16EC06';
  const statusLabel = data.status === 'green' ? 'Recovered' : data.status === 'yellow' ? 'Moderate' : 'Low Recovery';

  return (
    <>
      <MockBanner isMock={data.is_mock} />
      <div className="page">
      <MetricNav active="recovery" isMock={data.is_mock}>

      {/* Hero score */}
      <div className={`${styles.heroCard} fade-in`}>
        <div className={styles.heroContent}>
          <CircleDial
            label="RECOVERY"
            value={data.score}
            maxValue={100}
            color={color}
            unit="%"
            size={270}
            hero
          />
          <ShareButton metric="Recovery" value={`${Math.round(data.score)}%`} isMock={data.is_mock} />
        </div>
      </div>

      <div className={styles.summaryCard}>
        <h1>{statusLabel}</h1>
        <p>{data.is_mock ? 'Illustrative recovery estimate from sample measurements.' : 'Recovery estimate based on recent measurements.'}</p>
      </div>

      <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>HRV</span>
              <span className={styles.heroStatValue}>
                {data.today_hrv?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>ms</span>
              </span>
              <span className={styles.heroStatSub}>Baseline {data.hrv_baseline?.toFixed(0) ?? '—'}</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Resting HR</span>
              <span className={styles.heroStatValue}>
                {data.today_rhr?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>bpm</span>
              </span>
              <span className={styles.heroStatSub}>Baseline {data.rhr_baseline?.toFixed(0) ?? '—'}</span>
            </div>
      </div>

      {/* Component breakdown */}
      <div className={`${styles.compCard} fade-in fade-in-delay-1`}>
        <p className="section-title" style={{ marginBottom: 20 }}>Score Breakdown</p>
        <ComponentRow
          label="HRV Score"
          value={data.hrv_component}
          weight="40%"
          color="var(--text-secondary)"
        />
        <ComponentRow
          label="Resting HR"
          value={data.rhr_component}
          weight="25%"
          color="var(--text-secondary)"
        />
        <ComponentRow
          label="Sleep Quality"
          value={data.sleep_component}
          weight="25%"
          color="var(--sleep-blue)"
        />
        <ComponentRow
          label="Strain Recovery"
          value={data.strain_component}
          weight="10%"
          color="var(--strain-blue)"
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
          accent="var(--text-secondary)"
        />
        <MetricCard
          label="Resting HR"
          value={data.today_rhr?.toFixed(0) ?? '—'}
          unit="bpm"
          sublabel="Morning resting"
          accent="var(--text-secondary)"
        />
      </div>

      {/* Training recommendation */}
      <div className={`${styles.recBox} fade-in fade-in-delay-3`} style={{ borderLeft: `3px solid ${color}` }}>
        <p className={styles.recLabel}>Estimated guidance</p>
        <p className={styles.recText}>{data.training_recommendation}</p>
        <p className={styles.recNote}>This formula is under review; treat the guidance as illustrative.</p>
      </div>
      </MetricNav>
    </div>
    </>
  );
}
