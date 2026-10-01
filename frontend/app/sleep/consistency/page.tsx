'use client';

/**
 * Trend View — Sleep Consistency (/sleep/consistency)
 * WHOOP app Sleep Consistency Trend screen with full hover & scrub interactivity:
 * - Top header with back button and "TREND VIEW"
 * - Metric dropdown pill: crescent icon, "SLEEP CONSISTENCY"
 * - Summary section with dynamic Average or Hovered day score
 * - 7-day Bar chart with score values, y-axis gridlines, and day/date labels
 * - Interactive hover on each bar showing score, status, date, and highlighting bar
 * - Interactive hover on AVERAGE pill / line showing 7-day average (85%)
 * - Sleep Consistency Breakdown progress bar and days counts
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepConsistencyTrend, SleepConsistencyDay } from '@/lib/types';
import styles from './page.module.css';

export default function SleepConsistencyTrendPage() {
  const router = useRouter();
  const [trend, setTrend] = useState<SleepConsistencyTrend | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<'W' | 'M' | '6M'>('W');

  // Interactive state
  const [hoveredDay, setHoveredDay] = useState<SleepConsistencyDay | null>(null);
  const [isHoveringAvg, setIsHoveringAvg] = useState(false);

  useEffect(() => {
    api.getSleepConsistencyTrend()
      .then(setTrend)
      .catch((err) => {
        console.error('Failed to load consistency trend', err);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading || !trend) {
    return (
      <div className={styles.pageWrapper}>
        <div className={styles.container}>
          <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 12, marginBottom: 20 }} />
          <div className="skeleton" style={{ width: 140, height: 70, borderRadius: 10, marginBottom: 24 }} />
          <div className="skeleton" style={{ width: '100%', height: 280, borderRadius: 16, marginBottom: 20 }} />
        </div>
      </div>
    );
  }

  const { average_score, prior_week_change, range_label, insight, days, breakdown } = trend;
  const optimalRatio = (breakdown.optimal_days / breakdown.total_days) * 100;

  // Format date helper
  const formatDateFriendly = (dateStr: string) => {
    try {
      const parts = dateStr.split('-');
      const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  // Header display logic
  let displayScore = Math.round(average_score);
  let displayLabel = 'AVERAGE';
  let isDisplayDay = false;

  if (hoveredDay) {
    displayScore = Math.round(hoveredDay.score);
    displayLabel = `${hoveredDay.day_name.toUpperCase()}, ${formatDateFriendly(hoveredDay.date).toUpperCase()}`;
    isDisplayDay = true;
  } else if (isHoveringAvg) {
    displayScore = Math.round(average_score);
    displayLabel = '7-DAY AVERAGE';
  }

  return (
    <div className={styles.pageWrapper}>
      <div className={styles.container}>
        {/* -- Top Navigation Bar -- */}
        <header className={styles.topNav}>
          <button className={styles.navBackBtn} onClick={() => router.push('/sleep')} aria-label="Back">
            <svg width="10" height="16" viewBox="0 0 10 16" fill="none" stroke="#FFFFFF" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8.5 1.5L2 8L8.5 14.5" />
            </svg>
          </button>
          <span className={styles.navTitle}>TREND VIEW</span>
          <div style={{ width: 24 }} />
        </header>

        {/* -- Metric Selector Dropdown Pill -- */}
        <div className={styles.metricSelectorPill}>
          <div className={styles.selectorLeft}>
            <div className={styles.selectorIcon}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3a9 9 0 1 0 9 9" />
                <path d="M19 12.79A7 7 0 1 1 11.21 5" />
              </svg>
            </div>
            <span className={styles.selectorTitle}>SLEEP CONSISTENCY</span>
          </div>
          <svg width="12" height="8" viewBox="0 0 12 8" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="1 1.5 6 6.5 11 1.5" />
          </svg>
        </div>

        {/* -- Summary Header Row -- */}
        <div className={styles.summaryRow}>
          {/* Left: Dynamic Average or Hovered Bar Score */}
          <div className={styles.averageBlock}>
            <span className={`${styles.averageLabel} ${isDisplayDay ? styles.averageLabelActive : ''}`}>
              {displayLabel}
            </span>
            <div className={styles.scoreRow}>
              <span className={styles.scoreBig}>{displayScore}</span>
              <span className={styles.scoreUnit}>%</span>
            </div>
            <div className={styles.deltaPill}>
              {isDisplayDay && hoveredDay ? (
                <>
                  <span className={styles.deltaDotGreen}>●</span>
                  <span>{hoveredDay.status} consistency</span>
                </>
              ) : isHoveringAvg ? (
                <>
                  <span className={styles.deltaDotGreen}>●</span>
                  <span>7-Day rolling mean</span>
                </>
              ) : (
                <>
                  <span className={styles.deltaArrow}>▲</span>
                  <span>{prior_week_change}% vs. prior week</span>
                </>
              )}
            </div>
          </div>

          {/* Right: Timeframe toggle + Date range */}
          <div className={styles.controlsBlock}>
            <div className={styles.timeframeToggle}>
              {(['W', 'M', '6M'] as const).map((t) => (
                <button
                  key={t}
                  className={`${styles.toggleBtn} ${timeframe === t ? styles.toggleActive : ''}`}
                  onClick={() => setTimeframe(t)}
                >
                  {t}
                </button>
              ))}
            </div>

            <div className={styles.dateNavRow}>
              <button className={styles.dateArrowBtn} aria-label="Previous week">
                <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 1.5L1.5 5L5 8.5" />
                </svg>
              </button>
              <span className={styles.dateRangeText}>{range_label}</span>
              <button className={styles.dateArrowBtn} aria-label="Next week">
                <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 1.5L4.5 5L1 8.5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* -- Insight Narrative Text -- */}
        <p className={styles.insightText}>{insight}</p>

        {/* -- Interactive Bar Chart Trend Graph -- */}
        <div className={styles.chartContainer} onMouseLeave={() => setHoveredDay(null)}>
          {/* Y-Axis Gridlines */}
          <div className={styles.gridlinesWrapper}>
            {[100, 75, 50, 25, 0].map((val) => {
              const isAvgLine = val === 75; // Near 85%
              return (
                <div key={val} className={styles.gridlineRow}>
                  {val === 75 ? (
                    <button
                      className={`${styles.avgPill} ${isHoveringAvg ? styles.avgPillActive : ''}`}
                      onMouseEnter={() => { setIsHoveringAvg(true); setHoveredDay(null); }}
                      onMouseLeave={() => setIsHoveringAvg(false)}
                      onClick={() => setIsHoveringAvg(!isHoveringAvg)}
                      title="Hover to view average"
                    >
                      AVG.
                    </button>
                  ) : (
                    <span className={styles.yAxisLabel}>{val}%</span>
                  )}
                  <div className={`${styles.gridline} ${isHoveringAvg && isAvgLine ? styles.gridlineActive : ''}`} />
                </div>
              );
            })}
          </div>

          {/* Average Guideline overlay across bars */}
          <div
            className={`${styles.avgGuidelineOverlay} ${isHoveringAvg ? styles.avgGuidelineActive : ''}`}
            style={{ bottom: `calc(44px + (100% - 44px) * 0.85)` }}
            onMouseEnter={() => { setIsHoveringAvg(true); setHoveredDay(null); }}
            onMouseLeave={() => setIsHoveringAvg(false)}
          >
            {isHoveringAvg && (
              <span className={styles.avgGuidelineLabel}>7-DAY AVG: {Math.round(average_score)}%</span>
            )}
          </div>

          {/* 7 Daily Bars with Hover & Tap Interactivity */}
          <div className={styles.barsRow}>
            {days.map((day) => {
              const heightPct = Math.max(8, Math.min(100, day.score));
              const isBarHovered = hoveredDay?.date === day.date;

              return (
                <div
                  key={day.date}
                  className={`${styles.barCol} ${isBarHovered ? styles.barColActive : ''}`}
                  onMouseEnter={() => { setHoveredDay(day); setIsHoveringAvg(false); }}
                  onClick={() => setHoveredDay(day)}
                >
                  {/* Bar pillar with score resting right on top */}
                  <div className={styles.barTrack}>
                    <div
                      className={`${styles.barPillarWrapper} ${isBarHovered ? styles.barPillarWrapperActive : ''}`}
                      style={{ height: `${heightPct}%` }}
                    >
                      <span className={`${styles.barScoreLabel} ${isBarHovered ? styles.barScoreLabelActive : ''}`}>
                        {Math.round(day.score)}%
                      </span>
                      <div className={`${styles.barFill} ${isBarHovered ? styles.barFillActive : ''}`} />
                    </div>
                  </div>

                  {/* Day name & date under bar */}
                  <div className={styles.barMeta}>
                    <span className={`${styles.barDayName} ${isBarHovered ? styles.barMetaActive : ''}`}>
                      {day.day_name}
                    </span>
                    <span className={`${styles.barDayNum} ${isBarHovered ? styles.barMetaActive : ''}`}>
                      {day.day_num}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* -- Sleep Consistency Breakdown Section -- */}
        <section className={styles.breakdownSection}>
          <div className={styles.breakdownTitleRow}>
            <span className={styles.breakdownTitle}>SLEEP CONSISTENCY BREAKDOWN</span>
            <span className={styles.breakdownUnit}>(DAYS)</span>
          </div>

          {/* Dual-color Segmented Bar */}
          <div className={styles.breakdownProgressBar}>
            <div className={styles.optimalBarSegment} style={{ width: `${optimalRatio}%` }} />
            <div className={styles.sufficientBarSegment} style={{ width: `${100 - optimalRatio}%` }} />
          </div>

          {/* Legend rows */}
          <div className={styles.breakdownLegend}>
            <div className={styles.legendRow}>
              <span className={styles.legendDotOptimal} />
              <span className={styles.legendCount}>{breakdown.optimal_days}x</span>
              <span className={styles.legendDesc}>Optimal (80%+)</span>
            </div>
            <div className={styles.legendRow}>
              <span className={styles.legendDotSufficient} />
              <span className={styles.legendCount}>{breakdown.sufficient_days}x</span>
              <span className={styles.legendDesc}>Sufficient (70-79%)</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
