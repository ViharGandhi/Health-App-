'use client';

import { useEffect, useId, useState } from 'react';
import { api } from '@/lib/api';
import type { HeartRatePoint, HealthHeartRateData } from '@/lib/types';
import styles from '@/app/health/page.module.css';

export default function HealthMonitorHeart({ initial }: { initial: HealthHeartRateData }) {
  const id = useId();
  const [updated, setUpdated] = useState<HealthHeartRateData | null>(null);
  const [refreshError, setRefreshError] = useState(false);
  const [selection, setSelection] = useState<{ date: string; time: string } | null>(null);
  const [pinned, setPinned] = useState(false);
  const heart = updated ?? initial;
  const points = heart.heart_rate;
  const selectedIndex = selection?.date === heart.date ? points.findIndex(point => point.time === selection.time) : -1;
  const chosen = selectedIndex < 0 ? null : selectedIndex;
  const reading = chosen == null ? points.at(-1) : points[chosen];
  const latest = heart.latest_heart_rate;
  const offset = latest?.sample_time.match(/([+-]\d{2}:\d{2})$/)?.[1];
  const bpm = chosen == null ? latest?.value : reading?.value;
  const select = (index: number) => setSelection({ date: heart.date, time: points[index].time });
  useEffect(() => {
    let active = true, inFlight = false;
    const refresh = async () => {
      if (document.hidden || inFlight) return;
      inFlight = true;
      try {
        const result = await api.getHealthHeartRate();
        if (active) { setUpdated(result); setRefreshError(false); }
      } catch {
        if (active) setRefreshError(true);
      } finally { inFlight = false; }
    };
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, []);
  const minute = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
  const first = points.length ? minute(points[0].time) : 0;
  const span = points.length ? Math.max(1, minute(points.at(-1)!.time) - first) : 1;
  const values = points.map(point => point.value);
  const low = Math.min(...values), high = Math.max(...values);
  const x = (point: HeartRatePoint) => (minute(point.time) - first) / span * 440;
  const y = (point: HeartRatePoint) => 112 - (point.value - low) / Math.max(24, high - low) * 46;
  const segments: HeartRatePoint[][] = [];
  points.forEach((point, index) => {
    if (!index || minute(point.time) - minute(points[index - 1].time) > 30) segments.push([]);
    segments.at(-1)!.push(point);
  });
  const choose = (event: React.PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const target = (event.clientX - box.left) / box.width * 440;
    select(points.reduce((best, point, index) => Math.abs(x(point) - target) < Math.abs(x(points[best]) - target) ? index : best, 0));
  };
  return <section className={styles.monitorHeart} aria-label="Sampled heart rate">
    {points.length > 0 && <svg className={styles.monitorTrace} viewBox="0 0 440 180" preserveAspectRatio="none" role="slider" tabIndex={0}
      aria-label="Heart rate timeline. Hover, tap, or use arrow keys to explore."
      aria-valuemin={0} aria-valuemax={points.length - 1} aria-valuenow={chosen ?? points.length - 1}
      aria-valuetext={`${reading!.time}: ${Math.round(reading!.value)} bpm, 15-minute median`}
      onPointerMove={event => { if (!pinned) choose(event); }} onPointerLeave={() => { if (!pinned) setSelection(null); }}
      onClick={event => { choose(event); setPinned(true); }} onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); setSelection(null); setPinned(false); }
        else if (['Home', 'End', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
          event.preventDefault(); setPinned(true);
          select(event.key === 'Home' ? 0 : event.key === 'End' ? points.length - 1
            : Math.max(0, Math.min(points.length - 1, (chosen ?? points.length - 1) + (event.key === 'ArrowRight' ? 1 : -1))));
        }
      }}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop stopColor="#0093D1" stopOpacity=".18" /><stop offset="1" stopColor="#0093D1" stopOpacity="0" /></linearGradient></defs>
      {segments.map((segment, index) => {
        const line = segment.map((point, i) => `${i ? 'L' : 'M'}${x(point)},${y(point)}`).join(' ');
        return <g key={index}><path d={`${line} L${x(segment.at(-1)!)},180 L${x(segment[0])},180 Z`} fill={`url(#${id})`} /><path d={line} fill="none" stroke="#159BD4" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {segment.length === 1 && <circle cx={x(segment[0])} cy={y(segment[0])} r="2" fill="#159BD4" />}</g>;
      })}
      {chosen != null && <line x1={x(reading!)} x2={x(reading!)} y1="35" y2="158" stroke="#7CC8EC" strokeDasharray="3 4" />}
    </svg>}
    <div className={styles.bpmCircle} aria-live="polite"><svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 21 3 12C-3 5 7-2 12 5c5-7 15 0 9 7Z" /></svg><strong>{bpm == null ? '—' : Math.round(bpm)}</strong><span>BPM</span></div>
    <p className={styles.sampleCaption}>
      {chosen != null ? `${heart.date} · ${reading!.time} · 15-minute median` : latest ? `${latest.sample_time.slice(0, 10)} · ${latest.sample_time.slice(11, 19)}${offset ? ` UTC${offset}` : ''} · ${heart.is_mock ? 'Sample data' : 'Latest synced'}` : `No heart-rate samples · ${heart.date}`}
      <br />{refreshError ? 'Update failed · Retrying every minute' : 'Updates every minute'}
    </p>
  </section>;
}
