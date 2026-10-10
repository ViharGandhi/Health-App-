'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { clockDuration, ZONE_COLORS } from '@/lib/activity';
import ActivityIcon from '@/components/ActivityIcon';
import type { ActivityData } from '@/lib/types';
import styles from './page.module.css';

function Comparison({ value, current, unit, digits = 0 }: { value: number | null; current?: number | null; unit?: string; digits?: number }) {
  const direction = value == null || current == null ? '' : Math.abs(current - value) < .05 ? '• ' : current > value ? '▲ ' : '▼ ';
  return <small className={styles.comparison} title="Prior 30-day average for the same activity type">{value == null ? '—' : `${direction}${value.toFixed(digits)}${unit ?? ''}`}</small>;
}

function HeartRateChart({ data }: { data: ActivityData }) {
  const points = data.heart_rate;
  if (points.length < 2) return <div className={styles.emptyChart}>No usable heart-rate trace for this activity</div>;
  const start = Date.parse(data.start), end = Date.parse(data.end);
  const low = Math.floor(Math.min(...points.map(p => p.bpm)) / 25) * 25;
  const high = Math.max(low + 50, Math.ceil(Math.max(...points.map(p => p.bpm)) / 25) * 25);
  const x = (stamp: string) => 28 + (Date.parse(stamp) - start) / Math.max(1, end - start) * 336;
  const y = (bpm: number) => 208 - (bpm - low) / (high - low) * 183;
  const paths: string[][] = [];
  points.forEach((p, index) => {
    if (!index || Date.parse(p.timestamp) - Date.parse(points[index - 1].timestamp) > 300000) paths.push([]);
    paths.at(-1)!.push(`${x(p.timestamp).toFixed(2)},${y(p.bpm).toFixed(2)}`);
  });
  return <svg className={styles.hrChart} viewBox="0 0 380 242" role="img" aria-label="Recorded activity heart rate over time">
    <defs><linearGradient id="activityHR" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#009FE8" stopOpacity=".26" /><stop offset="1" stopColor="#009FE8" stopOpacity="0" /></linearGradient></defs>
    {Array.from({ length: (high - low) / 25 + 1 }, (_, i) => low + i * 25).map(tick => <g key={tick}><line x1="28" x2="364" y1={y(tick)} y2={y(tick)} stroke="#FFFFFF09" /><text x="3" y={y(tick) + 3} fill="#A3ABB3" fontSize="9">{tick}</text></g>)}
    {[28, 112, 196, 280, 364].map(pos => <line key={pos} x1={pos} x2={pos} y1="25" y2="208" stroke="#00000015" />)}
    {paths.map((p, i) => <g key={i}><path d={`M${p.join(' L')} L${p.at(-1)!.split(',')[0]},218 L${p[0].split(',')[0]},218 Z`} fill="url(#activityHR)" /><path d={`M${p.join(' L')}`} fill="none" stroke="#009FE8" strokeWidth="1.6" /></g>)}
    {[28, 364].map(pos => <g key={pos}><line x1={pos} x2={pos} y1="25" y2="220" stroke="#B1BCC555" strokeDasharray="3 3" /><circle cx={pos} cy="220" r="2" fill="#FFF" /></g>)}
    <text x="28" y="238" fill="#D8DDE1" fontSize="10">{data.start.slice(11, 16)}</text><text x="364" y="238" textAnchor="end" fill="#D8DDE1" fontSize="10">{data.end.slice(11, 16)}</text>
  </svg>;
}

