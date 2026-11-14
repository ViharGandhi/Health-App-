'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { TrainingLoad, TrainingLoadStatus } from '@/lib/types';
import styles from './TrainingLoadCard.module.css';

const STATUS: Record<TrainingLoadStatus, { label: string; color: string }> = {
  well_below: { label: 'Well below', color: '#6D97B1' },
  below: { label: 'Below', color: '#3299DD' },
  steady: { label: 'Steady', color: '#00D7A1' },
  above: { label: 'Above', color: '#FFA21A' },
  well_above: { label: 'Well above', color: '#FF0026' },
};
const BAND = .15;

/**
 * Apple Watch-style training load in WHOOP-style card: this week's effort × minutes
 * against the usual week. The coloured line is the rolling 7-day load, the white
 * line the usual week before it, the shaded band "steady" (±15%).
 */
export default function TrainingLoadCard({ demo }: { demo: boolean }) {
  const [data, setData] = useState<TrainingLoad | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const load = () => api.getTrainingLoad(demo).then(value => { if (active) setData(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Training load unavailable.'); });
    load();
    window.addEventListener('ojas:dynamic-sync', load);
    return () => { active = false; window.removeEventListener('ojas:dynamic-sync', load); };
  }, [demo]);

  const current = data?.current, state = current ? STATUS[current.status] : null;
  const points = data?.days ?? [];
  const values = points.flatMap(p => [p.week_load, p.usual_week_load == null ? null : p.usual_week_load * (1 + BAND)]).filter((v): v is number => v != null);
  const top = Math.max(1, ...values) * 1.08;
  const x = (i: number) => 4 + i * 312 / Math.max(1, points.length - 1);
  const y = (v: number) => 104 - v / top * 96;
  const line = (pick: (p: TrainingLoad['days'][number]) => number | null) => points.reduce<string[]>((paths, p, i) => {
    const v = pick(p);
    if (v == null) { paths.push(''); return paths; }
    const last = paths.length ? paths[paths.length - 1] : '';
    if (!paths.length || last === '') paths.push(`M${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    else paths[paths.length - 1] = `${last} L${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    return paths;
  }, []).filter(Boolean);
  const band = points.map((p, i) => [i, p.usual_week_load] as const).filter((p): p is readonly [number, number] => p[1] != null);
  const bandPath = band.length > 1 ? `M${band.map(([i, v]) => `${x(i).toFixed(1)},${y(v * (1 + BAND)).toFixed(1)}`).join(' L')} L${[...band].reverse().map(([i, v]) => `${x(i).toFixed(1)},${y(v * (1 - BAND)).toFixed(1)}`).join(' L')} Z` : '';
  const short = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const workouts = data ? data.week_workouts.rated + data.week_workouts.estimated : 0;

  return <section className={styles.card} aria-label="Training load">
    <div className={styles.header}><span>TRAINING LOAD</span><small>LAST 7 DAYS VS USUAL</small></div>
    {!data ? <p className={styles.note} role={error ? 'alert' : 'status'}>{error ?? 'Loading training load…'}</p> : <>
      <div className={styles.status}>
        {state && current ? <><strong style={{ color: state.color }}>{state.label}</strong>
          <span>{current.change > 0 ? '+' : ''}{Math.round(current.change * 100)}% vs your usual week</span></>
          : <><strong className={styles.pending}>Building</strong>
            <span>Needs 4 days with the band this week ({data.worn_days.week}) and 14 in the 3 weeks before ({data.worn_days.usual}).</span></>}
      </div>
      {points.some(p => p.week_load != null) && <svg className={styles.chart} viewBox="0 0 320 124" role="img"
        aria-label="Rolling 7-day training load against your usual week over the last 28 days">
        {bandPath && <path d={bandPath} fill="#FFFFFF12" />}
        {line(p => p.usual_week_load).map((d, i) => <path key={`u${i}`} d={d} fill="none" stroke="#FFFFFFB3" strokeWidth="1.5" strokeDasharray="3 3" />)}
        {line(p => p.week_load).map((d, i) => <path key={`w${i}`} d={d} fill="none" stroke={state?.color ?? '#3299DD'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />)}
        <text x="4" y="121" fill="#7F878D" fontSize="9">{short(points[0].date)}</text>
        <text x="316" y="121" fill="#7F878D" fontSize="9" textAnchor="end">TODAY</text>
      </svg>}
      <div className={styles.legend}><span><i style={{ background: state?.color ?? '#3299DD' }} />Last 7 days</span><span><i className={styles.usual} />Usual week</span><span><i className={styles.band} />Steady range</span></div>
      <p className={styles.note}>{workouts === 0 ? 'No workouts in the last 7 days.'
        : `${workouts} workout${workouts === 1 ? '' : 's'} this week · ${data.week_workouts.rated} rated, ${data.week_workouts.estimated} estimated from heart rate.`}
        {' '}Load is effort × minutes. {data.is_mock ? 'Sample data.' : 'Rate workouts on their activity page to make it yours.'}</p>
    </>}
  </section>;
}
