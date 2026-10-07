'use client';

import { useState } from 'react';
import type { StrainAnalytics, StrainMetric, ZoneMinutes } from '@/lib/types';
import { dateLabel, relativeChange } from '@/lib/recovery';
import { durationMetric, strainFormat, strainMetrics, strainMonths, strainSummary, strainValue, STRAIN_BLUE, weekBuckets, zoneColors, zoneKeys } from '@/lib/strain';
import shared from '@/app/recovery/page.module.css';
import styles from '@/app/strain/page.module.css';

export interface StrainSelection { label: string; value: number | null; zones: ZoneMinutes | null }

export default function StrainTrendChart({ data, metric, embedded = false, onSelect }: {
  data: StrainAnalytics; metric: StrainMetric; embedded?: boolean; onSelect?: (value: StrainSelection | null) => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const [pinned, setPinned] = useState(false);
  const weekly = embedded || data.timeframe === 'W', six = !embedded && data.timeframe === '6M';
  const grouped = !weekly && durationMetric(metric);
  const bars = grouped ? weekBuckets(data.days, metric) : data.days.map(day => ({ start: day.date, end: day.date, value: strainValue(day, metric), zones: day.zones }));
  const months = six ? strainMonths(data.days.filter(day => metric !== 'strain' || day.date !== data.today), metric) : [];
  const readings = six ? months : bars;
  const values = [...bars, ...months].map(point => point.value).filter((value): value is number => value != null);
  const max = Math.max(0, ...values);
  const stepTick = max * 1.08 <= 5000 ? 1000 : max * 1.08 <= 30000 ? 5000 : 10000;
  const high = metric === 'strain' ? 21 : metric === 'steps' ? Math.max(5000, Math.ceil(max * 1.08 / stepTick) * stepTick)
    : [15, 30, 60, 120, 180, 240, 360, 480, 720, 1440, 2880].find(value => value >= max * 1.08) ?? Math.ceil(max / 240) * 240;
  const ticks = metric === 'strain' ? [0, 5, 10, 15, 21] : metric === 'steps' ? Array.from({ length: high / stepTick + 1 }, (_, i) => stepTick * i) : Array.from({ length: 5 }, (_, i) => high / 4 * i);
  const left = embedded ? 10 : 43, right = 350, top = 28, bottom = 252;
  const x = (index: number) => left + (index + .5) * (right - left) / Math.max(1, bars.length);
  const y = (value: number) => bottom - value / high * (bottom - top);
  const width = Math.min(grouped && !six ? 54 : 16, (right - left) / Math.max(1, bars.length) * .62);
  const zoneIndices = metric === 'zones_1_3' ? [0, 1, 2] : metric === 'zones_4_5' ? [3, 4] : [];
  const summary = strainSummary(data.days, metric, data.timeframe, data.today);
  const monthEdges = months.map(month => ({ first: bars.findIndex(bar => bar.end >= month.start), last: bars.findLastIndex(bar => bar.start <= month.end) }));
  const selectedX = selected == null ? null : six ? (x(monthEdges[selected].first) + x(monthEdges[selected].last)) / 2 : x(selected);
  const select = (index: number | null) => {
    setSelected(index);
    if (index == null) { onSelect?.(null); return; }
    const item = readings[index];
    onSelect?.({ label: item.start === item.end ? dateLabel(item.start, { weekday: 'short', month: 'short', day: 'numeric' }) : `${dateLabel(item.start)} – ${dateLabel(item.end)}`,
      value: item.value, zones: item.zones });
  };
  const pointer = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect(), position = (event.clientX - box.left) / box.width * 360;
    const index = six ? monthEdges.findIndex(edge => position <= x(edge.last) + (right - left) / bars.length / 2)
      : Math.floor((position - left) / (right - left) * bars.length);
    return Math.max(0, Math.min(readings.length - 1, index < 0 && six ? readings.length - 1 : index));
  };
  const labels = weekly ? bars.map((_, i) => i) : grouped && !six ? bars.map((_, i) => i)
    : [0, Math.round((bars.length - 1) / 4), Math.round((bars.length - 1) / 2), Math.round(3 * (bars.length - 1) / 4), bars.length - 1];
  return <div>
    {embedded && zoneIndices.length > 0 && <div className={styles.chartLegend}>{zoneIndices.map(i => <span key={i}><i style={{ background: zoneColors[i] }} />ZONE {i + 1}</span>)}</div>}
    <svg viewBox="0 0 360 310" className={shared.chart} role="slider" tabIndex={0} data-timeframe={weekly ? 'W' : data.timeframe}
      aria-label={`Interactive ${strainMetrics.find(item => item.key === metric)!.title.toLowerCase()} chart`}
      aria-valuemin={0} aria-valuemax={Math.max(0, readings.length - 1)} aria-valuenow={selected ?? Math.max(0, readings.length - 1)}
      aria-valuetext={selected == null ? 'Arrow keys select a period; Escape clears selection.' : `${readings[selected].start}: ${strainFormat(readings[selected].value, metric)}`}
      onPointerMove={event => { if (!pinned && readings.length) select(pointer(event)); }}
      onPointerDown={event => { if (readings.length) { const index = pointer(event); if (pinned && selected === index) { setPinned(false); select(null); } else { setPinned(true); select(index); } } }}
      onPointerLeave={() => { if (!pinned) select(null); }} onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); setPinned(false); select(null); }
        else if (readings.length && ['Home', 'End', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
          event.preventDefault(); setPinned(true);
          select(event.key === 'Home' ? 0 : event.key === 'End' ? readings.length - 1 : Math.max(0, Math.min(readings.length - 1, (selected ?? readings.length - 1) + (event.key === 'ArrowRight' ? 1 : -1))));
        }
      }}>
      {embedded && bars.length > 0 && <rect x={x(bars.length - 1) - 17} y="10" width="34" height="294" rx="3" fill="#FFFFFF" opacity=".07" />}
      {ticks.map(value => <g key={value}><line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke="#FFF" strokeOpacity=".1" />
        {!embedded && <text x={left - 9} y={y(value) + 3} textAnchor="end" className={shared.axis}>{metric === 'strain' ? value : strainFormat(value, metric)}</text>}</g>)}
      {bars.map((bar, index) => {
        if (bar.value == null) return null;
        const opacity = six ? .25 : selected == null || selected === index ? 1 : .25;
        if (!zoneIndices.length) return <rect key={bar.start} x={x(index) - width / 2} y={y(bar.value)} width={width} height={bottom - y(bar.value)} rx="1.3" fill={STRAIN_BLUE} opacity={opacity} />;
        let total = 0;
        return <g key={bar.start} opacity={opacity}>{zoneIndices.map(i => {
          const value = bar.zones?.[zoneKeys[i]] ?? 0;
          total += value;
          const height = Math.max(0, y(total - value) - y(total));
          return <rect key={i} x={x(index) - width / 2} y={y(total)} width={width} height={Math.max(0, height - (height > 2 ? 1.5 : 0))} fill={zoneColors[i]} />;
        })}</g>;
      })}
      {!embedded && !six && !weekly && summary != null && <g><line x1={left} x2={right} y1={y(summary)} y2={y(summary)} stroke="#E4E7E9" strokeDasharray="3 3" /><rect x="1" y={y(summary) - 9} width="39" height="18" rx="3" fill="#F7F7F7" /><text x="20" y={y(summary) + 3} textAnchor="middle" className={styles.avgTag}>AVG.</text></g>}
      {selectedX != null && <line x1={selectedX} x2={selectedX} y1={top - 8} y2={bottom} stroke="#C4CDD3" strokeDasharray="3 3" />}
      {weekly && bars.map((bar, index) => bar.value == null ? null : <text key={bar.start} x={x(index)} y={Math.max(14, y(bar.value) - 7)} textAnchor="middle" className={shared.valueLabel} fill={zoneIndices.length ? '#FFF' : STRAIN_BLUE} opacity={selected == null || selected === index ? 1 : .35}>{strainFormat(bar.value, metric)}</text>)}
      {six && months.map((month, index) => {
        const edge = monthEdges[index], center = (x(edge.first) + x(edge.last)) / 2;
        const change = relativeChange(month.value, months[index - 1]?.value ?? null);
        const color = change == null || Math.abs(change) < .5 ? '#E4E7E9' : change > 0 ? '#00DCA0' : '#F5AC22';
        return <g key={month.end} opacity={selected == null || selected === index ? 1 : .35}>
          {month.value != null && <><line x1={x(edge.first) - width / 2} x2={x(edge.last) + width / 2} y1={y(month.value)} y2={y(month.value)} stroke={color} strokeWidth="2.5" />
            <text x={center} y={Math.max(13, y(month.value) - 12)} textAnchor="middle" className={shared.valueLabel} fill="#FFF">{strainFormat(month.value, metric)}</text>
            {change != null && <text x={center} y={Math.min(270, y(month.value) + 18)} textAnchor="middle" className={shared.valueLabel} fill={color}>{change > 0 ? '+' : ''}{change.toFixed(0)}%</text>}</>}
          <text x={center} y="290" textAnchor="middle" className={shared.axis}>{dateLabel(month.end, { month: 'short' })}</text>
        </g>;
      })}
      {!six && [...new Set(labels)].map(index => bars[index] && <text key={index} x={x(index)} y="278" textAnchor="middle" className={shared.axis}>{weekly ? <><tspan x={x(index)}>{dateLabel(bars[index].start, { weekday: 'short' })}</tspan><tspan x={x(index)} dy="14">{Number(bars[index].start.slice(-2))}</tspan></> : grouped ? `${dateLabel(bars[index].start)} – ${dateLabel(bars[index].end)}` : <><tspan x={x(index)}>{dateLabel(bars[index].start, { month: 'short' })}</tspan><tspan x={x(index)} dy="14">{Number(bars[index].start.slice(-2))}</tspan></>}</text>)}
      {!values.length && <text x="190" y="140" textAnchor="middle" className={shared.axis}>No recorded values in this period</text>}
    </svg>
    {embedded && selected != null && <div className={shared.chartReadout} aria-live="polite"><span>{dateLabel(readings[selected].start)}</span><strong>{strainFormat(readings[selected].value, metric)}</strong><button aria-label="Clear chart selection" onClick={() => { setPinned(false); select(null); }}>×</button></div>}
  </div>;
}
