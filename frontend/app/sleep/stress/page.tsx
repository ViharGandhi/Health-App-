'use client';

/**
 * Trend View — Sleep Stress (/sleep/stress)
 * WHOOP-exact Sleep Stress Trend Screen:
 * - Top header with back button and "TREND VIEW"
 * - Dropdown pill: crescent moon icon, "SLEEP STRESS", chevron
 * - Summary section:
 *    - AVG. HIGH STRESS: 0:04 hr
 *    - Amber delta badge: ▲ 300% vs. prior month
 *    - Timeframe toggle: W | M | 6M (M active by default)
 *    - Date range navigator: < MAR 17 - APR 15, 26 >
 * - Narrative insight:
 *    "You spent an average of 0:04 hours in the high-stress zone while sleeping this month, which is above your previous 30-day average (0:01)."
 * - Legend row: HIGH (orange) | MEDIUM (green) | LOW (sky blue)
 * - 100% Stacked Bar Chart (30 daily bars, low/medium/high stress breakdown)
 * - Y-Axis: 100%, 75%, 50%, 25%, 0%
 * - X-Axis ticks: Mar 18, Mar 25, Apr 1, Apr 8, Apr 15
 * - Info footnote: "ℹ Average does not include today (Apr. 15)"
 * - Learn More section with podcast resource cards
 * - Full interactive hover & scrubbing
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';

interface StressDay {
  date: string;
  dayName: string;
  dayNum: number;
  lowPct: number;    // Sky blue
  medPct: number;    // Spring green
  highPct: number;   // Amber
  highHoursStr: string;
  medHoursStr: string;
  lowHoursStr: string;
}

// 30 days data matching the exact visual distribution in WHOOP screenshot
const MONTH_DAYS: StressDay[] = [
  { date: '2026-03-17', dayName: 'Tue', dayNum: 17, lowPct: 96, medPct: 4, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:18', lowHoursStr: '7:12' },
  { date: '2026-03-18', dayName: 'Wed', dayNum: 18, lowPct: 96, medPct: 4, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:18', lowHoursStr: '7:15' },
  { date: '2026-03-19', dayName: 'Thu', dayNum: 19, lowPct: 94, medPct: 6, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:27', lowHoursStr: '7:03' },
  { date: '2026-03-20', dayName: 'Fri', dayNum: 20, lowPct: 93, medPct: 7, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:32', lowHoursStr: '6:58' },
  { date: '2026-03-21', dayName: 'Sat', dayNum: 21, lowPct: 93, medPct: 7, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:31', lowHoursStr: '6:55' },
  { date: '2026-03-22', dayName: 'Sun', dayNum: 22, lowPct: 55, medPct: 43, highPct: 2, highHoursStr: '0:09', medHoursStr: '3:15', lowHoursStr: '4:10' },
  { date: '2026-03-23', dayName: 'Mon', dayNum: 23, lowPct: 92, medPct: 8, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:36', lowHoursStr: '6:54' },
  { date: '2026-03-24', dayName: 'Tue', dayNum: 24, lowPct: 72, medPct: 27, highPct: 1, highHoursStr: '0:05', medHoursStr: '2:05', lowHoursStr: '5:30' },
  { date: '2026-03-25', dayName: 'Wed', dayNum: 25, lowPct: 85, medPct: 15, highPct: 0, highHoursStr: '0:00', medHoursStr: '1:08', lowHoursStr: '6:22' },
  { date: '2026-03-26', dayName: 'Thu', dayNum: 26, lowPct: 83, medPct: 17, highPct: 0, highHoursStr: '0:00', medHoursStr: '1:16', lowHoursStr: '6:14' },
  { date: '2026-03-27', dayName: 'Fri', dayNum: 27, lowPct: 65, medPct: 28, highPct: 7, highHoursStr: '0:32', medHoursStr: '2:10', lowHoursStr: '5:00' },
  { date: '2026-03-28', dayName: 'Sat', dayNum: 28, lowPct: 97, medPct: 3, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:14', lowHoursStr: '7:20' },
  { date: '2026-03-29', dayName: 'Sun', dayNum: 29, lowPct: 90, medPct: 10, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:45', lowHoursStr: '6:45' },
  { date: '2026-03-30', dayName: 'Mon', dayNum: 30, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:30' },
  { date: '2026-03-31', dayName: 'Tue', dayNum: 31, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:35' },
  { date: '2026-04-01', dayName: 'Wed', dayNum: 1, lowPct: 80, medPct: 18, highPct: 2, highHoursStr: '0:09', medHoursStr: '1:22', lowHoursStr: '6:05' },
  { date: '2026-04-02', dayName: 'Thu', dayNum: 2, lowPct: 94, medPct: 6, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:27', lowHoursStr: '7:05' },
  { date: '2026-04-03', dayName: 'Fri', dayNum: 3, lowPct: 60, medPct: 37, highPct: 3, highHoursStr: '0:14', medHoursStr: '2:50', lowHoursStr: '4:35' },
  { date: '2026-04-04', dayName: 'Sat', dayNum: 4, lowPct: 92, medPct: 8, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:36', lowHoursStr: '6:55' },
  { date: '2026-04-05', dayName: 'Sun', dayNum: 5, lowPct: 98, medPct: 2, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:09', lowHoursStr: '7:25' },
  { date: '2026-04-06', dayName: 'Mon', dayNum: 6, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:30' },
  { date: '2026-04-07', dayName: 'Tue', dayNum: 7, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:30' },
  { date: '2026-04-08', dayName: 'Wed', dayNum: 8, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:30' },
  { date: '2026-04-09', dayName: 'Thu', dayNum: 9, lowPct: 95, medPct: 4, highPct: 1, highHoursStr: '0:04', medHoursStr: '0:18', lowHoursStr: '7:10' },
  { date: '2026-04-10', dayName: 'Fri', dayNum: 10, lowPct: 98, medPct: 2, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:09', lowHoursStr: '7:25' },
  { date: '2026-04-11', dayName: 'Sat', dayNum: 11, lowPct: 96, medPct: 4, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:18', lowHoursStr: '7:15' },
  { date: '2026-04-12', dayName: 'Sun', dayNum: 12, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:30' },
  { date: '2026-04-13', dayName: 'Mon', dayNum: 13, lowPct: 99, medPct: 1, highPct: 0, highHoursStr: '0:00', medHoursStr: '0:05', lowHoursStr: '7:30' },
  { date: '2026-04-14', dayName: 'Tue', dayNum: 14, lowPct: 83, medPct: 15, highPct: 2, highHoursStr: '0:09', medHoursStr: '1:08', lowHoursStr: '6:15' },
  { date: '2026-04-15', dayName: 'Wed', dayNum: 15, lowPct: 95, medPct: 4, highPct: 1, highHoursStr: '0:04', medHoursStr: '0:18', lowHoursStr: '7:15' },
];

export default function SleepStressTrendPage() {
  const router = useRouter();
  const [timeframe, setTimeframe] = useState<'W' | 'M' | '6M'>('M');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Filter days based on timeframe
  const days = timeframe === 'W'
    ? MONTH_DAYS.slice(-7)
    : MONTH_DAYS;

  const rangeLabel = timeframe === 'W'
    ? 'APR 9 - APR 15, 26'
    : timeframe === 'M'
    ? 'MAR 17 - APR 15, 26'
    : 'NOV 25 - APR 15, 26';

  const avgHighStress = timeframe === 'W' ? '0:03' : '0:04';
  const deltaText = timeframe === 'W' ? '▲ 150% vs. prior week' : '▲ 300% vs. prior month';
  const insightText = timeframe === 'W'
    ? 'You spent an average of 0:03 hours in the high-stress zone while sleeping this week, which is consistent with normal restorative recovery.'
    : 'You spent an average of 0:04 hours in the high-stress zone while sleeping this month, which is above your previous 30-day average (0:01).';

  const hoveredDay = hoveredIndex !== null ? days[hoveredIndex] : null;

  // Header display logic
  let displayValue = avgHighStress;
  let displayLabel = 'AVG. HIGH STRESS';
  let isHovered = false;

  if (hoveredDay) {
    displayValue = hoveredDay.highHoursStr;
    displayLabel = `HIGH STRESS • ${hoveredDay.dayName.toUpperCase()} ${hoveredDay.dayNum}`;
    isHovered = true;
  }

  // Ticks indices to label on X-axis (spaced weekly)
  const xTickIndices = timeframe === 'M'
    ? [1, 8, 15, 22, 29] // Mar 18, Mar 25, Apr 1, Apr 8, Apr 15
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
              {/* Crescent Moon Icon */}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            </div>
            <span className={styles.selectorTitle}>SLEEP STRESS</span>
          </div>
          <svg width="12" height="8" viewBox="0 0 12 8" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="1 1.5 6 6.5 11 1.5" />
          </svg>
        </div>

        {/* -- Summary Header Row -- */}
        <div className={styles.summaryRow}>
          {/* Left: Dynamic Average or Hovered Day High Stress */}
          <div className={styles.averageBlock}>
            <span className={`${styles.averageLabel} ${isHovered ? styles.averageLabelActive : ''}`}>
              {displayLabel}
            </span>
            <div className={styles.scoreRow}>
              <span className={styles.scoreBig}>{displayValue}</span>
              <span className={styles.scoreUnit}>hr</span>
            </div>

            {/* Amber Delta Badge */}
            <div className={styles.deltaPill}>
              {isHovered && hoveredDay ? (
                <>
                  <span className={styles.deltaDotAmber}>●</span>
                  <span>{hoveredDay.highPct}% of night in high stress</span>
                </>
              ) : (
                <>
                  <span className={styles.deltaArrowAmber}>▲</span>
                  <span className={styles.deltaTextAmber}>{deltaText}</span>
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
              <span className={styles.dateRangeText}>{rangeLabel}</span>
              <button className={styles.dateArrowBtn} aria-label="Next range">
                <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 1.5L4.5 5L1 8.5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* -- Insight Narrative Text -- */}
        <p className={styles.insightText}>{insightText}</p>

        {/* -- Legend Row (HIGH | MEDIUM | LOW) -- */}
        <div className={styles.legendRow}>
          <div className={styles.legendItem}>
            <span className={styles.legendBoxHigh} />
            <span className={styles.legendText}>HIGH</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.legendBoxMedium} />
            <span className={styles.legendText}>MEDIUM</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.legendBoxLow} />
            <span className={styles.legendText}>LOW</span>
          </div>
        </div>

        {/* -- 100% Stacked Bar Chart -- */}
        <div className={styles.chartWrapper} onMouseLeave={() => setHoveredIndex(null)}>
          {/* Y-Axis Column */}
          <div className={styles.yAxisCol}>
            {['100%', '75%', '50%', '25%', '0%'].map((lbl) => (
              <div key={lbl} className={styles.yTickItem}>
                <span className={styles.yTickLabel}>{lbl}</span>
              </div>
            ))}
          </div>

          {/* Graph Body */}
          <div className={styles.graphBody}>
            {/* Horizontal Gridlines */}
            <div className={styles.gridlinesBody}>
              {['100%', '75%', '50%', '25%', '0%'].map((lbl) => (
                <div key={lbl} className={styles.gridlineRow} />
              ))}
            </div>

            {/* Daily Stacked Bars */}
            <div className={styles.barsContainer}>
              {days.map((d, i) => {
                const isSelected = hoveredIndex === i;
                return (
                  <div
                    key={d.date}
                    className={`${styles.barCol} ${isSelected ? styles.barColActive : ''}`}
                    onMouseEnter={() => setHoveredIndex(i)}
                    onClick={() => setHoveredIndex(i)}
                  >
                    <div className={styles.barStack}>
                      {/* Top segment: High Stress (Amber) */}
                      {d.highPct > 0 && (
                        <div
                          className={styles.segHigh}
                          style={{ height: `${d.highPct}%` }}
                        />
                      )}
                      {/* Middle segment: Medium Stress (Spring Green) */}
                      {d.medPct > 0 && (
                        <div
                          className={styles.segMedium}
                          style={{ height: `${d.medPct}%` }}
                        />
                      )}
                      {/* Bottom segment: Low Stress (Sky Blue) */}
                      <div
                        className={styles.segLow}
                        style={{ height: `${d.lowPct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Floating Tooltip when scrubbing */}
            {hoveredDay && hoveredIndex !== null && (
              <div
                className={styles.hoverTooltip}
                style={{
                  left: `${((hoveredIndex + 0.5) / days.length) * 100}%`,
                }}
              >
                <div className={styles.tooltipHeader}>
                  {hoveredDay.dayName}, {hoveredDay.date.slice(5).replace('-', '/')}
                </div>
                <div className={styles.tooltipRow}>
                  <span className={styles.tooltipDotHigh} />
                  <span>High: <strong>{hoveredDay.highHoursStr}</strong> ({hoveredDay.highPct}%)</span>
                </div>
                <div className={styles.tooltipRow}>
                  <span className={styles.tooltipDotMed} />
                  <span>Med: <strong>{hoveredDay.medHoursStr}</strong> ({hoveredDay.medPct}%)</span>
                </div>
                <div className={styles.tooltipRow}>
                  <span className={styles.tooltipDotLow} />
                  <span>Low: <strong>{hoveredDay.lowHoursStr}</strong> ({hoveredDay.lowPct}%)</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* -- X-Axis Dates Row -- */}
        <div className={styles.xAxisRow}>
          {xTickIndices.map((idx) => {
            const d = days[idx];
            if (!d) return null;
            const pct = ((idx + 0.5) / days.length) * 100;
            const isHighlighted = hoveredIndex !== null && Math.abs(hoveredIndex - idx) <= 1;

            return (
              <div
                key={d.date}
                className={`${styles.xTickItem} ${isHighlighted ? styles.xTickHighlighted : ''}`}
                style={{ left: `${pct}%` }}
                onClick={() => setHoveredIndex(idx)}
              >
                <span className={styles.xTickMonth}>{d.date.slice(5, 7) === '03' ? 'Mar' : 'Apr'}</span>
                <span className={styles.xTickDay}>{d.dayNum}</span>
              </div>
            );
          })}
        </div>

        {/* -- Footnote -- */}
        <div className={styles.footnoteRow}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#8E95A2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span>Average does not include today (Apr. 15)</span>
        </div>

        {/* -- Learn More / Resources Section -- */}
        <section className={styles.learnMoreSection}>
          <div className={styles.learnMoreHeader}>
            <span className={styles.learnMoreTitle}>LEARN MORE</span>
            <span className={styles.learnMoreViewAll}>VIEW ALL</span>
          </div>

          <div className={styles.podcastCardsRow}>
            <div className={styles.podcastCard}>
              <div className={styles.podcastBadge}>PODCAST</div>
              <span className={styles.podcastTitle}>The Science of Sleep Stress & Recovery</span>
            </div>
            <div className={styles.podcastCard}>
              <div className={styles.podcastBadge}>PODCAST</div>
              <span className={styles.podcastTitle}>Managing Autonomic Nervous System Elevation</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
