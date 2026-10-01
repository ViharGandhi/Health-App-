/**
 * ZoneBar.tsx
 * Heart-rate zone breakdown for the Strain detail view.
 * Shows each zone's minutes as a labeled horizontal bar.
 */
'use client';

import styles from './ZoneBar.module.css';
import type { ZoneMinutes } from '@/lib/types';

interface Props {
  zones: ZoneMinutes;
}

const ZONE_CONFIG = [
  { key: 'zone1' as const, label: 'Zone 1', sublabel: 'Light' },
  { key: 'zone2' as const, label: 'Zone 2', sublabel: 'Easy' },
  { key: 'zone3' as const, label: 'Zone 3', sublabel: 'Steady' },
  { key: 'zone4' as const, label: 'Zone 4', sublabel: 'Hard' },
  { key: 'zone5' as const, label: 'Zone 5', sublabel: 'Very hard' },
];

function fmt(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function ZoneBar({ zones }: Props) {
  const maxMinutes = Math.max(...ZONE_CONFIG.map(z => zones[z.key]), 1);

  return (
    <div className={styles.wrapper}>
      {ZONE_CONFIG.map(({ key, label, sublabel }) => {
        const minutes = zones[key];
        const pct = (minutes / maxMinutes) * 100;
        return (
          <div key={key} className={styles.row}>
            <div className={styles.zoneLabel}>
              <span className={styles.zoneName}>{label}</span>
              <span className={styles.zoneSub}>{sublabel}</span>
            </div>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{
                  width: `${pct}%`,
                  background: 'var(--strain-blue)',
                }}
              />
            </div>
            <span className={styles.zoneTime}>{fmt(minutes)}</span>
          </div>
        );
      })}
    </div>
  );
}
