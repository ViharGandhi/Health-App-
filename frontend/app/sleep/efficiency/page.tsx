'use client';

/**
 * Trend View — Sleep Efficiency (/sleep/efficiency)
 * WHOOP-exact Sleep Efficiency Trend Screen with Full Scrubbing & Hover Interactivity:
 * - Top header with back button and "TREND VIEW"
 * - Dropdown pill: bed + histogram icon, "SLEEP EFFICIENCY", chevron
 * - Summary section:
 *    - Dynamic AVERAGE / HOVERED SCORE
 *    - Interactive delta badge
 *    - Timeframe toggle: W | M | 6M (M active by default)
 *    - Date range navigator: < MAR 17 - APR 15, 26 >
 * - Interactive WHOOP Line & Area chart:
 *    - Hover anywhere to scrub points: shows vertical dotted guide, glowing circle, and floating score tooltip
 *    - Hover over "[ AVG. ]" badge or dashed reference line to highlight average (95%)
 *    - Smooth fallback to latest day / average when unhovered
 *    - Y-Axis: 100%, 96%, 92%, 88%, 84% with gridlines
 *    - X-Axis ticks: Mar 18, Mar 25, Apr 1, Apr 8, Apr 15
 * - SLEEP EFFICIENCY BREAKDOWN (DAYS):
 *    - Bright luminous cyan/mint bar (#00E5A3)
 *    - 30x Optimal (90%+)
 *    - 0x Sufficient (80-89%)
 */

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepEfficiencyTrend } from '@/lib/types';
import styles from './page.module.css';

