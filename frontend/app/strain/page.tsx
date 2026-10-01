'use client';

/**
 * Strain Detail Page (/strain)
 * 0–21 arc dial, zone breakdown bars, workout list.
 */

import { useEffect, useState } from 'react';
import CircleDial from '@/components/CircleDial';
import ZoneBar from '@/components/ZoneBar';
import MetricCard from '@/components/MetricCard';
import MetricNav from '@/components/MetricNav';
import MockBanner from '@/components/MockBanner';
import ShareButton from '@/components/ShareButton';
import { api } from '@/lib/api';
import type { StrainData } from '@/lib/types';
import styles from './page.module.css';

function strainLabel(score: number): string {
  if (score >= 18) return 'All Out';
  if (score >= 14) return 'Strenuous';
  if (score >= 10) return 'Moderate';
  if (score >= 5)  return 'Light';
  return 'Minimal';
}

export default function StrainPage() {
  const [data, setData] = useState<StrainData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getStrain()
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (error) return <div className="page" style={{ paddingTop: 24 }}>Could not load strain data.</div>;
  if (loading || !data) {
    return (
      <div className="page" style={{ paddingTop: 24 }}>
        <div className="skeleton" style={{ height: 200, borderRadius: 24, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />
      </div>
    );
  }

  const color = '#0093E7';
  const label = strainLabel(data.score_21);

  return (
    <>
    <MockBanner isMock={data.is_mock} />
    <div className="page">
      <MetricNav active="strain" isMock={data.is_mock}>

      {/* Hero */}
      <div className={`${styles.heroCard} fade-in`}>
        <div className={styles.heroContent}>
          <CircleDial
            label="STRAIN"
            value={data.score_21}
            maxValue={21}
            color={color}
            size={270}
            hero
          />
          <ShareButton metric="Strain" value={data.score_21.toFixed(1)} isMock={data.is_mock} />
        </div>
      </div>

      <div className={styles.summaryCard}>
        <h1>{label}</h1>
        <p>Estimated cardiovascular load on a 0–21 scale. The current formula is under review.</p>
      </div>

      <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Workout</span>
              <span className={styles.heroStatValue}>
                {data.workout_strain.toFixed(1)}
              </span>
              <span className={styles.heroStatSub}>load units</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Incidental</span>
              <span className={styles.heroStatValue}>
                {data.incidental_strain.toFixed(1)}
              </span>
              <span className={styles.heroStatSub}>load units</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Avg HR</span>
              <span className={styles.heroStatValue}>
                {data.avg_hr?.toFixed(0) ?? '—'}
                <span className={styles.heroStatUnit}>bpm</span>
              </span>
            </div>
      </div>
      {data.is_calibrating && <p className={styles.calibrationNote}>Calibrating — 7+ days needed for a personal capacity baseline.</p>}

      {/* Heart Rate Zones */}
      <div className={`card fade-in fade-in-delay-1`}>
        <p className="section-title" style={{ marginBottom: 20 }}>Heart Rate Zones</p>
        <ZoneBar zones={data.zone_minutes} />
      </div>

      {/* Workouts */}
      {data.workouts.length > 0 && (
        <div className={`card fade-in fade-in-delay-2`}>
          <p className="section-title" style={{ marginBottom: 16 }}>Workouts</p>
          {data.workouts.map((w, i) => (
            <div key={i} className={styles.workoutRow}>
              <div className={styles.workoutIcon}>🏃</div>
              <div className={styles.workoutInfo}>
                <span className={styles.workoutName}>{w.activity_name}</span>
                <span className={styles.workoutStrain}>
                  {w.strain.toFixed(1)} load units
                </span>
              </div>
              <span className={styles.workoutScore}>{w.strain.toFixed(1)}<span className={styles.workoutScoreUnit}> load units</span></span>
            </div>
          ))}
        </div>
      )}

      {/* Key metrics */}
      <div className={`grid-2 fade-in fade-in-delay-3`}>
        <MetricCard
          label="Max HR"
          value={data.max_hr.toFixed(0)}
          unit="bpm"
          sublabel="Tanaka estimate"
          accent={color}
        />
        <MetricCard
          label="Score"
          value={data.score_100.toFixed(0)}
          unit="/ 100"
          sublabel="0–100 scale"
          accent={color}
        />
      </div>
      </MetricNav>
    </div>
    </>
  );
}
