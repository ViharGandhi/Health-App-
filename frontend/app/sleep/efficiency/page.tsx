'use client';

/**
 * Trend View — Sleep Efficiency (/sleep/efficiency)
 * WHOOP-exact Sleep Efficiency Trend Screen:
 * - Top header with back button and "TREND VIEW"
 * - Dropdown pill: bed + histogram icon, "SLEEP EFFICIENCY", chevron
 * - Summary section:
 *    - AVERAGE 95%
 *    - "• 0% vs. prior month" pill
 *    - Timeframe toggle: W | M | 6M (M active by default)
 *    - Date range navigator: < MAR 17 - APR 15, 26 >
 * - Narrative insight:
 *    "Your average sleep efficiency (95%) this month was consistent with your previous 30-day average of 95%."
 * - High-precision SVG Line & Area chart:
 *    - Y-Axis: 100%, 96%, 92%, 88%, 84% with gridlines
 *    - Dashed horizontal average reference line with "[ AVG. ]" white capsule pill
 *    - Continuous cyan/teal curve with gradient fill
 *    - Open circular marker on last day with "96%" score above it
 *    - X-Axis ticks: Mar 18, Mar 25, Apr 1, Apr 8, Apr 15
 * - SLEEP EFFICIENCY BREAKDOWN (DAYS):
 *    - Bright luminous cyan/mint bar (#00E5A3)
 *    - 30x Optimal (90%+)
 *    - 0x Sufficient (80-89%)
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
  const [timeframe, setTimeframe] = useState<'W' | 'M' | '6M'>('M');

  useEffect(() => {
    setLoading(true);
    api.getSleepEfficiencyTrend(timeframe)
      .then(setTrend)
      .catch((err) => {
        console.error('Failed to load efficiency trend', err);
      })
      .finally(() => setLoading(false));
  }, [timeframe]);

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
    comparison_label = 'vs. prior month',
    range_label,
    insight,
    days,
    breakdown,
  } = trend;

  const totalDays = breakdown.total_days || days.length || 30;
  const optimalRatio = (breakdown.optimal_days / totalDays) * 100;
  const sufficientRatio = (breakdown.sufficient_days / totalDays) * 100;
  const poorRatio = (breakdown.poor_days / totalDays) * 100;

  // Chart coordinate math
  // Y-axis spans from 84% to 100%
  const yMin = 84;
  const yMax = 100;
  const yTicks = [100, 96, 92, 88, 84];

  const svgWidth = 320;
  const svgHeight = 175;
  const chartTop = 15;
  const chartBottom = 160;
  const chartLeft = 0;
  const chartRight = svgWidth;
  const plotWidth = chartRight - chartLeft;
  const plotHeight = chartBottom - chartTop;

  const getYCoord = (val: number) => {
    const clamped = Math.max(yMin, Math.min(yMax, val));
    const ratio = (yMax - clamped) / (yMax - yMin);
    return chartTop + ratio * plotHeight;
  };

  const n = days.length;
  const points = days.map((d, i) => {
    const x = chartLeft + (i / Math.max(1, n - 1)) * plotWidth;
    const y = getYCoord(d.score);
    return { x, y, score: d.score, day: d };
  });

  // SVG path definitions
  const linePathD = points.length > 0
    ? `M ${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ')}`
    : '';

  const areaPathD = points.length > 0
    ? `${linePathD} L ${points[points.length - 1].x.toFixed(1)},${chartBottom} L ${points[0].x.toFixed(1)},${chartBottom} Z`
    : '';

  const avgY = getYCoord(average_score);
  const lastPoint = points[points.length - 1];

  // Specific ticks for X-axis in Month mode
  // Ticks: Mar 18, Mar 25, Apr 1, Apr 8, Apr 15
  const monthTickIndices = timeframe === 'M'
    ? [1, 8, 15, 22, 29]
    : [0, 1, 2, 3, 4, 5, 6];

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
              {/* WHOOP Sleep Efficiency Icon: Bed with 3 vertical bars */}
              <svg width="22" height="18" viewBox="0 0 24 20" fill="none" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <line x1="6" y1="9" x2="6" y2="4" />
                <line x1="12" y1="9" x2="12" y2="2" />
                <line x1="18" y1="9" x2="18" y2="5" />
                <path d="M2 13h20" />
                <path d="M2 17v-6" />
                <path d="M22 17v-4" />
                <path d="M2 13a3 3 0 0 1 3-3h3a3 3 0 0 1 3 3" />
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
              {prior_week_change === 0 ? (
                <>
                  <span className={styles.deltaDot}>•</span>
                  <span>0% {comparison_label}</span>
                </>
              ) : prior_week_change > 0 ? (
                <>
                  <span className={styles.deltaArrowGreen}>▲</span>
                  <span className={styles.deltaTextGreen}>{prior_week_change}% {comparison_label}</span>
                </>
              ) : (
                <>
                  <span className={styles.deltaArrowRed}>▼</span>
                  <span className={styles.deltaTextRed}>{Math.abs(prior_week_change)}% {comparison_label}</span>
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
              <button className={styles.dateArrowBtn} aria-label="Previous range">
                <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 1.5L1.5 5L5 8.5" />
                </svg>
              </button>
              <span className={styles.dateRangeText}>{range_label}</span>
              <button className={styles.dateArrowBtn} aria-label="Next range">
                <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 1.5L4.5 5L1 8.5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* -- Insight Narrative Text -- */}
        <p className={styles.insightText}>{insight}</p>

        {/* -- WHOOP Line & Area Chart Container -- */}
        <div className={styles.chartWrapper}>
          {/* Y-Axis Column */}
          <div className={styles.yAxisCol}>
            {yTicks.map((val) => {
              const isAvgVal = val === 96; // near average 95
              return (
                <div key={val} className={styles.yTickItem}>
                  {isAvgVal ? (
                    <div className={styles.avgPill}>AVG.</div>
                  ) : (
                    <span className={styles.yTickLabel}>{val}%</span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Graph Body */}
          <div className={styles.graphBody}>
            {/* Background Gridlines */}
            <div className={styles.gridlinesBody}>
              {yTicks.map((val) => (
                <div key={val} className={styles.gridlineRow} />
              ))}
            </div>

            {/* SVG Plot */}
            <svg
              className={styles.svgPlot}
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient id="efficiencyGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#62A4B7" stopOpacity="0.22" />
                  <stop offset="100%" stopColor="#62A4B7" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Dashed Average Line across chart */}
              <line
                x1={0}
                y1={avgY}
                x2={svgWidth}
                y2={avgY}
                stroke="#8E95A2"
                strokeWidth="1.2"
                strokeDasharray="4 4"
                opacity="0.55"
              />

              {/* Subtle Gradient Area Fill Under Curve */}
              {areaPathD && (
                <path d={areaPathD} fill="url(#efficiencyGradient)" />
              )}

              {/* Cyan / Teal Line */}
              {linePathD && (
                <path
                  d={linePathD}
                  fill="none"
                  stroke="#62A4B7"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {/* Open Circular Marker on latest day */}
              {lastPoint && (
                <circle
                  cx={lastPoint.x}
                  cy={lastPoint.y}
                  r="4"
                  fill="#0E1217"
                  stroke="#FFFFFF"
                  strokeWidth="2.4"
                />
              )}
            </svg>

            {/* Floating 96% score directly above last point */}
            {lastPoint && (
              <span
                className={styles.endpointLabel}
                style={{
                  left: `${(lastPoint.x / svgWidth) * 100}%`,
                  top: `${(lastPoint.y / svgHeight) * 100}%`,
                }}
              >
                {Math.round(lastPoint.score)}%
              </span>
            )}
          </div>
        </div>

        {/* -- X-Axis Dates Row -- */}
        <div className={styles.xAxisRow}>
          {monthTickIndices.map((idx) => {
            const pt = points[idx];
            if (!pt) return null;
            const d = pt.day;
            const pct = (pt.x / svgWidth) * 100;
            return (
              <div
                key={d.date}
                className={styles.xTickItem}
                style={{ left: `${pct}%` }}
              >
                <span className={styles.xTickMonth}>{d.date.slice(5, 7) === '03' ? 'Mar' : 'Apr'}</span>
                <span className={styles.xTickDay}>{d.day_num}</span>
              </div>
            );
          })}
        </div>

        {/* -- Sleep Efficiency Breakdown Section -- */}
        <section className={styles.breakdownSection}>
          <div className={styles.breakdownTitleRow}>
            <span className={styles.breakdownTitle}>SLEEP EFFICIENCY BREAKDOWN</span>
            <span className={styles.breakdownUnit}>(DAYS)</span>
          </div>

          {/* Single/Dual Segmented Bar (100% luminous cyan in WHOOP screenshot) */}
          <div className={styles.breakdownProgressBar}>
            <div className={styles.optimalBarSegment} style={{ width: `${optimalRatio}%` }} />
            {sufficientRatio > 0 && (
              <div className={styles.sufficientBarSegment} style={{ width: `${sufficientRatio}%` }} />
            )}
            {poorRatio > 0 && (
              <div className={styles.poorBarSegment} style={{ width: `${poorRatio}%` }} />
            )}
          </div>

          {/* Legend rows with square dots matching screenshot */}
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
