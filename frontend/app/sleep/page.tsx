'use client';

/**
 * Sleep Detail Page (/sleep)
 * Exact WHOOP app Sleep Performance screen:
 * - Top navigation with back chevron, TODAY, and info icon (no WHOOP branding)
 * - Large circular gauge showing Sleep Performance score (%) with 3-segment status bar
 * - Top caret linking dial to the breakdown card
 * - Breakdown card with:
 *     - HOURS VS. NEEDED
 *     - SLEEP CONSISTENCY
 *     - SLEEP EFFICIENCY
 *     - HIGH SLEEP STRESS
 *   Each with custom icon, 3-segment range bar, and percentage
 * - Range legend: Poor, Sufficient, Optimal
 * - Detailed Sleep Stages breakdown (Deep, REM, Core, Awake)
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepData } from '@/lib/types';
import styles from './page.module.css';

// Segment bar helper: 3 pills (Poor, Sufficient, Optimal)
function SegmentIndicator({ value, isInverse = false }: { value: number; isInverse?: boolean }) {
  // For stress: 0% is optimal (green). For performance: >= 85% is optimal (green).
  const isOptimal = isInverse ? value <= 15 : value >= 85;
  const isSufficient = isInverse ? value > 15 && value <= 35 : value >= 70 && value < 85;
  const isPoor = isInverse ? value > 35 : value < 70;

  return (
    <div className={styles.segmentTrack}>
      <span className={`${styles.segment} ${isPoor ? styles.segmentPoor : styles.segmentInactive}`} />
      <span className={`${styles.segment} ${isSufficient ? styles.segmentSufficient : styles.segmentInactive}`} />
      <span className={`${styles.segment} ${isOptimal ? styles.segmentOptimal : styles.segmentInactive}`} />
    </div>
  );
}

export default function SleepPage() {
  const router = useRouter();
  const [data, setData] = useState<SleepData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSleep()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div className={styles.loadingPage}>
        <div className="skeleton" style={{ width: 210, height: 210, borderRadius: '50%', marginBottom: 24 }} />
        <div className="skeleton" style={{ width: '100%', maxWidth: 440, height: 260, borderRadius: 18 }} />
      </div>
    );
  }

  // Key metrics
  const sleepScore = Math.round(data.score);
  const hoursVsNeededPct = Math.min(100, Math.round((data.total_sleep_hours / data.sleep_need_hours) * 100));
  const consistencyPct = data.consistency_score ?? 80;
  const efficiencyPct = Math.round(data.efficiency_pct);
  const sleepStressPct = 0; // Optimal (0% high stress)

  // Circular gauge calculations
  const dialSize = 220;
  const strokeWidth = 11;
  const radius = (dialSize - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(1, Math.max(0, sleepScore / 100));
  const dashOffset = circumference * (1 - pct);
  const center = dialSize / 2;

  // Stages breakdown in hours/mins
  const { stages } = data;
  const formatMins = (mins: number) => {
    const h = Math.floor(mins / 60);
    const m = Math.round(mins % 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  return (
    <div className={styles.pageWrapper}>
      <div className={styles.container}>
        {/* -- Top Navigation Bar -- */}
        <header className={styles.topNav}>
          <button className={styles.navBackBtn} onClick={() => router.push('/')} aria-label="Back">
            <svg width="10" height="16" viewBox="0 0 10 16" fill="none" stroke="#FFFFFF" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8.5 1.5L2 8L8.5 14.5" />
            </svg>
          </button>

          <span className={styles.navTitle}>TODAY</span>

          <button className={styles.navInfoBtn} aria-label="Info">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
          </button>
        </header>

        {/* -- Hero Circular Sleep Dial (NO WHOOP branding) -- */}
        <section className={styles.dialSection} aria-label="Sleep Performance Gauge">
          <div className={styles.dialBox} style={{ width: dialSize, height: dialSize }}>
            <svg width={dialSize} height={dialSize} className={styles.svgRing}>
              {/* Dark subtle track */}
              <circle
                cx={center}
                cy={center}
                r={radius}
                fill="none"
                stroke="rgba(255, 255, 255, 0.12)"
                strokeWidth={strokeWidth}
              />
              {/* Active Sleep teal arc */}
              <circle
                cx={center}
                cy={center}
                r={radius}
                fill="none"
                stroke="#5B9BB0"
                strokeWidth={strokeWidth}
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={dashOffset}
                transform={`rotate(-90 ${center} ${center})`}
                style={{
                  transition: 'stroke-dashoffset 1.2s cubic-bezier(0.25, 1, 0.5, 1)',
                }}
              />
            </svg>

            {/* Inner Content: Score, SLEEP PERFORMANCE, and segment bar */}
            <div className={styles.dialInner}>
              <div className={styles.scoreRow}>
                <span className={styles.scoreNumber}>{sleepScore}</span>
                <span className={styles.scoreUnit}>%</span>
              </div>
              <div className={styles.scoreLabel}>
                <span>SLEEP</span>
                <span>PERFORMANCE</span>
              </div>
              <div className={styles.dialSegments}>
                <SegmentIndicator value={sleepScore} />
              </div>
            </div>
          </div>

          {/* Caret pointer connecting dial to card */}
          <div className={styles.cardCaret} />
        </section>

        {/* -- Main Breakdown Card -- */}
        <section className={styles.breakdownCard}>
          {/* Row 1: HOURS VS. NEEDED */}
          <div className={styles.metricRow}>
            <div className={styles.metricLeft}>
              <div className={styles.iconCircle}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              </div>
              <span className={styles.metricTitle}>HOURS VS. NEEDED</span>
            </div>
            <div className={styles.metricRight}>
              <SegmentIndicator value={hoursVsNeededPct} />
              <span className={styles.metricValue}>{hoursVsNeededPct}%</span>
            </div>
          </div>

          {/* Row 2: SLEEP CONSISTENCY (Clickable -> Trend View) */}
          <div
            className={styles.metricRow}
            onClick={() => router.push('/sleep/consistency')}
            role="button"
            tabIndex={0}
            style={{ cursor: 'pointer' }}
          >
            <div className={styles.metricLeft}>
              <div className={styles.iconCircle}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 3a9 9 0 1 0 9 9" />
                  <path d="M19 12.79A7 7 0 1 1 11.21 5" />
                </svg>
              </div>
              <div className={styles.metricTextGroup}>
                <span className={styles.metricTitle}>SLEEP CONSISTENCY</span>
                {data.average_bed_time && data.average_wake_time && (
                  <span className={styles.metricSubtitle}>
                    4-Day Avg: {data.average_bed_time} – {data.average_wake_time}
                  </span>
                )}
              </div>
            </div>
            <div className={styles.metricRight}>
              <SegmentIndicator value={consistencyPct} />
              <span className={styles.metricValue}>{consistencyPct}%</span>
              <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
            </div>
          </div>

          {/* Row 3: SLEEP EFFICIENCY (Clickable -> Trend View) */}
          <div
            className={styles.metricRow}
            onClick={() => router.push('/sleep/efficiency')}
            role="button"
            tabIndex={0}
            style={{ cursor: 'pointer' }}
          >
            <div className={styles.metricLeft}>
              <div className={styles.iconCircle}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
              </div>
              <span className={styles.metricTitle}>SLEEP EFFICIENCY</span>
            </div>
            <div className={styles.metricRight}>
              <SegmentIndicator value={efficiencyPct} />
              <span className={styles.metricValue}>{efficiencyPct}%</span>
              <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
            </div>
          </div>


          {/* Row 4: HIGH SLEEP STRESS */}
          <div className={styles.metricRow}>
            <div className={styles.metricLeft}>
              <div className={styles.iconCircle}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2v4" />
                  <path d="M12 18v4" />
                  <path d="M4.93 4.93l2.83 2.83" />
                  <path d="M16.24 16.24l2.83 2.83" />
                  <path d="M2 12h4" />
                  <path d="M18 12h4" />
                </svg>
              </div>
              <span className={styles.metricTitle}>HIGH SLEEP STRESS</span>
            </div>
            <div className={styles.metricRight}>
              <SegmentIndicator value={sleepStressPct} isInverse />
              <span className={styles.metricValue}>{sleepStressPct}%</span>
            </div>
          </div>

          {/* Range Legend: Poor, Sufficient, Optimal */}
          <div className={styles.legendRow}>
            <div className={styles.legendItem}>
              <span className={styles.legendBarPoor} />
              <span className={styles.legendText}>Poor</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.legendBarSufficient} />
              <span className={styles.legendText}>Sufficient</span>
            </div>
            <div className={styles.legendItem}>
              <span className={styles.legendBarOptimal} />
              <span className={styles.legendText}>Optimal</span>
            </div>
          </div>
        </section>

        {/* -- Sleep Stages Breakdown Section -- */}
        <section className={styles.stagesSection}>
          <div className={styles.stagesHeader}>
            <span className={styles.stagesTitle}>SLEEP STAGES</span>
            <span className={styles.stagesTotal}>{data.total_sleep_hours.toFixed(1)} hrs total</span>
          </div>

          <div className={styles.stagesGrid}>
            <div className={styles.stageCard}>
              <span className={styles.stageLabel}>DEEP</span>
              <span className={styles.stageDuration}>{formatMins(stages.deep_minutes)}</span>
              <span className={styles.stagePct}>{Math.round((stages.deep_minutes / stages.total_minutes) * 100)}%</span>
            </div>
            <div className={styles.stageCard}>
              <span className={styles.stageLabel}>REM</span>
              <span className={styles.stageDuration}>{formatMins(stages.rem_minutes)}</span>
              <span className={styles.stagePct}>{Math.round((stages.rem_minutes / stages.total_minutes) * 100)}%</span>
            </div>
            <div className={styles.stageCard}>
              <span className={styles.stageLabel}>LIGHT / CORE</span>
              <span className={styles.stageDuration}>{formatMins(stages.core_minutes)}</span>
              <span className={styles.stagePct}>{Math.round((stages.core_minutes / stages.total_minutes) * 100)}%</span>
            </div>
            <div className={styles.stageCard}>
              <span className={styles.stageLabel}>AWAKE</span>
              <span className={styles.stageDuration}>{formatMins(stages.awake_minutes)}</span>
              <span className={styles.stagePct}>{Math.round((stages.awake_minutes / stages.total_minutes) * 100)}%</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
