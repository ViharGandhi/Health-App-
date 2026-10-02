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
import type { SleepConsistencyScore, SleepData } from '@/lib/types';
import styles from './page.module.css';

// Segment bar helper: 3 pills (Poor, Sufficient, Optimal)
function SegmentIndicator({ value, isInverse = false, isConsistency = false }: { value: number; isInverse?: boolean; isConsistency?: boolean }) {
  // For stress: 0% is optimal (green). For performance: >= 85% is optimal (green).
  const isOptimal = isConsistency ? value >= 75 : isInverse ? value <= 15 : value >= 85;
  const isSufficient = isConsistency ? value >= 50 && value < 75 : isInverse ? value > 15 && value <= 35 : value >= 70 && value < 85;
  const isPoor = isConsistency ? value < 50 : isInverse ? value > 35 : value < 70;

  return (
    <div className={styles.segmentTrack}>
      <span className={`${styles.segment} ${isPoor ? (isConsistency ? styles.consistencyPoor : styles.segmentPoor) : styles.segmentInactive}`} />
      <span className={`${styles.segment} ${isSufficient ? (isConsistency ? styles.consistencyFair : styles.segmentSufficient) : styles.segmentInactive}`} />
      <span className={`${styles.segment} ${isOptimal ? styles.segmentOptimal : styles.segmentInactive}`} />
    </div>
  );
}

