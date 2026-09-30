'use client';

/**
 * Trend View — Sleep Consistency (/sleep/consistency)
 * Exact WHOOP app Sleep Consistency Trend screen:
 * - Top header with back button and "TREND VIEW"
 * - Metric dropdown pill with crescent icon: "SLEEP CONSISTENCY"
 * - Summary section with Average %, vs. prior week badge, W / M / 6M toggle, and date navigator
 * - Narrative insight paragraph
 * - 7-day Bar chart with score values, y-axis gridlines, and day/date labels
 * - Sleep Consistency Breakdown progress bar and days counts (Optimal / Sufficient)
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepConsistencyTrend } from '@/lib/types';
import styles from './page.module.css';

export default function SleepConsistencyTrendPage() {
  const router = useRouter();
  const [trend, setTrend] = useState<SleepConsistencyTrend | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<'W' | 'M' | '6M'>('W');

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
          <div style={{ width: 24 }} /> {/* balance spacer */}
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
          {/* Left: Average Score & Delta */}
          <div className={styles.averageBlock}>
            <span className={styles.averageLabel}>AVERAGE</span>
            <div className={styles.scoreRow}>
              <span className={styles.scoreBig}>{Math.round(average_score)}</span>
              <span className={styles.scoreUnit}>%</span>
            </div>
            <div className={styles.deltaPill}>
              <span className={styles.deltaArrow}>▲</span>
              <span>{prior_week_change}% vs. prior week</span>
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

        {/* -- Bar Chart Trend Graph -- */}
        <div className={styles.chartContainer}>
          {/* Y-Axis Gridlines */}
          <div className={styles.gridlinesWrapper}>
            {[100, 75, 50, 25, 0].map((val) => (
              <div key={val} className={styles.gridlineRow}>
                <span className={styles.yAxisLabel}>{val}%</span>
                <div className={styles.gridline} />
              </div>
            ))}
          </div>

          {/* 7 Daily Bars */}
          <div className={styles.barsRow}>
            {days.map((day) => {
              const heightPct = Math.max(8, Math.min(100, day.score));
              return (
                <div key={day.date} className={styles.barCol}>
                  {/* Bar pillar with score resting right on top */}
                  <div className={styles.barTrack}>
                    <div className={styles.barPillarWrapper} style={{ height: `${heightPct}%` }}>
                      <span className={styles.barScoreLabel}>{Math.round(day.score)}%</span>
                      <div className={styles.barFill} />
                    </div>
                  </div>

                  {/* Day name & date under bar */}
                  <div className={styles.barMeta}>
                    <span className={styles.barDayName}>{day.day_name}</span>
                    <span className={styles.barDayNum}>{day.day_num}</span>
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
