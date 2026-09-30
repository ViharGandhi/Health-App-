/**
 * CircleDial.tsx
 * WHOOP-style full circle dial with percentage inside.
 * Renders an SVG ring that fills based on score percentage.
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
  sublabel,
  size = 110,
  onClick,
  showChevron = false,
  isPrimary = false,
}: CircleDialProps) {
  const pct = Math.min(1, Math.max(0, value / maxValue));

  // SVG full circle
  const strokeWidth = isPrimary ? 8 : 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - pct);
  const center = size / 2;

  const displayValue = maxValue === 21
    ? value.toFixed(1)
    : Math.round(value);

  return (
    <div
      className={`${styles.wrapper} ${isPrimary ? styles.primary : ''}`}
      style={{ width: size, height: 'auto' }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className={styles.ringContainer} style={{ width: size, height: size }}>
        <svg width={size} height={size} className={styles.svg}>
          {/* Background track */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={strokeWidth}
          />
          {/* Filled arc — starts from top (-90 deg rotation) */}
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
              filter: `drop-shadow(0 0 8px ${color}66)`,
              transition: 'stroke-dashoffset 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
            }}
          />
        </svg>

        {/* Center content */}
        <div className={styles.inner}>
          <span className={styles.value} style={{ color }}>
            {displayValue}
            {unit && <span className={styles.unit}>{unit}</span>}
          </span>
        </div>
      </div>

      {/* Label below */}
      <div className={styles.labelRow}>
        <span className={styles.label}>{label}</span>
        {showChevron && <span className={styles.chevron}>›</span>}
      </div>
    </div>
  );
}