export default function SleepPage() {
  const router = useRouter();
  const [data, setData] = useState<SleepData | null>(null);
  const [consistency, setConsistency] = useState<SleepConsistencyScore | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSleep()
      .then(setData)
      .finally(() => setLoading(false));
    api.getSleepConsistencyScore().then(setConsistency).catch(() => setConsistency(null));
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
  const consistencyPct = consistency?.latest_score;
  const efficiencyPct = data.efficiency_pct == null ? null : Math.round(data.efficiency_pct);
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
            onKeyDown={(event) => { if (event.key === 'Enter') router.push('/sleep/consistency'); }}
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
                <span className={styles.metricSubtitle}>{consistency?.latest_sleep_date ? `Latest sleep · ${consistency.latest_label ?? 'Calibrating'}` : 'No score yet'}</span>
              </div>
            </div>
            <div className={styles.metricRight}>
              {consistencyPct != null && <SegmentIndicator value={consistencyPct} isConsistency />}
              <span className={styles.metricValue}>{consistencyPct == null ? '—' : `${Math.round(consistencyPct)}%`}</span>
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
              {efficiencyPct != null && <SegmentIndicator value={efficiencyPct} />}
              <span className={styles.metricValue}>{efficiencyPct == null ? '—' : `${efficiencyPct}%`}</span>
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

        {/* -- Last Night's Sleep Section (Exact WHOOP UI) -- */}
        <section className={styles.nightSection}>
          <div className={styles.nightSectionHeader}>
            <div className={styles.nightTitleBlock}>
              <h2 className={styles.nightMainTitle}>Last Night's Sleep</h2>
              <div className={styles.nightSubtitle}>
                <span className={styles.nightSubBold}>Today</span>
                <span className={styles.nightSubMuted}> vs. prior 30 days</span>
              </div>
            </div>
            <button className={styles.nightEditBtn} aria-label="Edit sleep times">
              <span>EDIT</span>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
              </svg>
            </button>
          </div>

          <div className={styles.nightCard}>
            {/* Top: HOURS OF SLEEP */}
            <div className={styles.hoursHeaderRow}>
              <span className={styles.hoursLabel}>HOURS OF SLEEP</span>
              <button className={styles.hoursInfoBtn} aria-label="Hours of sleep info">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
              </button>
            </div>

            <div className={styles.hoursScoreBlock}>
              <div className={styles.hoursScoreMain}>
                <span className={styles.hoursScoreValue}>9:06</span>
                <span className={styles.hoursScoreDelta}>▲</span>
              </div>
              <span className={styles.hoursScoreBaseline}>7:36</span>
            </div>

            {/* Intraday Sleep Heart Rate Graph */}
            <div className={styles.hrChartContainer}>
              <div className={styles.hrYAxis}>
                <span>110</span>
                <span>90</span>
                <span>70</span>
                <span>50</span>
                <span>30</span>
              </div>

              <div className={styles.hrGraphBody}>
                <div className={styles.hrGridlines}>
                  <div className={styles.hrGridline} />
                  <div className={styles.hrGridline} />
                  <div className={styles.hrGridline} />
                  <div className={styles.hrGridline} />
                  <div className={styles.hrGridline} />
                </div>

                <svg className={styles.hrSvg} viewBox="0 0 320 100" preserveAspectRatio="none">
                  {/* Sleep start dashed boundary line at x=28 (00:14) */}
                  <line x1="28" y1="0" x2="28" y2="82" stroke="rgba(255,255,255,0.4)" strokeWidth="1" strokeDasharray="3 3" />
                  <circle cx="28" cy="82" r="2.2" fill="#FFFFFF" />

                  {/* Sleep end dashed boundary line at x=286 (09:44) */}
                  <line x1="286" y1="0" x2="286" y2="82" stroke="rgba(255,255,255,0.4)" strokeWidth="1" strokeDasharray="3 3" />
                  <circle cx="286" cy="82" r="2.2" fill="#FFFFFF" />

                  {/* High-frequency Heart Rate waveform */}
                  <path
                    d="M 0,38 L 4,32 L 8,42 L 12,28 L 16,36 L 20,30 L 24,35 L 28,64 L 32,70 L 36,68 L 40,74 L 45,62 L 48,70 L 52,75 L 56,76 L 60,74 L 64,75 L 68,76 L 72,72 L 76,58 L 80,72 L 85,66 L 90,68 L 95,62 L 100,74 L 105,75 L 110,72 L 115,65 L 120,56 L 125,68 L 130,74 L 135,76 L 140,72 L 145,75 L 150,68 L 155,62 L 160,68 L 165,74 L 170,76 L 175,78 L 180,76 L 185,74 L 190,70 L 195,60 L 200,72 L 205,68 L 210,64 L 215,66 L 220,62 L 225,58 L 230,65 L 235,70 L 240,72 L 245,68 L 250,70 L 255,65 L 260,62 L 265,68 L 270,70 L 275,66 L 280,64 L 286,40 L 290,24 L 295,38 L 300,18 L 305,44 L 310,28 L 315,36 L 320,46"
                    fill="none"
                    stroke="#62A4B7"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>

                <div className={styles.hrTimestamps}>
                  <span className={styles.hrTimeStart} style={{ left: '8.75%' }}>00:14</span>
                  <span className={styles.hrTimeEnd} style={{ left: '89.375%' }}>09:44</span>
                </div>
              </div>
            </div>

            {/* Typical Range & Duration Header */}
            <div className={styles.typicalRangeHeader}>
              <div className={styles.typicalRangeTitle}>
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" className={styles.typicalRangeSvg}>
                  <line x1="0" y1="8" x2="3" y2="8" stroke="#8E95A2" strokeWidth="1.5" />
                  <line x1="13" y1="8" x2="16" y2="8" stroke="#8E95A2" strokeWidth="1.5" />
                  <rect x="3" y="2" width="10" height="12" rx="2" stroke="rgba(255, 255, 255, 0.75)" strokeWidth="1.2" strokeDasharray="2 2" fill="none" />
                </svg>
                <span>TYPICAL RANGE</span>
              </div>
              <div className={styles.durationBlock}>
                <span className={styles.durationLabel}>DURATION</span>
                <span className={styles.durationValue}>9:30</span>
              </div>
            </div>

            {/* The 4 Stage Rows with Protruding Transparent Optimal Range Square */}
            <div className={styles.stagesList}>
              {/* AWAKE 4% -> 0:24 */}
              <div className={styles.stageItem}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>AWAKE</span>
                    <span className={styles.stagePctMuted}>4%</span>
                  </div>
                  <span className={styles.stageDurationVal}>0:24</span>
                </div>
                <div className={styles.stageTrackWrapper}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: '4%', background: '#E2E6EE' }} />
                  </div>
                  <div className={styles.typicalRangeBox} style={{ left: '4.5%' }} />
                </div>
              </div>

              {/* LIGHT 52% -> 4:51 */}
              <div className={styles.stageItem}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>LIGHT</span>
                    <span className={styles.stagePctLavender}>52%</span>
                  </div>
                  <span className={styles.stageDurationVal}>4:51</span>
                </div>
                <div className={styles.stageTrackWrapper}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: '52%', background: '#9B8AFB' }} />
                  </div>
                  <div className={styles.typicalRangeBox} style={{ left: '52.5%' }} />
                </div>
              </div>

              {/* SWS (DEEP) 18% -> 1:43 */}
              <div className={styles.stageItem}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>SWS (DEEP)</span>
                    <span className={styles.stagePctPink}>18%</span>
                  </div>
                  <span className={styles.stageDurationVal}>1:43</span>
                </div>
                <div className={styles.stageTrackWrapper}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: '18%', background: '#FF5CD1' }} />
                  </div>
                  <div className={styles.typicalRangeBox} style={{ left: '14.5%' }} />
                </div>
              </div>

              {/* REM 26% -> 2:32 */}
              <div className={styles.stageItem}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>REM</span>
                    <span className={styles.stagePctPurple}>26%</span>
                  </div>
                  <span className={styles.stageDurationVal}>2:32</span>
                </div>
                <div className={styles.stageTrackWrapper}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: '26%', background: '#B040FF' }} />
                  </div>
                  <div className={styles.typicalRangeBox} style={{ left: '11%' }} />
                </div>
              </div>
            </div>


            {/* RESTORATIVE SLEEP Section (Exact WHOOP Image 2) */}
            <div className={styles.restorativeRow}>
              <div className={styles.restorativeLeft}>
                <span className={styles.restorativeDualSquare} />
                <span className={styles.restorativeLabel}>RESTORATIVE SLEEP</span>
              </div>
              <div className={styles.restorativeRight}>
                <div className={styles.restorativeValGroup}>
                  <span className={styles.restorativeValue}>4:15</span>
                  <span className={styles.restorativeDelta}>▲</span>
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