export default function ActivityPage() {
  const [data, setData] = useState<ActivityData | null>(null), [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null), [banner, setBanner] = useState(true), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    let active = true;
    setError(null);
    const id = params.get('id');
    if (!id) { setError('Choose an activity from My Day.'); return; }
    api.getActivity(id, params.get('date') ?? undefined, params.get('demo') === 'true', params.get('source') ?? 'home').then(value => { if (active) setData(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Activity unavailable.'); });
    return () => { active = false; };
  }, [attempt]);
  const back = data ? `/?${new URLSearchParams({ date: data.date, ...(data.is_mock ? { demo: 'true' } : {}) })}` : '/';
  const strength = /weight|strength|resistance/i.test(`${data?.activity_name} ${data?.exercise_type}`);
  const routeActivity = /walk|run|jog|hike|cycl/i.test(`${data?.activity_name} ${data?.exercise_type}`);
  const statOrder = strength ? { avg_hr: 0, max_hr: 1, calories: 2 } : { calories: 0, avg_hr: 1, max_hr: 2 };
  return <div className={styles.page}><div className={styles.container}>
    <header className={styles.header}><Link href={back} aria-label="Back to My Day"><svg width="12" height="21" viewBox="0 0 12 21" fill="none" stroke="currentColor" strokeWidth="2"><path d="m10 2-8 8.5 8 8.5" /></svg></Link><ActivityIcon name={data?.activity_name ?? 'Activity'} type={data?.exercise_type} size={29} /><div><h1>{data?.activity_name ?? 'ACTIVITY'}</h1><small>{data ? `${data.start.slice(11, 16)} to ${data.end.slice(11, 16)}` : 'Recorded workout'}</small></div><button aria-label="Activity options" onClick={() => setInfo('Activity editing and exercise logging are not connected yet.')}>•••</button></header>
    {!data ? <div className={styles.loading} role={error ? 'alert' : 'status'}>{error ?? 'Loading activity…'}{error && <button onClick={() => setAttempt(v => v + 1)}>Retry</button>}</div> : <>
      {data.is_mock && <p className={styles.sample}>SAMPLE DATA · Cardio Strain calculated from synthetic HR. Additional example values are illustrative.</p>}
      {strength && banner && <section className={styles.banner}><button className={styles.close} aria-label="Dismiss workout information" onClick={() => setBanner(false)}>×</button><h2>Get More from Your Workouts</h2><p>{data.is_mock ? 'Preview how strength sessions appear. Muscular contribution is an illustrative example; this score uses cardio load only.' : 'Cardio Strain is estimated from your heart rate. Muscular load and exercise logging are not available yet.'}</p><button onClick={() => setInfo('Adding individual exercises is not available yet.')}>ADD EXERCISES →</button></section>}
      <section className={styles.scores}><div><strong className={styles.strain}>{data.strain?.toFixed(1) ?? '—'}</strong><Comparison value={data.averages.strain} current={data.strain} digits={1} /><h2>ACTIVITY STRAIN</h2><small className={styles.caption}>Estimated cardio</small></div>
        {strength ? <div className={styles.split}><div><span>CARDIO</span><span>MUSCULAR</span></div><div className={styles.splitBar}>{data.muscular_split && <i style={{ left: `${data.muscular_split.cardio}%` }} />}</div><div><strong>{data.muscular_split ? `${data.muscular_split.cardio}%` : '—'}</strong><strong>{data.muscular_split ? `${data.muscular_split.muscular}%` : '—'}</strong></div><small>{data.muscular_split ? 'Illustrative split' : 'Split unavailable'}</small></div>
          : <div><strong>{data.steps?.toLocaleString('en-US') ?? '—'}</strong><Comparison value={data.averages.steps} current={data.steps} /><h2>ACTIVITY STEPS</h2><small className={styles.caption}>{data.is_mock ? 'Illustrative example' : 'Not supplied for this workout'}</small></div>}
      </section>
      <HeartRateChart data={data} />
      <div className={styles.chartMeta}><span><i /> TYPICAL RANGE{!data.is_mock && <small> unavailable</small>}</span><span>DURATION <b>{clockDuration(data.duration_min, true)}</b></span></div>
      <section className={styles.zones} aria-label="Heart-rate zones">{data.zones.map(zone => <div key={zone.zone} className={`${styles.zone} ${zone.minutes === 0 ? styles.zero : ''}`}><div className={styles.zoneTop}><strong>ZONE {zone.zone}</strong><span>{zone.low == null ? 'HRMAX NEEDED' : zone.zone === 0 ? `<${Math.round(zone.high!)} BPM` : zone.zone === 5 ? `${Math.round(zone.low)}+ BPM` : `${Math.round(zone.low)}–<${Math.round(zone.high!)} BPM`}</span><b style={{ color: ZONE_COLORS[zone.zone] }}>{zone.percent == null ? '—' : `${Math.round(zone.percent)}%`}</b><time>{clockDuration(zone.minutes, true)}</time></div>
        {zone.minutes !== 0 && <div className={styles.zoneTrack}>{zone.typical && <i className={styles.typical} style={{ left: `${zone.typical.low}%`, width: `${zone.typical.high - zone.typical.low}%` }} />}<span style={{ width: `${zone.percent ?? 0}%`, background: ZONE_COLORS[zone.zone] }} /></div>}
      </div>)}</section>
      <p className={styles.note}>Zones use the app&apos;s existing estimated HRmax thresholds (50/60/70/80/90%). <button onClick={() => setInfo('HRmax is estimated as 208 − 0.7 × age. Zone 0 is below 50%; Zones 1–5 begin at 50%, 60%, 70%, 80%, and 90%. These are the app’s thresholds, which differ from the screenshot examples.')}>View HR Settings</button></p>
      <p className={styles.note}>HR coverage {Math.round(data.coverage * 100)}%{data.unrecorded_minutes > .01 && ` · ${clockDuration(data.unrecorded_minutes, true)} without usable HR; gaps are excluded.`} {data.is_mock ? 'Dashed typical ranges are synthetic examples.' : 'Personal typical ranges are not calculated.'}</p>
      <div className={styles.statsHeading}><h2>KEY STATISTICS</h2><span>VS. 30 DAY AVERAGE</span></div>
      <section className={styles.stats} aria-label="Key statistics">{[
        { key: 'calories' as const, title: 'CALORIES', icon: '♨', value: data.calories, unit: 'cals' },
        { key: 'avg_hr' as const, title: 'AVG HR', icon: '♡', value: data.avg_hr, unit: 'bpm' },
        { key: 'max_hr' as const, title: 'MAX HR', icon: '♡↑', value: data.max_hr, unit: 'bpm' },
      ].sort((a, b) => statOrder[a.key] - statOrder[b.key]).map(stat => <article key={stat.key}><h3><span>{stat.icon}</span>{stat.title}</h3><p><strong>{stat.value == null ? '—' : Math.round(stat.value)}</strong><span>{stat.unit}</span></p><Comparison value={data.averages[stat.key]} current={stat.value} unit={stat.unit} /><small className={styles.caption}>{stat.value == null ? 'Unavailable' : stat.key === 'calories' && data.is_mock ? 'Illustrative example' : data.is_mock ? 'Sample heart rate' : 'Recorded heart rate'}</small></article>)}</section>
      <p className={styles.note}>{data.comparison_count ? `${data.comparison_count} recorded ${data.activity_name.toLowerCase()} sessions in the prior 30 days.` : 'No matching recorded sessions in the prior 30 days.'} Swipe statistics to see more.</p>
      {routeActivity && <section className={styles.route}><h2>ROUTE {data.route_sample && <small>ILLUSTRATIVE SAMPLE</small>}</h2>{data.route_sample ? <svg viewBox="0 0 360 200" role="img" aria-label="Illustrative sample route, not a recorded location"><rect width="360" height="200" fill="#E4E5E3" /><path d="M-20 54H390M75-20V220M235-20V220M-20 155H390" stroke="#FFF" strokeWidth="15" /><path d="m15 10 330 180" stroke="#C1C9CD" strokeWidth="28" /><path d="m81 53 34 24 119-23 18 32-54 60-96 4 30-59-51-38" fill="none" stroke="#009FE8" strokeWidth="4" /><circle cx="81" cy="53" r="6" fill="#00BFA0" /><circle cx="101" cy="150" r="6" fill="#009FE8" /><text x="18" y="187" fill="#657179" fontSize="11">Synthetic route · no location data</text></svg> : <div className={styles.routeEmpty}>No recorded route available</div>}</section>}
      <section className={styles.insight}><ActivityIcon name={data.activity_name} type={data.exercise_type} /><p>{data.strain != null ? `This ${data.activity_name.toLowerCase()} contributed ${data.strain.toFixed(1)} estimated cardio Strain. Activity scores are not additive.` : 'This session has no calculated cardio Strain.'}</p></section>
    </>}
    {info && <div className={styles.modalBackdrop}><section role="dialog" aria-modal="true" aria-label="Activity information" className={styles.modal}><p>{info}</p><button onClick={() => setInfo(null)}>Close</button></section></div>}
  </div></div>;
}
