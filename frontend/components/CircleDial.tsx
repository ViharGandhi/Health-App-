/**
 * CircleDial.tsx
 * WHOOP-exact circular gauge dial with bold white score inside and label underneath.
 */
'use client';

import React from 'react';
import styles from './CircleDial.module.css';

interface CircleDialProps {
  label: string;
  value: number;
  maxValue: number;
  unit?: string;
  color: string;
  sublabel?: string;
  size?: number;
  onClick?: () => void;
  showChevron?: boolean;
  isPrimary?: boolean;
}

export default function CircleDial({
  label,
  value,
  maxValue,
  unit,
  color,
  size = 94,
  onClick,
  showChevron = true,
  isPrimary = false,
}: CircleDialProps) {
  // Normalize percentage (0 to 1)
  const rawPct = Math.min(1, Math.max(0, value / maxValue));
  // If value > 0 ensure tiny minimum arc is visible like WHOOP's 0.1 strain tick
  const pct = value > 0 ? Math.max(rawPct, 0.016) : 0;

  const strokeWidth = isPrimary ? 7.5 : 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - pct);
  const center = size / 2;

  const displayValue = maxValue === 21
    ? value.toFixed(1)
    : Math.round(value);

  return (
    <div
      className={`${styles.dialWrapper} ${isPrimary ? styles.isPrimary : ''}`}
      style={{ width: size }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className={styles.ringBox} style={{ width: size, height: size }}>
        <svg width={size} height={size} className={styles.svg}>
          {/* Subtle dark background track */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="rgba(255, 255, 255, 0.12)"
            strokeWidth={strokeWidth}
          />
          {/* Active colored arc */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${center} ${center})`}
            style={{
              filter: isPrimary ? `drop-shadow(0 0 6px ${color}80)` : `drop-shadow(0 0 3px ${color}40)`,
              transition: 'stroke-dashoffset 1s cubic-bezier(0.25, 1, 0.5, 1)',
            }}
          />
        </svg>

        {/* Center score - PURE WHITE as in WHOOP */}
        <div className={styles.centerContent}>
          <div className={styles.valueRow}>
            <span className={styles.number}>{displayValue}</span>
            {unit && <span className={styles.unit}>{unit}</span>}
          </div>
        </div>
      </div>

      {/* Label under dial: "SLEEP >", "RECOVERY >", "STRAIN >" */}
      <div className={styles.labelRow}>
        <span className={styles.labelText}>{label}</span>
        {showChevron && <span className={styles.chevron}>&gt;</span>}
      </div>
    </div>
  );
}
