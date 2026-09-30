'use client';

/**
 * Trend View — Sleep Efficiency (/sleep/efficiency)
 * WHOOP app Sleep Efficiency Trend screen:
 * - Top header with back button and "TREND VIEW"
 * - Metric dropdown pill with efficiency icon: "SLEEP EFFICIENCY"
 * - Summary section with Average %, vs. prior week badge, W / M / 6M toggle, and date navigator
 * - Narrative insight paragraph
 * - 7-day Bar chart with score values hugging tops of bars, y-axis gridlines, and day/date labels
 * - Sleep Efficiency Breakdown segmented bar and days counts (Optimal / Sufficient / Poor)
 * - Average Asleep / In Bed / Awake stats row
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepEfficiencyTrend } from '@/lib/types';
import styles from './page.module.css';

export default function SleepEfficiencyTrendPage() {
  const router = useRouter();
  const [trend, setTrend] = useState<SleepEfficiencyTrend | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<'W' | 'M' | '6M'>('W');

  useEffect(() => {
    api.getSleepEfficiencyTrend()
      .then(setTrend)
      .catch((err) => {
        console.error('Failed to load efficiency trend', err);
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

  const {
    average_score,
    prior_week_change,
    range_label,
    insight,
    days,
    breakdown,
    average_time_asleep_hours,
    average_time_in_bed_hours,
    average_awake_minutes,
  } = trend;

  const totalDays = breakdown.total_days || 7;
  const optimalRatio = (breakdown.optimal_days / totalDays) * 100;
  const sufficientRatio = (breakdown.sufficient_days / totalDays) * 100;
  const poorRatio = (breakdown.poor_days / totalDays) * 100;

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
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>
            <span className={styles.selectorTitle}>SLEEP EFFICIENCY</span>
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
              <span className={styles.deltaArrow}>{prior_week_change >= 0 ? '▲' : '▼'}</span>
              <span>{Math.abs(prior_week_change)}% vs. prior week</span>
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

        {/* -- Duration Breakdown Metrics Cards -- */}
        <div className={styles.statsCardsRow}>
          <div className={styles.statCard}>
            <span className={styles.statLabel}>AVG ASLEEP</span>
            <span className={styles.statValue}>{average_time_asleep_hours.toFixed(1)} <span className={styles.statUnit}>hrs</span></span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statLabel}>AVG IN BED</span>
            <span className={styles.statValue}>{average_time_in_bed_hours.toFixed(1)} <span className={styles.statUnit}>hrs</span></span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statLabel}>AVG AWAKE</span>
            <span className={styles.statValue}>{Math.round(average_awake_minutes)} <span className={styles.statUnit}>min</span></span>
          </div>
        </div>

        {/* -- Sleep Efficiency Breakdown Section -- */}
        <section className={styles.breakdownSection}>
          <div className={styles.breakdownTitleRow}>
            <span className={styles.breakdownTitle}>SLEEP EFFICIENCY BREAKDOWN</span>
            <span className={styles.breakdownUnit}>(DAYS)</span>
          </div>

          {/* Segmented Bar */}
          <div className={styles.breakdownProgressBar}>
            <div className={styles.optimalBarSegment} style={{ width: `${optimalRatio}%` }} />
            <div className={styles.sufficientBarSegment} style={{ width: `${sufficientRatio}%` }} />
            {poorRatio > 0 && (
              <div className={styles.poorBarSegment} style={{ width: `${poorRatio}%` }} />
            )}
          </div>

          {/* Legend rows */}
          <div className={styles.breakdownLegend}>
            <div className={styles.legendRow}>
              <span className={styles.legendDotOptimal} />
              <span className={styles.legendCount}>{breakdown.optimal_days}x</span>
              <span className={styles.legendDesc}>Optimal (90%+)</span>
            </div>
            <div className={styles.legendRow}>
              <span className={styles.legendDotSufficient} />
              <span className={styles.legendCount}>{breakdown.sufficient_days}x</span>
              <span className={styles.legendDesc}>Sufficient (80-89%)</span>
            </div>
            {breakdown.poor_days > 0 && (
              <div className={styles.legendRow}>
                <span className={styles.legendDotPoor} />
                <span className={styles.legendCount}>{breakdown.poor_days}x</span>
                <span className={styles.legendDesc}>Poor (&lt;80%)</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
