'use client';

import { useId, useState } from 'react';
import type { RecoveryAnalytics, RecoveryMetric } from '@/lib/types';
import { BLUE, LINE_BLUE, axisBounds, changeColor, dateLabel, lineSegments, recoveryColor, recoveryMetrics, relativeChange } from '@/lib/recovery';
import { lineLabelPositions } from '@/lib/sleepChartLabels';
import styles from '@/app/recovery/page.module.css';

export interface RecoveryChartSelection { label: string; value: number | null }

export default function RecoveryTrendChart({ data, metric, embedded = false, onSelect }: {
  data: RecoveryAnalytics; metric: RecoveryMetric; embedded?: boolean;
  onSelect?: (selection: RecoveryChartSelection | null) => void;
}) {
  const id = useId().replaceAll(':', '');
  const [selected, setSelected] = useState<number | null>(null);
  const [pinned, setPinned] = useState(false);
  const config = recoveryMetrics.find(item => item.metric === metric)!;
  const sixMonths = !embedded && data.timeframe === '6M';
  const days = data.days;
  const band = data.typical_ranges[metric];
  const values = days.map(day => day[metric]).filter((value): value is number => value != null);
  const [low, high] = axisBounds(values, metric, band);
  const left = embedded ? 12 : 40, right = 328, top = 28, bottom = 238;
  const x = (index: number) => left + (index + .5) * (right - left) / Math.max(1, days.length);
  const y = (value: number) => bottom - (value - low) / (high - low) * (bottom - top);
  const segments = lineSegments(days, metric);
  const pointCount = sixMonths ? data.monthly_buckets.length : days.length;
  const selectedDay = selected == null || sixMonths ? null : days[selected];
  const bucket = selected == null || !sixMonths ? null : data.monthly_buckets[selected];
  const selectedValue = bucket ? bucket.averages[metric] : selectedDay?.[metric];
  const selectedX = bucket ? (x(days.findIndex(day => day.date >= bucket.start_date)) + x(days.findLastIndex(day => day.date <= bucket.end_date))) / 2 : selected == null ? null : x(selected);
  const selectionLabel = bucket ? `${dateLabel(bucket.start_date)} – ${dateLabel(bucket.end_date)}` : selectedDay ? dateLabel(selectedDay.date, { weekday: 'short', month: 'short', day: 'numeric' }) : '';
  const select = (index: number | null) => {
    setSelected(index);
    if (index == null) { onSelect?.(null); return; }
    const item = sixMonths ? data.monthly_buckets[index] : days[index];
    onSelect?.({ label: 'averages' in item ? `${dateLabel(item.start_date)} – ${dateLabel(item.end_date)}` : dateLabel(item.date, { weekday: 'short', month: 'short', day: 'numeric' }),
                value: 'averages' in item ? item.averages[metric] : item[metric] });
  };
  const fromPointer = (event: React.PointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = (event.clientX - bounds.left) / bounds.width * 340;
    if (sixMonths) {
      const index = data.monthly_buckets.findIndex(item => {
        const first = days.findIndex(day => day.date >= item.start_date);
        const last = days.findLastIndex(day => day.date <= item.end_date);
        return position <= x(last) + (right - left) / days.length / 2 && first >= 0;
      });
      return Math.max(0, index < 0 ? pointCount - 1 : index);
    }
    return Math.max(0, Math.min(pointCount - 1, Math.floor((position - left) / (right - left) * days.length)));
  };
  const weekly = embedded || data.timeframe === 'W';
  const labels = lineLabelPositions(days.map((day, index) => day[metric] == null ? null : { x: x(index), y: y(day[metric]!) }), days.map(() => null), 24);
  const ticks = config.kind === 'bar' ? [0, 25, 50, 75, 100] : [low, low + (high - low) / 3, low + 2 * (high - low) / 3, high];
  const labelIndices = weekly ? days.map((_, i) => i) : [0, Math.round((days.length - 1) / 4), Math.round((days.length - 1) / 2), Math.round(3 * (days.length - 1) / 4), days.length - 1];
  const last = days.findLastIndex(day => day[metric] != null);
  const barWidth = Math.min(15, (right - left) / Math.max(days.length, 1) * .55);
  return <div className={styles.chartWrap}>
    {!embedded && config.kind === 'line' && !sixMonths && <div className={styles.typicalLegend}><i />{band ? 'TYPICAL RANGE' : 'BUILDING TYPICAL RANGE'}</div>}
    <svg className={styles.chart} viewBox="0 0 340 286" role="group" tabIndex={0} aria-label={`Interactive ${config.title.toLowerCase()} chart. Arrow keys select readings; Escape clears selection.`}
      onPointerMove={event => select(fromPointer(event))} onPointerDown={event => { setPinned(true); select(fromPointer(event)); }}
      onPointerLeave={() => { if (!pinned) select(null); }}
      onKeyDown={event => {
        if (event.key === 'Escape') { setPinned(false); select(null); }
        else if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
          event.preventDefault(); setPinned(true);
          select(event.key === 'Home' ? 0 : event.key === 'End' ? pointCount - 1 : Math.max(0, Math.min(pointCount - 1, (selected ?? pointCount - 1) + (event.key === 'ArrowRight' ? 1 : -1))));
        }
      }}>
      <defs><linearGradient id={`recovery-fill-${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={LINE_BLUE} stopOpacity=".12" /><stop offset="1" stopColor={LINE_BLUE} stopOpacity="0" /></linearGradient></defs>
      {weekly && days.length > 0 && <rect x={x(days.length - 1) - 17} y="10" width="34" height="268" rx="3" fill="#FFFFFF" opacity=".055" />}
      {!embedded && !sixMonths && band && config.kind === 'line' && <rect x={left} y={y(band.high)} width={right - left} height={y(band.low) - y(band.high)} fill="#ADB5BD" opacity=".14" />}
      {ticks.map(tick => <g key={tick}><line x1={left} x2={right} y1={y(tick)} y2={y(tick)} stroke="#FFFFFF" strokeOpacity=".10" />
        {!embedded && <text x={left - 11} y={y(tick) + 3} textAnchor="end" className={styles.axis}>{config.kind === 'bar' ? `${tick}%` : metric === 'respiratory_rate' ? tick.toFixed(1) : tick.toFixed(0)}</text>}</g>)}
      {config.kind === 'line' && segments.map((segment, index) => {
        const path = segment.map((point, position) => `${position ? 'L' : 'M'}${x(point.index)},${y(point.value)}`).join(' ');
        return <g key={index} opacity={selected != null || sixMonths ? .3 : 1}>
          {segment.length > 1 && <path d={`${path} L${x(segment.at(-1)!.index)},${bottom} L${x(segment[0].index)},${bottom}Z`} fill={`url(#recovery-fill-${id})`} />}
          <path d={path} fill="none" stroke={LINE_BLUE} strokeWidth={sixMonths ? 1.2 : 2} strokeLinecap="round" strokeLinejoin="round" />
          {!weekly && segment.length === 1 && <circle cx={x(segment[0].index)} cy={y(segment[0].value)} r="2" fill={LINE_BLUE} />}
        </g>;
      })}
      {config.kind === 'bar' && !sixMonths && days.map((day, index) => day[metric] == null ? null : <rect key={day.date} x={x(index) - barWidth / 2} y={y(day[metric]!)} width={barWidth} height={bottom - y(day[metric]!)} rx="1.5" fill={metric === 'recovery' ? recoveryColor(day.zone, day.date === data.range_end ? data.current.status : undefined) : BLUE} opacity={selected == null || selected === index ? 1 : .35} />)}
      {weekly && days.map((day, index) => day[metric] == null ? null : <g key={day.date} opacity={selected == null || selected === index ? 1 : .4}>
        {config.kind === 'line' && <circle cx={x(index)} cy={y(day[metric]!)} r="4" fill="#222A31" stroke={LINE_BLUE} strokeWidth="2" />}
        <text x={x(index)} y={config.kind === 'bar' ? Math.max(13, y(day[metric]!) - 7) : labels[index].first ?? y(day[metric]!) - 12} textAnchor="middle" className={styles.valueLabel} fill={metric === 'recovery' ? recoveryColor(day.zone, day.date === data.range_end ? data.current.status : undefined) : BLUE}>{day[metric]!.toFixed(config.digits)}{config.unit === '%' ? '%' : ''}</text>
      </g>)}
      {!weekly && !sixMonths && last >= 0 && <>{config.kind === 'line' && <circle cx={x(last)} cy={y(days[last][metric]!)} r="4" fill="#20262B" stroke={LINE_BLUE} strokeWidth="2" />}<text x={x(last)} y={Math.max(14, y(days[last][metric]!) - 12)} textAnchor="middle" className={styles.valueLabel} fill={BLUE}>{days[last][metric]!.toFixed(config.digits)}{config.unit === '%' ? '%' : ''}</text></>}
      {sixMonths && data.monthly_buckets.map((item, index) => {
        const value = item.averages[metric];
        if (value == null) return null;
        const first = days.findIndex(day => day.date >= item.start_date), lastDay = days.findLastIndex(day => day.date <= item.end_date);
        const halfStep = (right - left) / days.length / 2;
        const x1 = x(first) - halfStep + 2, x2 = x(lastDay) + halfStep - 2;
        const change = relativeChange(value, data.monthly_buckets[index - 1]?.averages[metric] ?? null);
        const color = index ? changeColor(metric, change) : '#DCE0E3';
        return <g key={item.start_date} opacity={selected == null || selected === index ? 1 : .45}>
          {config.kind === 'bar' ? <rect x={(x1 + x2) / 2 - 9} y={y(value)} width="18" height={bottom - y(value)} rx="1.5" fill={BLUE} /> : <line x1={x1} x2={x2} y1={y(value)} y2={y(value)} stroke={color} strokeWidth="2.5" />}
          <text x={(x1 + x2) / 2} y={y(value) - 12} textAnchor="middle" className={styles.valueLabel} fill="#FFF">{value.toFixed(config.digits)}{config.unit === '%' ? '%' : ''}</text>
          {config.kind === 'line' && change != null && <text x={(x1 + x2) / 2} y={y(value) + 18} textAnchor="middle" className={styles.valueLabel} fill={color}>{change > 0 ? '+' : ''}{change.toFixed(0)}%</text>}
          <text x={(x1 + x2) / 2} y="265" textAnchor="middle" className={styles.axis}>{dateLabel(item.end_date, { month: 'short' })}</text>
        </g>;
      })}
      {!sixMonths && labelIndices.map(index => <text key={index} x={x(index)} y="257" textAnchor="middle" className={styles.axis}>
        {weekly ? <><tspan x={x(index)}>{dateLabel(days[index].date, { weekday: 'short' })}</tspan><tspan x={x(index)} dy="13">{new Date(`${days[index].date}T12:00:00`).getDate()}</tspan></> : dateLabel(days[index].date)}
      </text>)}
      {selectedX != null && <><line x1={selectedX} x2={selectedX} y1={top} y2={bottom} stroke="#ADB6C0" strokeWidth="1" strokeDasharray="3 3" />
        {selectedValue != null && <circle cx={selectedX} cy={y(selectedValue)} r="5" fill={LINE_BLUE} stroke="#1C242B" strokeWidth="1.5" />}</>}
      {!values.length && <text x="184" y="138" textAnchor="middle" className={styles.axis}>No recorded values in this period</text>}
    </svg>
    {selected != null && <div className={styles.chartReadout} aria-live="polite"><span>{selectionLabel}</span><strong>{selectedValue == null ? 'No reading' : `${selectedValue.toFixed(config.digits)} ${config.unit}`}</strong>
      {metric === 'recovery' && selectedDay?.confidence && <span>{selectedDay.confidence} confidence{selectedDay.sleep_context_missing ? ' · HRV/RHR only' : ''}</span>}
      <button onClick={() => { setPinned(false); select(null); }} aria-label="Clear chart selection">×</button></div>}
  </div>;
}