export default function SleepEfficiencyTrendPage() {
  const router = useRouter();
  const [trend, setTrend] = useState<SleepEfficiencyTrend | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<'W' | 'M' | '6M'>('M');
  
  // Interactive state
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [isHoveringAvg, setIsHoveringAvg] = useState(false);
  const graphRef = useRef<HTMLDivElement | null>(null);

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
    return { x, y, score: d.score, day: d, index: i };
  });

  // SVG path definitions
  const linePathD = points.length > 0
    ? `M ${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ')}`
    : '';

  const areaPathD = points.length > 0
    ? `${linePathD} L ${points[points.length - 1].x.toFixed(1)},${chartBottom} L ${points[0].x.toFixed(1)},${chartBottom} Z`
    : '';

  const avgY = getYCoord(average_score);
  const defaultIndex = points.length - 1;
  const activePoint = hoveredIndex !== null ? points[hoveredIndex] : points[defaultIndex];

  // Specific ticks for X-axis in Month mode
  const monthTickIndices = timeframe === 'M'
    ? [1, 8, 15, 22, 29]
    : [0, 1, 2, 3, 4, 5, 6];

  // Mouse & Touch Scrubbing handlers
  const handlePointerMove = (clientX: number) => {
    if (!graphRef.current) return;
    const rect = graphRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, x / rect.width));
    const idx = Math.round(ratio * (points.length - 1));
    setHoveredIndex(idx);
    setIsHoveringAvg(false);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    handlePointerMove(e.clientX);
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    if (e.touches[0]) {
      handlePointerMove(e.touches[0].clientX);
    }
  };

  const handlePointerLeave = () => {
    setHoveredIndex(null);
  };

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

  // Compute what to show in the big score display
  let displayScore = Math.round(average_score);
  let displayLabel = 'AVERAGE';
  let isDisplayDay = false;

  if (hoveredIndex !== null && activePoint) {
    displayScore = Math.round(activePoint.score);
    displayLabel = `${activePoint.day.day_name.toUpperCase()}, ${formatDateFriendly(activePoint.day.date).toUpperCase()}`;
    isDisplayDay = true;
  } else if (isHoveringAvg) {
    displayScore = Math.round(average_score);
    displayLabel = '30-DAY AVERAGE';
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
          {/* Left: Dynamic Average or Hovered Score */}
          <div className={styles.averageBlock}>
            <span className={`${styles.averageLabel} ${isDisplayDay ? styles.averageLabelActive : ''}`}>
              {displayLabel}
            </span>
            <div className={styles.scoreRow}>
              <span className={styles.scoreBig}>{displayScore}</span>
              <span className={styles.scoreUnit}>%</span>
            </div>

            {/* Delta pill or Day status pill */}
            <div className={styles.deltaPill}>
              {isDisplayDay && activePoint ? (
                <>
                  <span className={styles.deltaDotGreen}>●</span>
                  <span>{activePoint.day.status} • {activePoint.day.asleep_hours}h asleep</span>
                </>
              ) : isHoveringAvg ? (
                <>
                  <span className={styles.deltaDotGreen}>●</span>
                  <span>Average across {totalDays} days</span>
                </>
              ) : prior_week_change === 0 ? (
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

        {/* -- WHOOP Interactive Line & Area Chart Container -- */}
        <div className={styles.chartWrapper}>
          {/* Y-Axis Column */}
          <div className={styles.yAxisCol}>
            {yTicks.map((val) => {
              const isAvgVal = val === 96; // Position near 95%
              return (
                <div key={val} className={styles.yTickItem}>
                  {isAvgVal ? (
                    <button
                      className={`${styles.avgPill} ${isHoveringAvg ? styles.avgPillActive : ''}`}
                      onMouseEnter={() => { setIsHoveringAvg(true); setHoveredIndex(null); }}
                      onMouseLeave={() => setIsHoveringAvg(false)}
                      onClick={() => setIsHoveringAvg(!isHoveringAvg)}
                      title="Hover to view average line"
                    >
                      AVG.
                    </button>
                  ) : (
                    <span className={styles.yTickLabel}>{val}%</span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Graph Body with Full Mouse & Touch Scrubbing */}
          <div
            ref={graphRef}
            className={styles.graphBody}
            onMouseMove={handleMouseMove}
            onTouchMove={handleTouchMove}
            onMouseLeave={handlePointerLeave}
          >
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
                  <stop offset="0%" stopColor="#62A4B7" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#62A4B7" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Dashed Average Line across chart */}
              <line
                x1={0}
                y1={avgY}
                x2={svgWidth}
                y2={avgY}
                stroke={isHoveringAvg ? '#00E5A3' : '#8E95A2'}
                strokeWidth={isHoveringAvg ? 2 : 1.2}
                strokeDasharray={isHoveringAvg ? '6 4' : '4 4'}
                opacity={isHoveringAvg ? 1.0 : 0.55}
                style={{ transition: 'stroke 0.2s ease, opacity 0.2s ease' }}
              />

              {/* Invisible wide line for easy hover on average */}
              <line
                x1={0}
                y1={avgY}
                x2={svgWidth}
                y2={avgY}
                stroke="transparent"
                strokeWidth={16}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => { setIsHoveringAvg(true); setHoveredIndex(null); }}
                onMouseLeave={() => setIsHoveringAvg(false)}
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

              {/* Vertical Guide Line on Hovered Point */}
              {hoveredIndex !== null && activePoint && (
                <line
                  x1={activePoint.x}
                  y1={chartTop}
                  x2={activePoint.x}
                  y2={chartBottom}
                  stroke="rgba(255, 255, 255, 0.45)"
                  strokeWidth="1.2"
                  strokeDasharray="3 3"
                />
              )}

              {/* Active Marker Point (snaps to hovered point or defaults to last point) */}
              {activePoint && (
                <g>
                  {/* Outer pulse when hovered */}
                  {hoveredIndex !== null && (
                    <circle
                      cx={activePoint.x}
                      cy={activePoint.y}
                      r="8"
                      fill="none"
                      stroke="#00E5A3"
                      strokeWidth="1.5"
                      opacity="0.6"
                    />
                  )}
                  {/* Core marker */}
                  <circle
                    cx={activePoint.x}
                    cy={activePoint.y}
                    r="4.2"
                    fill="#0E1217"
                    stroke={hoveredIndex !== null ? '#00E5A3' : '#FFFFFF'}
                    strokeWidth="2.4"
                    style={{ transition: 'cx 0.05s ease, cy 0.05s ease' }}
                  />
                </g>
              )}
            </svg>

            {/* Hover Tooltip / Score Badge */}
            {activePoint && (
              <div
                className={`${styles.scrubTooltip} ${hoveredIndex !== null ? styles.scrubTooltipActive : ''}`}
                style={{
                  left: `${(activePoint.x / svgWidth) * 100}%`,
                  top: `${(activePoint.y / svgHeight) * 100}%`,
                }}
              >
                <span className={styles.scrubScore}>{Math.round(activePoint.score)}%</span>
                {hoveredIndex !== null && (
                  <span className={styles.scrubDate}>
                    {formatDateFriendly(activePoint.day.date)}
                  </span>
                )}
              </div>
            )}

            {/* Hover Tooltip for Average Line */}
            {isHoveringAvg && (
              <div
                className={styles.avgFloatingTooltip}
                style={{ top: `${(avgY / svgHeight) * 100}%` }}
              >
                <span>30-DAY AVG: <strong>{Math.round(average_score)}%</strong></span>
              </div>
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
            const isHighlighted = hoveredIndex !== null && Math.abs(hoveredIndex - idx) <= 1;

            return (
              <div
                key={d.date}
                className={`${styles.xTickItem} ${isHighlighted ? styles.xTickHighlighted : ''}`}
                style={{ left: `${pct}%` }}
                onClick={() => setHoveredIndex(idx)}
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

          {/* Segmented Bar (100% luminous cyan in WHOOP screenshot) */}
          <div className={styles.breakdownProgressBar}>
            <div className={styles.optimalBarSegment} style={{ width: `${optimalRatio}%` }} />
            {sufficientRatio > 0 && (
              <div className={styles.sufficientBarSegment} style={{ width: `${sufficientRatio}%` }} />
            )}
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
