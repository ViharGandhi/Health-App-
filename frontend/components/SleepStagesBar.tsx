/**
 * SleepStagesBar.tsx
 * Horizontal stacked bar showing deep / REM / core / awake proportions.
 * WHOOP-style with color-coded segments and time labels below.
 */
'use client';

import styles from './SleepStagesBar.module.css';
import type { SleepStages } from '@/lib/types';

interface Props {
  stages: SleepStages;
}

function fmt(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const SEGMENTS = [
  { key: 'deep_minutes',  label: 'Deep',  color: '#4A9EFF' },
  { key: 'rem_minutes',   label: 'REM',   color: '#9B6DFF' },
  { key: 'core_minutes',  label: 'Core',  color: '#48CFAD' },
  { key: 'awake_minutes', label: 'Awake', color: 'rgba(255,255,255,0.18)' },
] as const;

export default function SleepStagesBar({ stages }: Props) {
  const total = stages.deep_minutes + stages.rem_minutes + stages.core_minutes + stages.awake_minutes;

  return (
    <div className={styles.wrapper}>
      {/* Stacked bar */}
      <div className={styles.bar}>
        {SEGMENTS.map(({ key, label, color }) => {
          const pct = total > 0 ? (stages[key] / total) * 100 : 0;
          return (
            <div
              key={key}
              className={styles.segment}
              style={{ width: `${pct}%`, background: color }}
              title={`${label}: ${fmt(stages[key])}`}
            />
          );
        })}
      </div>

      {/* Labels */}
      <div className={styles.labels}>
        {SEGMENTS.map(({ key, label, color }) => (
          <div key={key} className={styles.labelItem}>
            <span className={styles.dot} style={{ background: color }} />
            <div className={styles.labelText}>
              <span className={styles.stageName}>{label}</span>
              <span className={styles.stageTime}>{fmt(stages[key])}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
