/**
 * MetricCard.tsx
 * WHOOP-style dark metric card.
 */
'use client';

import styles from './MetricCard.module.css';

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  sublabel?: string;
  accent?: string;  // optional left-border color
  icon?: string;    // emoji or simple icon character
}

export default function MetricCard({
  label,
  value,
  unit,
  sublabel,
  accent,
  icon,
}: MetricCardProps) {
  return (
    <div
      className={styles.card}
      style={accent ? { borderLeft: `3px solid ${accent}` } : undefined}
    >
      {icon && <span className={styles.icon}>{icon}</span>}
      <div className={styles.content}>
        <span className={styles.label}>{label}</span>
        <div className={styles.valueRow}>
          <span className={styles.value}>{value}</span>
          {unit && <span className={styles.unit}>{unit}</span>}
        </div>
        {sublabel && <span className={styles.sublabel}>{sublabel}</span>}
      </div>
    </div>
  );
}
