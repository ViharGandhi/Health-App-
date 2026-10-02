'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { SleepTrend } from '@/lib/types';
import styles from './SleepTrendView.module.css';

type Timeframe = 'W' | 'M' | '6M';
type Metric = 'efficiency' | 'consistency';

function formatDateRange(start: string, end: string): string {
  const s = new Date(`${start}T12:00:00`);
  const e = new Date(`${end}T12:00:00`);
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  const year = e.getFullYear().toString().slice(2);
  return `${s.toLocaleDateString('en-US', opts).toUpperCase()} - ${e.toLocaleDateString('en-US', opts).toUpperCase()}, ${year}`;
}

interface XTick {
  index: number;
  top: string;
  bottom: string;
}

function getXTicks(days: { date: string }[], timeframe: Timeframe): XTick[] {
  if (!days.length) return [];

  if (timeframe === 'W') {
    // Show all 7 days with weekday and date
    return days.map((d, i) => {
      const dt = new Date(`${d.date}T12:00:00`);
      return {
        index: i,
        top: dt.toLocaleDateString('en-US', { weekday: 'short' }),
        bottom: String(dt.getDate()),
      };
    });
  }

  if (timeframe === 'M') {
    // Exactly 5 ticks across 30 days like reference UI (e.g. Mar 18, Mar 25, Apr 1, Apr 8, Apr 15)
    const tickIndices = [0, 7, 14, 21, days.length - 1];
    return tickIndices.map((i) => {
      const idx = Math.min(i, days.length - 1);
      const dt = new Date(`${days[idx].date}T12:00:00`);
      return {
        index: idx,
        top: dt.toLocaleDateString('en-US', { month: 'short' }),
        bottom: String(dt.getDate()),
      };
    });
  }

  // 6M: 5 ticks
  const count = 5;
  return Array.from({ length: count }, (_, k) => {
    const idx = Math.round((k / (count - 1)) * (days.length - 1));
    const dt = new Date(`${days[idx].date}T12:00:00`);
    return {
      index: idx,
      top: dt.toLocaleDateString('en-US', { month: 'short' }),
      bottom: String(dt.getDate()),
    };
  });
}

