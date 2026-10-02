'use client';

/**
 * Strain Detail Page (/strain)
 * 0–21 arc dial, zone breakdown bars, workout list.
 */

import { useEffect, useState } from 'react';
import CircleDial from '@/components/CircleDial';
import ZoneBar from '@/components/ZoneBar';
import MetricCard from '@/components/MetricCard';
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

function strainColor(score: number): string {
  if (score >= 18) return '#FF3B3B';
  if (score >= 14) return '#FF7043';
  if (score >= 10) return '#4A9EFF';
  if (score >= 5)  return '#48CFAD';
  return '#aaaaaa';
}

export default function StrainPage() {
  const [data, setData] = useState<StrainData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getStrain()
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

  const color = strainColor(data.score_21);
  const label = strainLabel(data.score_21);

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">Strain</h1>
        <span className="pill pill-blue">{label}</span>
      </div>

      {/* Hero */}
      <div className={`card ${styles.heroCard} fade-in`} style={{ borderColor: `${color}30` }}>
        <div className={styles.heroContent}>
          <CircleDial
            label="Strain"
            value={data.score_21}
            maxValue={21}
            color={color}
            sublabel={label.toUpperCase()}
            size={180}
          />
          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.heroStatLabel}>Workout</span>
              <span className={styles.heroStatValue} style={{ color }}>
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
        </div>

        {data.is_calibrating && (
          <div className={styles.calibrationNote}>
            ⚙️ Calibrating — 7+ days needed for personal capacity baseline
          </div>
        )}
      </div>

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
              <span className={styles.workoutScore} style={{ color }}>
                {((w.strain / (data.workout_strain + data.incidental_strain || 1)) * data.score_21).toFixed(1)}
                <span className={styles.workoutScoreUnit}>/21</span>
              </span>
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
          icon="🔥"
        />
        <MetricCard
          label="Score"
          value={data.score_100.toFixed(0)}
          unit="/ 100"
          sublabel="0–100 scale"
          accent={color}
          icon="⚡"
        />
      </div>
    </div>
  );
}
