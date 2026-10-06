'use client';

import { useId, useState } from 'react';
import type { HealthPoint, HeartRatePoint } from '@/lib/types';
import { healthBounds, healthDate, healthMonths, healthSegments, type HealthRange } from '@/lib/health';
import { lineLabelPositions } from '@/lib/sleepChartLabels';
import styles from '@/app/recovery/page.module.css';

export type HealthSelection = { label: string; value: number | null; baseline: number | null; count?: number; days?: number };

export default function HealthTrendChart({ points = [], heartRate, range = 'W', metric, unit, digits, compact = false, onSelect }: {
  points?: HealthPoint[]; heartRate?: HeartRatePoint[]; range?: HealthRange;
  metric: string; unit: string; digits: number; compact?: boolean;
  onSelect?: (selection: HealthSelection | null) => void;
}) {
  const id = useId();
  const [chosen, setChosen] = useState<number | null>(null);
  const [pinned, setPinned] = useState(false);
  const intraday = heartRate != null;
  const monthly = range === '6M' && !intraday;
  const dayPoints = intraday ? heartRate.map(point => ({ ...point, date: point.time, baseline: null })) : points;
  const minutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
  const left = 42, right = 326, top = 32, bottom = compact ? 192 : 238;
  const span = Math.max(1, dayPoints.length - 1);
  const x = (index: number) => intraday
    ? left + (minutes(dayPoints[index].date) - minutes(dayPoints[0].date)) / Math.max(1, minutes(dayPoints.at(-1)!.date) - minutes(dayPoints[0].date)) * (right - left)
    : left + index / span * (right - left);
  const values = dayPoints.flatMap(point => [point.value, point.baseline]).filter((value): value is number => value != null);
  const readings = dayPoints.filter(point => point.value != null);
  if (!readings.length) return <div className={styles.loading}>No {intraday ? 'heart-rate samples today' : 'measurements in this period'}.</div>;
  const [low, high] = healthBounds(values, metric);
  const y = (value: number) => bottom - (value - low) / (high - low) * (bottom - top);
  const months = monthly ? healthMonths(points) : [];
  const options: (HealthSelection & { x: number })[] = monthly ? months.map(month => ({
    label: `${healthDate(points[month.start].date)} – ${healthDate(points[month.end].date, { month: 'short', day: 'numeric', year: 'numeric' })}`,
    value: month.value, baseline: null, count: month.count, days: month.days, x: x((month.start + month.end) / 2),
  })) : dayPoints.map((point, index) => ({ label: intraday ? `${point.date} · 15-minute median` : healthDate(point.date, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }),
    value: point.value, baseline: point.baseline, x: x(index) }));
  const select = (index: number | null, pin = false) => {
    setChosen(index); setPinned(pin); onSelect?.(index == null ? null : options[index]);
  };
  const fromPointer = (event: React.PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const target = (event.clientX - box.left) / box.width * 340;
    return options.reduce((best, point, index) => Math.abs(point.x - target) < Math.abs(options[best].x - target) ? index : best, 0);
  };
  let segments = healthSegments(dayPoints);
  if (intraday) {
    segments = [];
    dayPoints.forEach((point, index) => {
      if (!index || minutes(point.date) - minutes(dayPoints[index - 1].date) > 30) segments.push([]);
      segments.at(-1)!.push({ index, value: point.value! });
    });
  }
  const path = (segment: { index: number; value: number }[]) => segment.map((point, index) => `${index ? 'L' : 'M'}${x(point.index)},${y(point.value)}`).join(' ');
  const positions = lineLabelPositions(dayPoints.map((point, index) => point.value == null ? null : { x: x(index), y: y(point.value) }),
    dayPoints.map((point, index) => point.baseline == null ? null : { x: x(index), y: y(point.baseline) }), 16);
  const latest = dayPoints.findLastIndex(point => point.value != null);
  const selection = chosen == null ? null : options[chosen];
  const ticks = intraday ? [0, Math.floor(span / 2), span] : range === 'W' ? dayPoints.map((_, index) => index) : [0, Math.round(span / 4), Math.round(span / 2), Math.round(span * .75), span];
  return <div className={styles.chartWrap}>
    <svg className={styles.chart} viewBox={`0 0 340 ${bottom + 46}`} role="slider" tabIndex={0}
      aria-label={`${metric.replaceAll('_', ' ')} ${intraday ? 'heart-rate samples' : `${range} trend`}. Use arrow keys to explore.`}
      aria-valuemin={0} aria-valuemax={Math.max(0, options.length - 1)} aria-valuenow={chosen ?? options.length - 1}
      aria-valuetext={selection ? `${selection.label}: ${selection.value == null ? 'No measurement' : `${selection.value.toFixed(digits)} ${unit}`}` : 'No selection'}
      onPointerMove={event => { if (!pinned) select(fromPointer(event)); }} onPointerLeave={() => { if (!pinned) select(null); }}
      onClick={event => select(fromPointer(event), true)}
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); select(null); }
        else if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const index = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : Math.max(0, Math.min(options.length - 1, (chosen ?? options.length - 1) + (event.key === 'ArrowRight' ? 1 : -1)));
          select(index, true);
        }
      }}>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop stopColor="#67AEE6" stopOpacity=".13" /><stop offset="1" stopColor="#67AEE6" stopOpacity="0" /></linearGradient></defs>
      {Array.from({ length: 5 }, (_, index) => {
        const value = high - (high - low) * index / 4;
        return <g key={index}><line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke="#FFFFFF16" /><text x={left - 9} y={y(value) + 3} textAnchor="end" className={styles.axis}>{value.toFixed(digits)}</text></g>;
      })}
      {chosen != null && <rect x={options[chosen].x - (monthly ? 16 : range === 'W' && !intraday ? 13 : 5)} y={top - 5}
        width={monthly ? 32 : range === 'W' && !intraday ? 26 : 10} height={bottom - top + 5} rx="3" fill="#FFFFFF09" />}
      {segments.map((segment, index) => <g key={index} opacity={monthly ? .24 : selection ? .5 : 1}>
        {!monthly && segment.length > 1 && <path d={`${path(segment)} L${x(segment.at(-1)!.index)},${bottom} L${x(segment[0].index)},${bottom} Z`} fill={`url(#${id})`} />}
        <path d={path(segment)} fill="none" stroke="#67AEE6" strokeWidth={monthly ? 1.2 : 2} strokeLinejoin="round" strokeLinecap="round" />
        {segment.length === 1 && <circle cx={x(segment[0].index)} cy={y(segment[0].value)} r="3.5" fill="#67AEE6" />}
      </g>)}
      {!monthly && healthSegments(dayPoints, 'baseline').map((segment, index) => <g key={`baseline-${index}`}>
        <path d={path(segment)} fill="none" stroke="#ADB6BD" strokeWidth="1.3" strokeDasharray="4 4" />
        {segment.length === 1 && <line x1={x(segment[0].index) - 5} x2={x(segment[0].index) + 5} y1={y(segment[0].value)} y2={y(segment[0].value)} stroke="#ADB6BD" strokeDasharray="3 2" />}
      </g>)}
      {!monthly && dayPoints.map((point, index) => point.value == null || (range !== 'W' || intraday) && index !== latest && index !== chosen ? null
        : <circle key={index} cx={x(index)} cy={y(point.value)} r="3.5" fill="#202830" stroke="#67AEE6" strokeWidth="1.7" />)}
      {monthly && months.map((month, index) => month.value == null ? null : <g key={month.month}>
        <line x1={x(month.start) + 2} x2={Math.max(x(month.start) + 4, x(month.end) - 2)} y1={y(month.value)} y2={y(month.value)} stroke="#7BA1BB" strokeWidth="3" />
        <text x={options[index].x} y={y(month.value) - 10} fill="#FFF" textAnchor="middle" className={styles.valueLabel}>{month.value.toFixed(digits)}</text>
      </g>)}
      {!monthly && dayPoints.map((point, index) => point.value == null || chosen != null || (range !== 'W' || intraday) && index !== latest ? null
        : <text key={index} x={Math.max(left + 9, Math.min(right - 9, x(index)))} y={Math.max(16, positions[index].first!)} fill="#67AEE6" textAnchor="middle" className={styles.valueLabel}>{point.value.toFixed(digits)}</text>)}
      {selection && <g><line x1={selection.x} x2={selection.x} y1={top} y2={bottom} stroke="#FFF" strokeDasharray="3 3" opacity=".65" />
        {selection.value != null && <circle cx={selection.x} cy={y(selection.value)} r="5" fill="#67AEE6" stroke="#1D252C" strokeWidth="2" />}</g>}
      {monthly ? months.map((month, index) => <text key={month.month} x={options[index].x} y={bottom + 20} textAnchor="middle" className={styles.axis}>{healthDate(`${month.month}-01`, { month: 'short' })}</text>)
        : [...new Set(ticks)].map(index => <text key={index} x={x(index)} y={bottom + 18} textAnchor="middle" className={styles.axis}>
          {intraday ? dayPoints[index].date : healthDate(dayPoints[index].date, range === 'W' ? { weekday: 'short' } : { month: 'short', day: 'numeric' })}
          {!intraday && range === 'W' && <tspan x={x(index)} dy="12">{healthDate(dayPoints[index].date, { day: 'numeric' })}</tspan>}
        </text>)}
    </svg>
    {selection && <div className={styles.chartReadout} aria-live="polite"><span>{selection.label}</span><strong>{selection.value == null ? 'No measurement' : `${selection.value.toFixed(digits)} ${unit}`}</strong>
      {selection.baseline != null && <span>Prior 14-day median {selection.baseline.toFixed(digits)} {unit}</span>}
      {selection.count != null && <span>{selection.count} / {selection.days} days recorded</span>}
      <button aria-label="Clear chart selection" onClick={() => select(null)}>×</button>
    </div>}
  </div>;
}