function TrendChart({
  trend,
  metric,
  timeframe,
  hoveredIndex,
  onHover,
  isHoveringAvg,
  onHoverAvg,
}: {
  trend: SleepTrend;
  metric: Metric;
  timeframe: Timeframe;
  hoveredIndex: number | null;
  onHover: (i: number | null) => void;
  isHoveringAvg: boolean;
  onHoverAvg: (v: boolean) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  const values = trend.days.map((d) => d.value).filter((v): v is number => v !== null);
  if (!values.length) {
    return <div className={styles.emptyChart}>No complete measurements in this range.</div>;
  }

  const average = trend.average_value ?? values.reduce((a, b) => a + b, 0) / values.length;
  const unit = metric === 'efficiency' ? '%' : 'min';

  const rawMin = Math.min(...values, average);
  const rawMax = Math.max(...values, average);

  // Exact WHOOP Y-axis scaling (84, 88, 92, 96, 100)
  let yMin = 84;
  let yMax = 100;
  let tickStep = 4;

  if (metric === 'efficiency') {
    if (rawMin < 84) {
      yMin = Math.max(0, Math.floor((rawMin - 2) / 4) * 4);
    }
    if (rawMax > 100) {
      yMax = Math.ceil(rawMax / 4) * 4;
    }
  } else {
    yMin = Math.max(0, Math.floor((rawMin - 10) / 10) * 10);
    yMax = Math.ceil((rawMax + 10) / 10) * 10;
    tickStep = Math.max(5, Math.round((yMax - yMin) / 4));
  }

  const tickCount = Math.round((yMax - yMin) / tickStep) + 1;
  const yTicks = Array.from({ length: tickCount }, (_, k) => yMin + k * tickStep);

  const W = 360;
  const H = 195;
  const GUTTER_LEFT = 42;  // where AVG badge ends and grid lines start
  const PLOT_LEFT = 54;    // where data points begin (leaving clear gap from AVG badge)
  const PLOT_RIGHT = 348;  // where data points end
  const TOP = 16;
  const BOTTOM = 32;
  const cH = H - TOP - BOTTOM;
  const cW = PLOT_RIGHT - PLOT_LEFT;

  const toX = (i: number) => PLOT_LEFT + (i / Math.max(1, trend.days.length - 1)) * cW;
  const toY = (v: number) => TOP + cH - ((v - yMin) / Math.max(1, yMax - yMin)) * cH;
  const avgY = toY(average);

  const segments: { index: number; value: number }[][] = [];
  trend.days.forEach((day, i) => {
    if (day.value === null) return;
    if (i === 0 || trend.days[i - 1].value === null) segments.push([]);
    segments[segments.length - 1].push({ index: i, value: day.value });
  });

  const days = trend.days;
  const xTicks = getXTicks(days, timeframe);

  const hoveredDay = hoveredIndex !== null ? trend.days[hoveredIndex] : null;
  const hx = hoveredIndex !== null ? toX(hoveredIndex) : null;
  const hy = hoveredDay?.value != null ? toY(hoveredDay.value) : null;

  const lastRealIdx = trend.days.reduce((acc, d, i) => (d.value != null ? i : acc), -1);
  const lastReal = lastRealIdx >= 0 ? trend.days[lastRealIdx] : null;
  const lastRealX = lastRealIdx >= 0 ? toX(lastRealIdx) : null;
  const lastRealY = lastReal?.value != null ? toY(lastReal.value) : null;

  const tooltipX = hx != null ? Math.min(Math.max(hx, PLOT_LEFT + 20), PLOT_RIGHT - 20) : null;

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const xPos = e.clientX - rect.left;
    const frac = (xPos - (PLOT_LEFT / W) * rect.width) / ((cW / W) * rect.width);
    const clampedIdx = Math.min(days.length - 1, Math.max(0, Math.round(frac * (days.length - 1))));
    onHover(clampedIdx);
  }

  return (
    <div className={styles.chartWrap}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className={styles.chartSvg}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => onHover(null)}
        onTouchMove={(e) => {
          const t = e.touches[0];
          const rect = e.currentTarget.getBoundingClientRect();
          const xPos = t.clientX - rect.left;
          const frac = (xPos - (PLOT_LEFT / W) * rect.width) / ((cW / W) * rect.width);
          onHover(Math.min(days.length - 1, Math.max(0, Math.round(frac * (days.length - 1)))));
        }}
        onTouchEnd={() => onHover(null)}
        role="img"
        aria-label={`${metric} trend chart`}
      >
        <defs>
          <linearGradient id={`grad-${metric}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#4a7596" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#4a7596" stopOpacity="0.0" />
          </linearGradient>
          <clipPath id={`clip-${metric}`}>
            <rect x={PLOT_LEFT - 4} y={TOP - 10} width={cW + 8} height={cH + 20} />
          </clipPath>
          <filter id="avgGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* 1. Y-axis ticks and horizontal grid lines */}
        {yTicks.map((tick) => {
          const y = toY(tick);
          const collidesWithAvg = Math.abs(y - avgY) < 7.5;
          return (
            <g key={tick}>
              <line
                x1={GUTTER_LEFT + 2}
                x2={PLOT_RIGHT}
                y1={y}
                y2={y}
                stroke="#1e222a"
                strokeWidth="1"
              />
              {!collidesWithAvg && (
                <text
                  x={GUTTER_LEFT - 3}
                  y={y + 3.5}
                  fill="#565d6c"
                  fontSize="9.5"
                  fontWeight="500"
                  textAnchor="end"
                  fontFamily="var(--font-display)"
                >
                  {metric === 'efficiency' ? `${tick}%` : tick}
                </text>
              )}
            </g>
          );
        })}

        {/* 2. Area fill + Data Line */}
        <g clipPath={`url(#clip-${metric})`}>
          {segments.map((seg, si) => {
            const linePath = seg
              .map((pt, pi) => `${pi === 0 ? 'M' : 'L'} ${toX(pt.index)} ${toY(pt.value)}`)
              .join(' ');
            const areaPath = `${linePath} L ${toX(seg[seg.length - 1].index)} ${TOP + cH} L ${toX(seg[0].index)} ${TOP + cH} Z`;
            return (
              <g key={si}>
                <path d={areaPath} fill={`url(#grad-${metric})`} />
                <path
                  d={linePath}
                  fill="none"
                  stroke="#4a7596"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            );
          })}
        </g>

        {/* 3. Dashed average line spanning from AVG badge to right edge */}
        <line
          x1={GUTTER_LEFT - 2}
          x2={PLOT_RIGHT}
          y1={avgY}
          y2={avgY}
          stroke={isHoveringAvg ? '#FFFFFF' : 'rgba(255, 255, 255, 0.45)'}
          strokeWidth={isHoveringAvg ? 2 : 1.2}
          strokeDasharray="4 4"
          filter={isHoveringAvg ? 'url(#avgGlow)' : undefined}
          style={{ transition: 'stroke 0.15s, stroke-width 0.15s' }}
        />

        {/* 4. Invisible wider hit zone for hovering over average line */}
        <line
          x1={4}
          x2={PLOT_RIGHT}
          y1={avgY}
          y2={avgY}
          stroke="transparent"
          strokeWidth="18"
          style={{ cursor: 'pointer' }}
          onMouseEnter={() => onHoverAvg(true)}
          onMouseLeave={() => onHoverAvg(false)}
        />

        {/* 5. AVG. white pill badge in left column (never collides with data line) */}
        <g
          style={{ cursor: 'pointer' }}
          onMouseEnter={() => onHoverAvg(true)}
          onMouseLeave={() => onHoverAvg(false)}
        >
          <rect
            x={4}
            y={avgY - 8}
            width={36}
            height={16}
            rx={4}
            fill="#FFFFFF"
            stroke={isHoveringAvg ? '#00E676' : 'none'}
            strokeWidth="1.2"
            style={{ transition: 'stroke 0.15s' }}
          />
          <text
            x={22}
            y={avgY + 3.5}
            fill="#111317"
            fontSize="8.5"
            fontWeight="800"
            letterSpacing="0.4"
            textAnchor="middle"
            fontFamily="var(--font-display)"
          >
            AVG.
          </text>
        </g>

        {/* 6. Last-point dot + value label (shown when not hovering) */}
        {lastRealX != null && lastRealY != null && lastReal?.value != null && hoveredIndex === null && (
          <g>
            <circle
              cx={lastRealX}
              cy={lastRealY}
              r="4"
              fill="#121418"
              stroke="#588cae"
              strokeWidth="2"
            />
            <text
              x={lastRealX}
              y={lastRealY - 7}
              fill="#8fb7ca"
              fontSize="10.5"
              fontWeight="700"
              textAnchor="middle"
              fontFamily="var(--font-display)"
            >
              {Math.round(lastReal.value)}{unit}
            </text>
          </g>
        )}

        {/* 7. Hover crosshair + dot + value label on graph */}
        {hx != null && hy != null && hoveredDay?.value != null && (
          <g>
            <line
              x1={hx}
              x2={hx}
              y1={TOP}
              y2={TOP + cH}
              stroke="rgba(255,255,255,0.22)"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            <circle
              cx={hx}
              cy={hy}
              r="5"
              fill="#121418"
              stroke="#588cae"
              strokeWidth="2.5"
            />
            {tooltipX != null && (
              <g>
                <rect
                  x={tooltipX - 22}
                  y={Math.max(TOP + 2, hy - 25)}
                  width={44}
                  height={18}
                  rx={4}
                  fill="#1c2026"
                  stroke="rgba(255,255,255,0.2)"
                  strokeWidth="0.8"
                />
                <text
                  x={tooltipX}
                  y={Math.max(TOP + 2, hy - 25) + 12.5}
                  fill="#FFFFFF"
                  fontSize="10"
                  fontWeight="700"
                  textAnchor="middle"
                  fontFamily="var(--font-display)"
                >
                  {Math.round(hoveredDay.value)}{unit}
                </text>
              </g>
            )}
          </g>
        )}

        {/* 8. X-axis labels (2 lines: Month/Day or Weekday/Date) */}
        {xTicks.map(({ index, top, bottom }) => (
          <g key={index} transform={`translate(${toX(index)}, 0)`}>
            <text
              x="0"
              y={H - 15}
              fill="#565d6c"
              fontSize="9.5"
              fontWeight="500"
              textAnchor="middle"
              fontFamily="var(--font-display)"
            >
              {top}
            </text>
            <text
              x="0"
              y={H - 4}
              fill="#565d6c"
              fontSize="9.5"
              fontWeight="500"
              textAnchor="middle"
              fontFamily="var(--font-display)"
            >
              {bottom}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function BreakdownBar({ trend, metric }: { trend: SleepTrend; metric: Metric }) {
  if (metric !== 'efficiency') return null;
  const days = trend.days.filter((d) => d.value != null);
  const optimal = days.filter((d) => (d.value ?? 0) >= 90).length;
  const sufficient = days.filter((d) => (d.value ?? 0) >= 80 && (d.value ?? 0) < 90).length;
  const poor = days.filter((d) => (d.value ?? 0) < 80).length;
  const total = days.length;
  const optPct = total > 0 ? (optimal / total) * 100 : 0;
  const sufPct = total > 0 ? (sufficient / total) * 100 : 0;
  const poorPct = total > 0 ? (poor / total) * 100 : 0;

  return (
    <div className={styles.breakdown}>
      <div className={styles.breakdownHeader}>
        <span className={styles.breakdownTitle}>SLEEP EFFICIENCY BREAKDOWN</span>
        <span className={styles.breakdownSub}>(DAYS)</span>
      </div>
      <div className={styles.breakdownBar}>
        {optPct > 0 && <div className={styles.barOptimal} style={{ width: `${optPct}%` }} />}
        {sufPct > 0 && <div className={styles.barSufficient} style={{ width: `${sufPct}%` }} />}
        {poorPct > 0 && <div className={styles.barPoor} style={{ width: `${poorPct}%` }} />}
      </div>
      <div className={styles.breakdownLegend}>
        {/* Optimal: Green #00E676 */}
        <div className={styles.legendRow}>
          <span className={`${styles.legendDot} ${styles.dotOptimal}`} />
          <span className={styles.legendCount}>{optimal}x</span>
          <span className={styles.legendLabel}>Optimal (90%+)</span>
        </div>
        {/* Sufficient: Grey #5A606D */}
        <div className={styles.legendRow}>
          <span className={`${styles.legendDot} ${styles.dotSufficient}`} />
          <span className={styles.legendCount}>{sufficient}x</span>
          <span className={styles.legendLabel}>Sufficient (80-89%)</span>
        </div>
        {/* Poor: Yellow/Orange #F59E0B */}
        <div className={styles.legendRow}>
          <span className={`${styles.legendDot} ${styles.dotPoor}`} />
          <span className={styles.legendCount}>{poor}x</span>
          <span className={styles.legendLabel}>Poor (&lt;80%)</span>
        </div>
      </div>
    </div>
  );
}

export default function SleepTrendView({ metric }: { metric: Metric }) {
  // Default to 'M' to match reference UI screenshot
  const [timeframe, setTimeframe] = useState<Timeframe>('M');
  const [trend, setTrend] = useState<SleepTrend | null>(null);
  const [error, setError] = useState(false);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [isHoveringAvg, setIsHoveringAvg] = useState(false);

  useEffect(() => {
    let active = true;
    setTrend(null);
    setError(false);
    setHoveredIndex(null);
    setIsHoveringAvg(false);

    const load = metric === 'efficiency'
      ? api.getSleepEfficiencyTrend(timeframe)
      : api.getSleepConsistencyTrend(timeframe);

    load
      .then((result) => {
        if (active) {
          setTrend(result);
          setError(false);
        }
      })
      .catch(() => {
        if (active) {
          setError(true);
          setTrend(null);
        }
      });

    return () => {
      active = false;
    };
  }, [metric, timeframe]);

  const title = metric === 'efficiency' ? 'SLEEP EFFICIENCY' : 'SLEEP CONSISTENCY';
  const unit = metric === 'efficiency' ? '%' : 'min';

  const hoveredDay = hoveredIndex !== null ? trend?.days[hoveredIndex] : null;
  const displayValue =
    hoveredIndex !== null && hoveredDay?.value != null
      ? hoveredDay.value
      : trend?.average_value;
  const showingHover = hoveredIndex !== null && hoveredDay?.value != null;

  const periodLabel = timeframe === 'W' ? '7-day' : timeframe === 'M' ? '30-day' : '6-month';
  const timeLabel = timeframe === 'W' ? 'week' : timeframe === 'M' ? 'month' : '6 months';
  const vsLabel = timeframe === 'W' ? 'prior week' : timeframe === 'M' ? 'prior month' : 'prior 6M';

  return (
    <div className={styles.viewportContainer}>
      <main className={styles.page}>
        {/* Top Header */}
        <header className={styles.header}>
          <Link href="/sleep" aria-label="Back to sleep" className={styles.backBtn}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </Link>
          <span className={styles.headerTitle}>TREND VIEW</span>
          <div className={styles.headerRight} />
        </header>

        {/* Metric Pill Selector Card */}
        <div className={styles.metricPill}>
          <span className={styles.metricPillIcon}>
            {/* Custom Sleep Efficiency Icon: Bed with 3 bars */}
            <svg width="22" height="18" viewBox="0 0 24 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="5" y="8" width="2" height="5" rx="0.8" fill="#717886" />
              <rect x="9" y="5" width="2" height="8" rx="0.8" fill="#717886" />
              <rect x="13" y="2" width="2" height="11" rx="0.8" fill="#717886" />
              <path d="M2 14H22M2 11V18M22 13V18" stroke="#717886" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              <rect x="4" y="10" width="4" height="3" rx="1" stroke="#717886" strokeWidth="1.2" />
            </svg>
          </span>
          <span className={styles.metricPillLabel}>{title}</span>
          <span className={styles.metricPillChevron}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </div>

        {/* Stats Row & Timeframe Switcher */}
        <div className={styles.statsSection}>
          <div className={styles.statsTopRow}>
            <div className={styles.averageEyebrow}>AVERAGE</div>
            <div className={styles.timeframeTabs} role="group" aria-label="Time range">
              {(['W', 'M', '6M'] as const).map((tf) => (
                <button
                  key={tf}
                  type="button"
                  className={`${styles.tfTab} ${timeframe === tf ? styles.tfActive : ''}`}
                  onClick={() => setTimeframe(tf)}
                  aria-pressed={timeframe === tf}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.statsValueRow}>
            <div className={styles.averageValue}>
              {displayValue != null ? Math.round(displayValue) : '—'}
              <span className={styles.averageUnit}>{unit}</span>
            </div>
          </div>

          <div className={styles.statsBottomRow}>
            <div className={styles.deltaPill}>
              <span className={styles.deltaDot} />
              <span className={styles.deltaText}>
                {isHoveringAvg
                  ? `Average: ${Math.round(trend?.average_value ?? 0)}${unit}`
                  : showingHover && hoveredDay
                  ? `${new Date(`${hoveredDay.date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}: ${Math.round(hoveredDay.value!)}${unit}`
                  : `0% vs. ${vsLabel}`}
              </span>
            </div>

            {trend && (
              <div className={styles.dateNav}>
                <button className={styles.navArrow} aria-label="Previous period">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                </button>
                <span className={styles.dateRange}>
                  {formatDateRange(trend.range_start, trend.range_end)}
                </span>
                <button className={styles.navArrow} aria-label="Next period">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Insight Paragraph */}
        {trend && trend.average_value != null && (
          <p className={styles.insightText}>
            Your average {metric === 'efficiency' ? 'sleep efficiency' : 'sleep consistency'} (
            {Math.round(trend.average_value)}{unit}) this {timeLabel} was consistent with your
            previous {periodLabel} average of {Math.round(trend.average_value)}{unit}.
          </p>
        )}

        {/* Trend Chart (rendered directly on background) */}
        {error ? (
          <div className={styles.message}>Could not load sleep history.</div>
        ) : !trend ? (
          <div className={styles.loading}>Loading sleep history…</div>
        ) : (
          <div className={styles.chartArea}>
            <TrendChart
              trend={trend}
              metric={metric}
              timeframe={timeframe}
              hoveredIndex={hoveredIndex}
              onHover={setHoveredIndex}
              isHoveringAvg={isHoveringAvg}
              onHoverAvg={setIsHoveringAvg}
            />
          </div>
        )}

        {/* Breakdown Section */}
        {trend && <BreakdownBar trend={trend} metric={metric} />}
      </main>

      {/* Floating Action Button with Whoop 'W' Logo */}
      <div className={styles.floatingActionBtn} aria-label="Whoop shortcut">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path
            d="M4.5 7.5L8.5 17L12 9.5L15.5 17L19.5 7.5"
            stroke="#8fb7ca"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
}
