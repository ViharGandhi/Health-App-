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
import type { SleepConsistencyScore, SleepData, SleepStressHistory, SleepStageRangeHistory, SleepStageRangeMetric, SleepStage } from '@/lib/types';
import styles from './page.module.css';
import SleepHeartRateChart from './SleepHeartRateChart';

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

function stageDuration(minutes: number | undefined): string {
  if (minutes == null) return '—';
  const rounded = Math.round(minutes);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}

function rangeDescription(metric: SleepStageRangeMetric | undefined): string | undefined {
  if (!metric?.range) return undefined;
  const { low, high, n } = metric.range;
  const duration = metric.range_minutes;
  return `Your usual range: ${low.toFixed(1)}–${high.toFixed(1)}%${duration ? ` (${stageDuration(duration.low)}–${stageDuration(duration.high)})` : ''}. ${metric.status} your usual. Based on ${n} nights; provisional.`;
}

function TypicalRangeMarker({ metric }: { metric: SleepStageRangeMetric | undefined }) {
  if (!metric?.range) return null;
  return <div className={styles.typicalRangeBox} role="img" aria-label={rangeDescription(metric)}
    style={{ left: `${metric.range.low}%`, width: `${metric.range.high - metric.range.low}%` }} />;
}

export default function SleepPage() {
  const router = useRouter();
  const [data, setData] = useState<SleepData | null>(null);
  const [consistency, setConsistency] = useState<SleepConsistencyScore | null>(null);
  const [stress, setStress] = useState<SleepStressHistory | null>(null);
  const [stageHistory, setStageHistory] = useState<SleepStageRangeHistory | null>(null);
  const [stageRangesLoading, setStageRangesLoading] = useState(true);
  const [stageRangesError, setStageRangesError] = useState(false);
  const [selectedStage, setSelectedStage] = useState<SleepStage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSleep()
      .then(setData)
      .finally(() => setLoading(false));
    api.getSleepConsistencyScore().then(setConsistency).catch(() => setConsistency(null));
    api.getSleepStress('W').then(setStress).catch(() => setStress(null));
    api.getSleepStageRanges().then(setStageHistory)
      .catch(() => setStageRangesError(true)).finally(() => setStageRangesLoading(false));
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
  const latestStress = stress?.nights.filter((night) => night.main_sleep && night.status === 'ok')
    .sort((left, right) => left.night_date.localeCompare(right.night_date)).slice(-1)[0];
  const sleepStressPct = latestStress?.stress_pct == null ? null : Math.round(latestStress.stress_pct);

  // Circular gauge calculations
  const dialSize = 220;
  const strokeWidth = 11;
  const radius = (dialSize - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(1, Math.max(0, sleepScore / 100));
  const dashOffset = circumference * (1 - pct);
  const center = dialSize / 2;

  // Use the latest record, including unavailable/pending nights, rather than an older scored night.
  const stageNight = stageHistory?.nights.slice().sort((a, b) => a.night_date.localeCompare(b.night_date)).slice(-1)[0];
  const stageReadings = stageNight?.stages;
  const stageRangeNote = stageRangesLoading ? 'Loading typical range…'
    : stageRangesError ? 'Typical range unavailable'
    : !stageNight ? 'No recent sleep-stage data'
    : stageNight.status === 'building_baseline'
      ? `Building baseline · ${stageNight.nights_available} of ${stageNight.config_snapshot?.min_nights ?? 4} nights`
    : stageNight.status === 'stages_pending' ? 'Sleep stages are still processing'
    : stageNight.status !== 'ok' ? 'Stage breakdown not available for this night'
    : `Based on ${stageNight.nights_used} nights · Provisional`;
  const restorative = stageReadings?.restorative;
  const stageSelection = (stage: SleepStage) => {
    const available = stageReadings?.[stage]?.pct != null;
    const toggle = () => { if (available) setSelectedStage(current => current === stage ? null : stage); };
    return { role: 'button', tabIndex: available ? 0 : -1, 'aria-disabled': !available,
      'aria-pressed': selectedStage === stage, 'aria-controls': 'sleep-heart-rate-chart',
      onClick: toggle, onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); }
      } };
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
              {sleepStressPct !== null && <SegmentIndicator value={sleepStressPct} isInverse />}
              <span className={styles.metricValue}>{sleepStressPct === null ? '—' : `${sleepStressPct}%`}</span>
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
            <SleepHeartRateChart night={stageNight} waiting={stageRangesLoading} selectedStage={selectedStage} />

            {/* Typical Range & Duration Header */}
            <div className={styles.typicalRangeHeader}>
              <div className={styles.typicalRangeTitle}>
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" className={styles.typicalRangeSvg}>
                  <line x1="0" y1="8" x2="3" y2="8" stroke="#8E95A2" strokeWidth="1.5" />
                  <line x1="13" y1="8" x2="16" y2="8" stroke="#8E95A2" strokeWidth="1.5" />
                  <rect x="3" y="2" width="10" height="12" rx="2" stroke="rgba(255, 255, 255, 0.75)" strokeWidth="1.2" strokeDasharray="2 2" fill="none" />
                </svg>
                <span>TYPICAL RANGE{stageHistory?.is_mock ? ' · DEMO' : ''}</span>
              </div>
              <div className={styles.durationBlock}>
                <span className={styles.durationLabel}>DURATION</span>
                <span className={styles.durationValue}>{stageDuration(stageNight?.total_minutes)}</span>
              </div>
            </div>
            <div className={styles.stageRangeNote}>
              {stageNight && <span>{stageNight.night_date} · </span>}{stageRangeNote}
            </div>

            {/* Stage percentages and dashed personal ranges share the same backend denominator. */}
            <div className={styles.stagesList}>
              {/* AWAKE */}
              <div className={styles.stageItem} {...stageSelection('awake')}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>AWAKE</span>
                    <span className={styles.stagePctMuted}>{stageReadings?.awake?.pct == null ? '—' : `${Math.round(stageReadings.awake.pct)}%`}</span>
                  </div>
                  <span className={styles.stageDurationVal}>{stageDuration(stageReadings?.awake?.minutes)}</span>
                </div>
                <div className={styles.stageTrackWrapper} title={rangeDescription(stageReadings?.awake)}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: `${stageReadings?.awake?.pct ?? 0}%`, background: '#E2E6EE' }} />
                  </div>
                  <TypicalRangeMarker metric={stageReadings?.awake} />
                </div>
              </div>

              {/* LIGHT */}
              <div className={styles.stageItem} {...stageSelection('light')}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>LIGHT</span>
                    <span className={styles.stagePctLavender}>{stageReadings?.light?.pct == null ? '—' : `${Math.round(stageReadings.light.pct)}%`}</span>
                  </div>
                  <span className={styles.stageDurationVal}>{stageDuration(stageReadings?.light?.minutes)}</span>
                </div>
                <div className={styles.stageTrackWrapper} title={rangeDescription(stageReadings?.light)}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: `${stageReadings?.light?.pct ?? 0}%`, background: '#9B8AFB' }} />
                  </div>
                  <TypicalRangeMarker metric={stageReadings?.light} />
                </div>
              </div>

              {/* SWS (DEEP) */}
              <div className={styles.stageItem} {...stageSelection('deep')}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>SWS (DEEP)</span>
                    <span className={styles.stagePctPink}>{stageReadings?.deep?.pct == null ? '—' : `${Math.round(stageReadings.deep.pct)}%`}</span>
                  </div>
                  <span className={styles.stageDurationVal}>{stageDuration(stageReadings?.deep?.minutes)}</span>
                </div>
                <div className={styles.stageTrackWrapper} title={rangeDescription(stageReadings?.deep)}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: `${stageReadings?.deep?.pct ?? 0}%`, background: '#FF5CD1' }} />
                  </div>
                  <TypicalRangeMarker metric={stageReadings?.deep} />
                </div>
              </div>

              {/* REM */}
              <div className={styles.stageItem} {...stageSelection('rem')}>
                <div className={styles.stageTopRow}>
                  <div className={styles.stageNameGroup}>
                    <span className={styles.stageCircleIcon} style={{ borderColor: '#8E95A2' }} />
                    <span className={styles.stageName}>REM</span>
                    <span className={styles.stagePctPurple}>{stageReadings?.rem?.pct == null ? '—' : `${Math.round(stageReadings.rem.pct)}%`}</span>
                  </div>
                  <span className={styles.stageDurationVal}>{stageDuration(stageReadings?.rem?.minutes)}</span>
                </div>
                <div className={styles.stageTrackWrapper} title={rangeDescription(stageReadings?.rem)}>
                  <div className={styles.stageTrackBar}>
                    <div className={styles.stageFill} style={{ width: `${stageReadings?.rem?.pct ?? 0}%`, background: '#B040FF' }} />
                  </div>
                  <TypicalRangeMarker metric={stageReadings?.rem} />
                </div>
              </div>
            </div>


            {/* RESTORATIVE SLEEP Section (Exact WHOOP Image 2) */}
            <div className={styles.restorativeRow}>
              <div className={styles.restorativeLeft}>
                <span className={styles.restorativeDualSquare} />
                <span className={styles.restorativeLabel}>RESTORATIVE SLEEP</span>
              </div>
              <div className={styles.restorativeRight} title={rangeDescription(restorative)}>
                <div className={styles.restorativeValGroup}>
                  <span className={styles.restorativeValue}>{stageDuration(restorative?.minutes)}</span>
                  {restorative?.status && restorative.status !== 'within' &&
                    <span className={styles.restorativeDelta} style={{ color: '#8E95A2' }}>{restorative.status === 'above' ? '▲' : '▼'}</span>}
                </div>
                <span className={styles.restorativeBaseline}>{restorative?.range_minutes
                  ? `${stageDuration(restorative.range_minutes.low)}–${stageDuration(restorative.range_minutes.high)}` : '—'}</span>
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
