'use client';

import { useId, useState } from 'react';
import ActivityIcon from './ActivityIcon';
import { stressColors, stressLevel, stressTime, stressUnavailable, type StressData } from '@/lib/stress';
import styles from './StressMonitor.module.css';

export default function StressChart({ data, interactive = false }: { data: StressData; interactive?: boolean }) {
  const { current: day, timezone } = data;
  const [selected, setSelected] = useState<number | null>(null);
  const id = useId();
  const first = Date.parse(day.start), last = Date.parse(interactive ? day.calendar_end : day.end), span = Math.max(last - first, 1);
  const x = (value: string) => 29 + (Date.parse(value) - first) / span * 309;
  const y = (score: number) => 188 - score * 50;
  const point = selected == null ? null : day.points[selected];
  const middle = (start: string, end: string) => (x(start) + x(end)) / 2;
  return <div className={styles.chart}>
    <svg viewBox="0 0 350 220" role="img" aria-labelledby={`${id}-title ${id}-desc`}>
      <title id={`${id}-title`}>{data.is_mock ? 'Synthetic stress replay' : 'Estimated stress'} for {day.date}</title>
      <desc id={`${id}-desc`}>Scale zero to three. Blue is low, green is medium, yellow is high. Gaps are unscored. Shaded bands mark recorded sleep and activities. Times in {timezone}.</desc>
      <defs><pattern id={`${id}-missing`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="6" stroke="#9CA7AF" strokeOpacity=".13" strokeWidth="2" /></pattern></defs>
      {day.overlays.map((item, i) => <g key={`${item.kind}-${i}`}><title>{item.name}: {stressTime(item.start, timezone)}–{stressTime(item.end, timezone)}</title>
        <rect x={x(item.start)} y="38" width={x(item.end) - x(item.start)} height="150" fill={item.kind === 'sleep' ? '#7BA9BD16' : '#009FE818'} />
        <line x1={x(item.start)} x2={x(item.end)} y1="38" y2="38" stroke={item.kind === 'sleep' ? '#7BA9BD' : '#009FE8'} strokeWidth="2" />
        <g transform={`translate(${middle(item.start, item.end) - 9} 10)`} color="#F5F7F8">{item.kind === 'sleep' ? <path d="M14 0a8 8 0 1 1-11 11A8 8 0 0 0 14 0" fill="currentColor" /> : <ActivityIcon name={item.name} size={19} />}</g>
      </g>)}
      {[0, 1, 2, 3].map(value => <g key={value}><line x1="29" x2="338" y1={y(value)} y2={y(value)} stroke="#FFFFFF16" /><text x="4" y={y(value) + 3}>{value}.0</text></g>)}
      {[0, 1, 2, 3].map(i => <g key={i}><line x1={29 + i * 103} x2={29 + i * 103} y1="38" y2="188" stroke="#FFFFFF0B" /><text x={29 + i * 103} y="210" textAnchor={i === 3 ? 'end' : i === 0 ? 'start' : 'middle'}>{stressTime(new Date(first + span * i / 3).toISOString(), timezone)}</text></g>)}
      {day.points.map((p, i) => {
        const next = day.points[i + 1];
        if (p.score == null) return <rect key={p.start} x={x(p.start)} y="38" width={x(p.end) - x(p.start)} height="150" fill={`url(#${id}-missing)`} />;
        const px = middle(p.start, p.end), color = stressColors[stressLevel(p.score)];
        return <g key={p.start}><circle cx={px} cy={y(p.score)} r="1" fill={color} />{next?.score != null && p.end === next.start && (p.state === 'SLEEP') === (next.state === 'SLEEP') && <line x1={px} y1={y(p.score)} x2={middle(next.start, next.end)} y2={y(next.score)} stroke={color} strokeWidth="1.8" strokeLinecap="round" />}</g>;
      })}
      {!day.points.length && <><rect x="29" y="39" width={x(day.end) - 29} height="148" fill={`url(#${id}-missing)`} /><rect x="53" y="94" width="267" height="38" rx="7" fill="#272E34" /><text className={styles.empty} x="186" y="117" textAnchor="middle">No usable HR readings</text></>}
      {point && <line x1={middle(point.start, point.end)} x2={middle(point.start, point.end)} y1="34" y2="190" stroke="#FFFFFF99" strokeDasharray="3 3" />}
      <line x1={x(day.end)} x2={x(day.end)} y1="29" y2="196" stroke="#BBC2C7" strokeDasharray="3 3" /><circle cx={x(day.end)} cy="196" r="2" fill="#FFF" />
    </svg>
    {interactive && day.points.length > 0 && <div className={styles.scrubber}><label htmlFor={`${id}-time`}>Explore time</label><input id={`${id}-time`} type="range" min="0" max={day.points.length - 1} value={selected ?? day.points.length - 1} onChange={e => setSelected(Number(e.target.value))} />
      <output>{point ? `${stressTime(point.start, timezone)}–${stressTime(point.end, timezone)} · ${point.score == null ? stressUnavailable(point.reason) : `${stressLevel(point.score).toUpperCase()} ${point.score.toFixed(1)} · ${point.source === 'hr_only' ? 'HR-only estimate' : 'HR + verified nighttime HRV'}`}` : 'Select a time to inspect its reading'}</output></div>}
  </div>;
}
