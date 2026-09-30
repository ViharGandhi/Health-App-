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
  { key: 'zone1' as const, label: 'Zone 1', sublabel: 'Warm Up', color: '#64D9FF' },
  { key: 'zone2' as const, label: 'Zone 2', sublabel: 'Fat Burn', color: '#48CFAD' },
  { key: 'zone3' as const, label: 'Zone 3', sublabel: 'Aerobic',  color: '#FFCE54' },
  { key: 'zone4' as const, label: 'Zone 4', sublabel: 'Threshold',color: '#FF7043' },
  { key: 'zone5' as const, label: 'Zone 5', sublabel: 'Max',      color: '#FF4444' },
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
      {ZONE_CONFIG.map(({ key, label, sublabel, color }) => {
        const minutes = zones[key];
        const pct = (minutes / maxMinutes) * 100;
        return (
          <div key={key} className={styles.row}>
            <div className={styles.zoneLabel}>
              <span className={styles.zoneName} style={{ color }}>{label}</span>
              <span className={styles.zoneSub}>{sublabel}</span>
            </div>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{
                  width: `${pct}%`,
                  background: color,
                  boxShadow: minutes > 0 ? `0 0 8px ${color}66` : 'none',
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
