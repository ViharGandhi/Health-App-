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


          {/* Row 4: HIGH SLEEP STRESS (Clickable -> Trend View) */}
          <div
            className={styles.metricRow}
            onClick={() => router.push('/sleep/stress')}
            role="button"
            tabIndex={0}
            style={{ cursor: 'pointer' }}
          >
            <div className={styles.metricLeft}>
              <div className={styles.iconCircle}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              </div>
              <span className={styles.metricTitle}>HIGH SLEEP STRESS</span>
            </div>
            <div className={styles.metricRight}>
              <SegmentIndicator value={sleepStressPct} isInverse />
              <span className={styles.metricValue}>{sleepStressPct}%</span>
              <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
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

        {/* -- Last Night's Sleep Detailed Breakdown (Exact WHOOP UI) -- */}
        <section className={styles.lastNightSection}>
          {/* Section Header */}
          <div className={styles.lastNightHeader}>
            <div className={styles.lastNightTitles}>
              <h2 className={styles.lastNightTitle}>Last Night&apos;s Sleep</h2>
              <span className={styles.lastNightSubtitle}>Today vs. prior 30 days</span>
            </div>
            <button className={styles.editBtn} aria-label="Edit sleep times">
              <span>EDIT</span>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          </div>

          {/* Main Card */}
          <div className={styles.sleepDetailCard}>
            {/* Hours of Sleep Header */}
            <div className={styles.hoursHeaderRow}>
              <span className={styles.hoursHeaderLabel}>HOURS OF SLEEP</span>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            </div>

            {/* Score & Baseline */}
            <div className={styles.hoursValueRow}>
              <span className={styles.hoursValueBig}>9:06</span>
              <span className={styles.hoursGreenArrow}>▲</span>
            </div>
            <span className={styles.hoursBaseline}>7:36</span>

            {/* Heart Rate / Sleep Intraday Graph */}
            <div className={styles.hrGraphWrapper}>
              {/* Y-axis labels on left */}
              <div className={styles.hrYAxis}>
                <span>110</span>
                <span>90</span>
                <span>70</span>
                <span>50</span>
                <span>30</span>
              </div>

              {/* Chart body */}
              <div className={styles.hrChartBody}>
                <svg className={styles.hrSvg} viewBox="0 0 320 85" preserveAspectRatio="none">
                  {/* Subtle horizontal grid lines */}
                  <line x1="0" y1="5" x2="320" y2="5" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
                  <line x1="0" y1="24" x2="320" y2="24" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
                  <line x1="0" y1="43" x2="320" y2="43" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
                  <line x1="0" y1="62" x2="320" y2="62" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
                  <line x1="0" y1="80" x2="320" y2="80" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />

                  {/* Pre-sleep dim shade (x 0 to 22) */}
                  <rect x="0" y="0" width="22" height="85" fill="rgba(0,0,0,0.3)" />

                  {/* Sleep onset dotted vertical line at 00:14 */}
                  <line x1="22" y1="2" x2="22" y2="85" stroke="#FFFFFF" strokeDasharray="2 2" strokeWidth="1.2" opacity="0.65" />
                  <circle cx="22" cy="3" r="2.2" fill="#FFFFFF" />

                  {/* Wake-up dotted vertical line at 09:44 */}
                  <line x1="298" y1="2" x2="298" y2="85" stroke="#FFFFFF" strokeDasharray="2 2" strokeWidth="1.2" opacity="0.65" />
                  <circle cx="298" cy="3" r="2.2" fill="#FFFFFF" />

                  {/* Post-wake dim shade (x 298 to 320) */}
                  <rect x="298" y="0" width="22" height="85" fill="rgba(0,0,0,0.3)" />

                  {/* Heart rate trace (replicates exact WHOOP nocturnal signal) */}
                  <path
                    d="M 0,38 L 4,32 L 8,36 L 12,28 L 16,34 L 20,40 L 22,12 L 24,48 L 28,42 L 32,54 L 36,46 L 40,58 L 44,52 L 48,56 L 52,48 L 56,60 L 60,54 L 64,52 L 68,48 L 72,55 L 76,50 L 80,48 L 84,40 L 88,52 L 92,46 L 96,56 L 100,50 L 104,52 L 108,44 L 112,56 L 116,48 L 120,54 L 124,42 L 128,50 L 132,48 L 136,56 L 140,52 L 144,46 L 148,58 L 152,50 L 156,54 L 160,44 L 164,52 L 168,48 L 172,56 L 176,38 L 180,50 L 184,46 L 188,54 L 192,50 L 196,48 L 200,56 L 204,52 L 208,48 L 212,54 L 216,46 L 220,52 L 224,36 L 228,48 L 232,46 L 236,54 L 240,48 L 244,52 L 248,46 L 252,54 L 256,44 L 260,52 L 264,48 L 268,54 L 272,46 L 276,52 L 280,48 L 284,54 L 288,44 L 292,50 L 296,28 L 298,14 L 302,46 L 306,32 L 310,42 L 314,30 L 320,44"
                    fill="none"
                    stroke="#5A99B8"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>

                {/* Start & End time markers under vertical lines */}
                <div className={styles.hrTimeLabels}>
                  <span className={styles.hrTimeStart}>00:14</span>
                  <span className={styles.hrTimeEnd}>09:44</span>
                </div>
              </div>
            </div>

            {/* Typical Range & Duration Row */}
            <div className={styles.typicalHeaderRow}>
              <div className={styles.typicalLeft}>
                <span className={styles.typicalBoxIcon} />
                <span>TYPICAL RANGE</span>
              </div>
              <div className={styles.durationRight}>
                <span className={styles.durationLabel}>DURATION</span>
                <span className={styles.durationVal}>9:30</span>
              </div>
            </div>

            {/* The 4 Sleep Stage Rows with Diagonal Stripe Pattern & Range Boxes */}
            <div className={styles.stagesList}>
              {/* Row 1: AWAKE 4% (0:24) */}
              <div className={styles.stageItem}>
                <div className={styles.stageItemHeader}>
                  <div className={styles.stageTitleGroup}>
                    <span className={`${styles.stageCircleIcon} ${styles.circleAwake}`} />
                    <span className={styles.stageName}>AWAKE</span>
                    <span className={styles.stagePct}>4%</span>
                  </div>
                  <span className={styles.stageDuration}>0:24</span>
                </div>
                <div className={styles.stageTrack}>
                  <div className={`${styles.stageFill} ${styles.fillAwake}`} style={{ width: '6%' }} />
                  {/* Dashed Typical Range Overlay */}
                  <div className={styles.typicalRangeBox} style={{ left: '2%', width: '8%' }} />
                </div>
              </div>

              {/* Row 2: LIGHT 52% (4:51) */}
              <div className={styles.stageItem}>
                <div className={styles.stageItemHeader}>
                  <div className={styles.stageTitleGroup}>
                    <span className={`${styles.stageCircleIcon} ${styles.circleLight}`} />
                    <span className={styles.stageName}>LIGHT</span>
                    <span className={`${styles.stagePct} ${styles.pctLight}`}>52%</span>
                  </div>
                  <span className={styles.stageDuration}>4:51</span>
                </div>
                <div className={styles.stageTrack}>
                  <div className={`${styles.stageFill} ${styles.fillLight}`} style={{ width: '52%' }} />
                  <div className={styles.typicalRangeBox} style={{ left: '46%', width: '14%' }} />
                </div>
              </div>

              {/* Row 3: SWS (DEEP) 18% (1:43) */}
              <div className={styles.stageItem}>
                <div className={styles.stageItemHeader}>
                  <div className={styles.stageTitleGroup}>
                    <span className={`${styles.stageCircleIcon} ${styles.circleDeep}`} />
                    <span className={styles.stageName}>SWS (DEEP)</span>
                    <span className={`${styles.stagePct} ${styles.pctDeep}`}>18%</span>
                  </div>
                  <span className={styles.stageDuration}>1:43</span>
                </div>
                <div className={styles.stageTrack}>
                  <div className={`${styles.stageFill} ${styles.fillDeep}`} style={{ width: '18%' }} />
                  <div className={styles.typicalRangeBox} style={{ left: '16%', width: '10%' }} />
                </div>
              </div>

              {/* Row 4: REM 26% (2:32) */}
              <div className={styles.stageItem}>
                <div className={styles.stageItemHeader}>
                  <div className={styles.stageTitleGroup}>
                    <span className={`${styles.stageCircleIcon} ${styles.circleRem}`} />
                    <span className={styles.stageName}>REM</span>
                    <span className={`${styles.stagePct} ${styles.pctRem}`}>26%</span>
                  </div>
                  <span className={styles.stageDuration}>2:32</span>
                </div>
                <div className={styles.stageTrack}>
                  <div className={`${styles.stageFill} ${styles.fillRem}`} style={{ width: '26%' }} />
                  <div className={styles.typicalRangeBox} style={{ left: '20%', width: '12%' }} />
                </div>
              </div>
            </div>

            {/* Restorative Sleep Divider & Bottom Metric */}
            <div className={styles.restorativeRow}>
              <div className={styles.restorativeLeft}>
                {/* Diagonal split square: half REM purple, half SWS pink */}
                <div className={styles.restorativeSquareIcon} />
                <span className={styles.restorativeTitle}>RESTORATIVE SLEEP</span>
              </div>
              <div className={styles.restorativeRight}>
                <div className={styles.restorativeValRow}>
                  <span className={styles.restorativeVal}>4:15</span>
                  <span className={styles.restorativeGreenArrow}>▲</span>
                </div>
                <span className={styles.restorativeBaseline}>3:02</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

