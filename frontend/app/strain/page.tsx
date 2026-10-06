'use client';

/**
 * Strain Detail Page (/strain)
 * 0–21 arc dial, zone breakdown bars, workout list.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import CircleDial from '@/components/CircleDial';
import ZoneBar from '@/components/ZoneBar';
import MetricCard from '@/components/MetricCard';
import MockBanner from '@/components/MockBanner';
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
  const [error, setError] = useState('');

  useEffect(() => {
    api.getStrain()
      .then(setData)
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Strain data unavailable.'))
      .finally(() => setLoading(false));
  }, []);

  if (error) return <div className="page" role="alert" style={{ paddingTop: 24 }}><p>{error}</p><button className="btn btn-primary" onClick={() => window.location.reload()}>Retry</button></div>;

  if (loading || !data) {
    return (
      <div className="page" role="status" aria-live="polite" style={{ paddingTop: 24 }}>
        <p>Loading your strain data…</p>
        <div className="skeleton" style={{ height: 200, borderRadius: 24, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 20 }} />
      </div>
    );
  }

  const color = '#0093E7';
  const label = strainLabel(data.score_21);
  const noHeartRate = !data.is_mock && data.avg_hr === null;

  return (
    <>
    <MockBanner isMock={data.is_mock} />
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title">Strain</h1>
        <span className="pill pill-blue">{data.is_mock ? label : 'EXPERIMENTAL'}</span>
      </div>

      {/* Hero */}
      {data.is_mock ? <div className={`card ${styles.heroCard} fade-in`} style={{ borderColor: `${color}30` }}>
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
      </div> : <div className={`card ${styles.heroCard} fade-in`} style={{ borderColor: `${color}30` }}>
        <p className="section-title">FITBIT HEART-RATE LOAD</p>
        <div className={styles.heroContent}>
          <div className={styles.heroStats}>
            <div className={styles.heroStat}><span className={styles.heroStatLabel}>WORKOUT</span><span className={styles.heroStatValue}>{data.age_is_default || noHeartRate ? '—' : data.workout_strain.toFixed(1)}</span><span className={styles.heroStatSub}>prototype load units</span></div>
            <div className={styles.heroStat}><span className={styles.heroStatLabel}>OTHER ACTIVITY</span><span className={styles.heroStatValue}>{data.age_is_default || noHeartRate ? '—' : data.incidental_strain.toFixed(1)}</span><span className={styles.heroStatSub}>prototype load units</span></div>
            <div className={styles.heroStat}><span className={styles.heroStatLabel}>AVG HR</span><span className={styles.heroStatValue}>{data.avg_hr?.toFixed(0) ?? '—'}<span className={styles.heroStatUnit}>bpm</span></span></div>
          </div>
        </div>
        <p className={styles.calibrationNote}>{data.age_is_default ? <>Add your age in <Link href="/connect">Connection settings</Link> to estimate heart-rate zones.</> : noHeartRate ? 'No heart-rate samples were returned for this date.' : 'This load uses an age-estimated maximum heart rate. The 0–21 score is under review and is shown only in demo mode.'}</p>
      </div>}

      {/* Heart Rate Zones */}
      {(data.is_mock || (!data.age_is_default && !noHeartRate)) && <div className={`card fade-in fade-in-delay-1`}>
        <p className="section-title" style={{ marginBottom: 20 }}>Heart Rate Zones</p>
        <ZoneBar zones={data.zone_minutes} />
      </div>}

      {/* Workouts */}
      {data.workouts.length > 0 && (data.is_mock || !data.age_is_default) && (
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
              {data.is_mock && <span className={styles.workoutScore} style={{ color }}>
                {((w.strain / (data.workout_strain + data.incidental_strain || 1)) * data.score_21).toFixed(1)}
                <span className={styles.workoutScoreUnit}>/21</span>
              </span>}
            </div>
          ))}
        </div>
      )}

      {/* Key metrics */}
      {(data.is_mock || !data.age_is_default) && <div className={`grid-2 fade-in fade-in-delay-3`}>
        <MetricCard
          label="Max HR"
          value={data.max_hr.toFixed(0)}
          unit="bpm"
          sublabel="Tanaka estimate"
          accent={color}
          icon="🔥"
        />
        {data.is_mock && <MetricCard
          label="Prototype score"
          value={data.score_100.toFixed(0)}
          unit="/ 100"
          sublabel="Not validated for Fitbit Air"
          accent={color}
          icon="⚡"
        />}
      </div>}
    </div>
    </>
  );
}
