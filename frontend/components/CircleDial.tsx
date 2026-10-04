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
  displayText?: string;
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
  displayText,
}: CircleDialProps) {
  // Normalize percentage (0 to 1)
  const rawPct = Math.min(1, Math.max(0, value / maxValue));
  // If value > 0 ensure tiny minimum arc is visible like WHOOP's 0.1 strain tick
  const pct = value > 0 ? Math.max(rawPct, 0.016) : 0;

  const strokeWidth = size >= 200 ? 10 : isPrimary ? 6.5 : 5.5;
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
      onKeyDown={onClick ? event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onClick(); } } : undefined}
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
          {/* Active colored arc — crisp flat stroke, no glow */}
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
              transition: 'stroke-dashoffset 1s cubic-bezier(0.25, 1, 0.5, 1)',
            }}
          />
        </svg>

        {/* Center score - PURE WHITE as in WHOOP */}
        <div className={styles.centerContent}>
          <div className={styles.valueRow}>
            <span className={styles.number} style={size >= 200 ? { fontSize: 62 } : undefined}>{displayText ?? displayValue}</span>
            {unit && !displayText && <span className={styles.unit} style={size >= 200 ? { fontSize: 26 } : undefined}>{unit}</span>}
          </div>
        </div>
      </div>

      {/* Label under dial: "SLEEP >", "RECOVERY >", "STRAIN >" */}
      <div className={styles.labelRow}>
        <span className={styles.labelText}>{label}</span>
        {showChevron && (
          <svg className={styles.chevronSvg} width="6" height="9" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 1.5L4.5 5L1 8.5" />
          </svg>
        )}
      </div>
    </div>
  );
}
