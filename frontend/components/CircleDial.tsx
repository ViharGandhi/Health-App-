/**
 * CircleDial.tsx
 * WHOOP-exact circular gauge dial with bold white score inside and label underneath.
 */
'use client';

import { useEffect, useState } from 'react';
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
  hero?: boolean;
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
  hero = false,
}: CircleDialProps) {
  const [displayed, setDisplayed] = useState(0);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDisplayed(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 850);
      setDisplayed(value * (1 - Math.pow(1 - progress, 3)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  const rawPct = Math.min(1, Math.max(0, displayed / maxValue));
  // If value > 0 ensure tiny minimum arc is visible like WHOOP's 0.1 strain tick
  const pct = displayed > 0 ? Math.max(rawPct, 0.016) : 0;

  const strokeWidth = hero ? 10 : isPrimary ? 6.5 : 5.5;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - pct);
  const center = size / 2;

  const displayValue = maxValue === 21
    ? displayed.toFixed(1)
    : Math.round(displayed);

  return (
    <div
      className={`${styles.dialWrapper} ${isPrimary ? styles.isPrimary : ''} ${hero ? styles.hero : ''}`}
      style={{ width: size, maxWidth: '100%' }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      } : undefined}
      aria-label={onClick ? `${label}: ${maxValue === 21 ? value.toFixed(1) : Math.round(value)}${unit ?? ''}` : undefined}
    >
      <div className={styles.ringBox}>
        <svg viewBox={`0 0 ${size} ${size}`} className={styles.svg} aria-hidden="true">
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
              filter: hero ? `drop-shadow(0 0 7px ${color}66)` : undefined,
            }}
          />
        </svg>

        {/* Center score - PURE WHITE as in WHOOP */}
        <div className={styles.centerContent}>
          {hero && <span className={styles.insideLabel}>{label}</span>}
          <div className={styles.valueRow}>
            <span className={styles.number}>{displayValue}</span>
            {unit && <span className={styles.unit}>{unit}</span>}
          </div>
        </div>
      </div>

      {/* Label under dial: "SLEEP >", "RECOVERY >", "STRAIN >" */}
      {!hero && <div className={styles.labelRow}>
        <span className={styles.labelText}>{label}</span>
        {showChevron && (
          <svg className={styles.chevronSvg} width="6" height="9" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 1.5L4.5 5L1 8.5" />
          </svg>
        )}
      </div>}
    </div>
  );
}
