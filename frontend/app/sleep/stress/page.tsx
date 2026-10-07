'use client';
import { sleepStressStatus } from '@/lib/sleepStressStatus';

/** Sleep Stress trend view using scored sleep sessions from the backend. */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SleepStressHistory } from '@/lib/types';
import styles from './page.module.css';
import theme from '@/components/SleepAnalytics.module.css';

type Timeframe = 'W' | 'M' | '6M';

interface StressBar {
  date: string;
  endDate: string;
  highPct: number;
  noHighPct: number;
  highMinutes: number;
  noHighMinutes: number;
  scoredDays: number;
}

function dateAtNoon(day: string): Date {
  return new Date(`${day}T12:00:00Z`);
}

function formatMinutes(minutes: number): string {
  const rounded = Math.round(minutes);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}

function formatRange(start: string, end: string): string {
  if (start === end) {
    return dateAtNoon(start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit', timeZone: 'UTC' }).toUpperCase();
  }
  const first = dateAtNoon(start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const last = dateAtNoon(end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit', timeZone: 'UTC' });
  return `${first} - ${last}`.toUpperCase();
}

function buildBars(history: SleepStressHistory, timeframe: Timeframe): StressBar[] {
  const byDate = new Map<string, { valid: number; high: number }>();
  for (const night of history.nights) {
    if (night.status !== 'ok' || night.stressed_minutes === null || night.valid_minutes <= 0) continue;
    const entry = byDate.get(night.night_date) ?? { valid: 0, high: 0 };
    entry.valid += night.valid_minutes;
    entry.high += night.stressed_minutes;
    byDate.set(night.night_date, entry);
  }

  const days: string[] = [];
  const current = new Date(`${history.range_start}T00:00:00Z`);
  const end = new Date(`${history.range_end}T00:00:00Z`);
  while (current <= end) {
    days.push(current.toISOString().slice(0, 10));
    current.setUTCDate(current.getUTCDate() + 1);
  }

  const groups: string[][] = [];
  if (timeframe === '6M') {
    for (let last = days.length; last > 0; last -= 7) {
      groups.unshift(days.slice(Math.max(0, last - 7), last));
    }
  } else {
    days.forEach((day) => groups.push([day]));
  }

  return groups.map((group) => {
    const values = group.map((day) => byDate.get(day)).filter((item): item is { valid: number; high: number } => item !== undefined);
    const valid = values.reduce((total, item) => total + item.valid, 0);
    const high = values.reduce((total, item) => total + item.high, 0);
    const highPct = valid ? 100 * high / valid : 0;
    return {
      date: group[0],
      endDate: group[group.length - 1],
      highPct,
      noHighPct: valid ? Math.max(0, 100 - highPct) : 0,
      highMinutes: high,
      noHighMinutes: Math.max(0, valid - high),
      scoredDays: values.length,
    };
  });
}

export default function SleepStressTrendPage() {
  const router = useRouter();
  const [timeframe, setTimeframe] = useState<Timeframe>('M');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [history, setHistory] = useState<SleepStressHistory | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setHistory(null); setError('');
    api.getSleepStress(timeframe).then((result) => {
      if (active) { setHistory(result); setError(''); setHoveredIndex(null); }
    }).catch(reason => {
      if (active) { setHistory(null); setError(reason instanceof Error ? reason.message : 'Sleep stress unavailable.'); }
    });
    return () => { active = false; };
  }, [timeframe]);

  const days = history ? buildBars(history, timeframe) : [];
  const scoredDays = days.reduce((total, day) => total + day.scoredDays, 0);
  const totalHigh = days.reduce((total, day) => total + day.highMinutes, 0);
  const avgHighStress = scoredDays ? formatMinutes(totalHigh / scoredDays) : '—';
  const rangeLabel = history ? formatRange(history.range_start, history.range_end) : '';
  const rangeDayCount = history ? Math.round((dateAtNoon(history.range_end).getTime() - dateAtNoon(history.range_start).getTime()) / 86400000) + 1 : 0;
  const deltaText = `${scoredDays} of ${rangeDayCount} nights scored`;
  const insightText = scoredDays
    ? `Across ${scoredDays} scored night${scoredDays === 1 ? '' : 's'}, you spent an average of ${avgHighStress} hours in high sleep stress. High stress requires both lower HRV and higher heart rate than your personal baseline.`
    : sleepStressStatus(history?.nights.filter(n => n.main_sleep).sort((a, b) => a.night_date.localeCompare(b.night_date)).at(-1));
  const hoveredDay = hoveredIndex !== null ? days[hoveredIndex] : null;
  let displayValue = avgHighStress;
  let displayLabel = 'AVG. HIGH STRESS';
  let isHovered = false;

  if (hoveredDay && hoveredDay.scoredDays) {
    displayValue = formatMinutes(hoveredDay.highMinutes);
    displayLabel = `HIGH STRESS • ${timeframe === '6M' ? formatRange(hoveredDay.date, hoveredDay.endDate) : hoveredDay.date.toUpperCase()}`;
    isHovered = true;
  }

  const xTickIndices = timeframe === 'W' ? days.map((_, i) => i)
    : [...new Set(Array.from({ length: timeframe === 'M' ? 5 : 6 }, (_, i) =>
      Math.round(i * (days.length - 1) / (timeframe === 'M' ? 4 : 5))))];

  if (!history && !error) return <div className={theme.detail}><div className={theme.detailInner}><div className="skeleton" style={{ height: 240, borderRadius: 18, marginTop: 24 }} /></div></div>;
  if (error) return <div className={theme.detail}><div className={theme.detailInner}><button className="btn" onClick={() => router.push('/sleep')}>← SLEEP</button><div className="card" role="alert" style={{ marginTop: 24, padding: 24 }}><h1>Sleep stress unavailable</h1><p className="text-secondary" style={{ marginTop: 12 }}>{error}</p></div></div></div>;

  return (
    <>
    <div className={theme.detail}>
      <div className={theme.detailInner}>
        {/* -- Top Navigation Bar -- */}
        <header className={theme.detailHeader}>
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

            {/* Scored-night count */}
            <div className={styles.deltaPill}>
              {isHovered && hoveredDay ? (
                <>
                  <span className={styles.deltaDotAmber}>●</span>
                  <span>{hoveredDay.highPct.toFixed(1)}% of valid sleep in high stress</span>
                </>
              ) : (
                <span className={styles.deltaTextAmber}>{deltaText}</span>
              )}
            </div>
          </div>

          {/* Right: Timeframe toggle + Date range */}
          <div className={styles.controlsBlock}>
            <div className={styles.timeframeToggle}>
              {(['W', 'M', '6M'] as const).map((t) => (
                <button
                  key={t}
                  aria-pressed={timeframe === t}
                  className={`${styles.toggleBtn} ${timeframe === t ? styles.toggleActive : ''}`}
                  onClick={() => {
                    if (t !== timeframe) { setHistory(null); setHoveredIndex(null); setTimeframe(t); }
                  }}
                >
                  {t}
                </button>
              ))}
            </div>

            <div className={styles.dateNavRow}>
              <span className={styles.dateRangeText}>{rangeLabel}</span>
            </div>
          </div>
        </div>

        {/* -- Insight Narrative Text -- */}
        <p className={styles.insightText}>{insightText}</p>

        {/* -- Legend Row -- */}
        <div className={styles.legendRow}>
          <div className={styles.legendItem}>
            <span className={styles.legendBoxHigh} />
            <span className={styles.legendText}>HIGH STRESS</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.legendBoxNoHigh} />
            <span className={styles.legendText}>NO HIGH STRESS</span>
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
                    {d.scoredDays > 0 && <div className={styles.barStack}>
                      {/* Top segment: High Stress (Amber) */}
                      {d.highPct > 0 && (
                        <div
                          className={styles.segHigh}
                          style={{ height: `${d.highPct}%` }}
                        />
                      )}
                      {/* Remaining valid sleep without detected high stress */}
                      <div
                        className={styles.segNoHigh}
                        style={{ height: `${d.noHighPct}%` }}
                      />
                    </div>}
                  </div>
                );
              })}
            </div>

            {/* Floating Tooltip when scrubbing */}
            {hoveredDay && hoveredDay.scoredDays > 0 && hoveredIndex !== null && (
              <div
                className={styles.hoverTooltip}
                style={{
                  left: `clamp(min(120px, 50%), ${((hoveredIndex + 0.5) / days.length) * 100}%, max(50%, calc(100% - 120px)))`,
                }}
              >
                <div className={styles.tooltipHeader}>
                  {formatRange(hoveredDay.date, hoveredDay.endDate)} · {hoveredDay.scoredDays} night{hoveredDay.scoredDays === 1 ? '' : 's'}
                </div>
                <div className={styles.tooltipRow}>
                  <span className={styles.tooltipDotHigh} />
                  <span>High stress: <strong>{formatMinutes(hoveredDay.highMinutes)}</strong> ({hoveredDay.highPct.toFixed(1)}%)</span>
                </div>
                <div className={styles.tooltipRow}>
                  <span className={styles.tooltipDotNoHigh} />
                  <span>No high stress: <strong>{formatMinutes(hoveredDay.noHighMinutes)}</strong> ({hoveredDay.noHighPct.toFixed(1)}%)</span>
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
                <span className={styles.xTickMonth}>{dateAtNoon(d.endDate).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' })}</span>
                <span className={styles.xTickDay}>{dateAtNoon(d.endDate).getUTCDate()}</span>
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
          <span>Average uses scored nights through {dateAtNoon(history!.range_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })}.</span>
        </div>

        {history?.is_mock && <p className={theme.demo}>DEMO · SYNTHETIC HISTORY</p>}
      </div>
    </div>
    </>
  );
}
