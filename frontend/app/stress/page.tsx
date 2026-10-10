'use client';

import { useEffect, useId, useState } from 'react';
import Link from 'next/link';
import { useLocalDay } from '@/lib/useLocalDay';
import { useStressMonitor } from '@/lib/useStressMonitor';
import { shiftDay } from '@/lib/recovery';
import { stressColors, stressDuration, stressNote, stressTime, type StressLevel } from '@/lib/stress';
import StressChart from '@/components/StressChart';
import ActivityIcon from '@/components/ActivityIcon';
import styles from './page.module.css';

const levels: StressLevel[] = ['low', 'medium', 'high'];

export default function StressPage() {
  const today = useLocalDay(), pattern = useId();
  const [selectedDay, setDay] = useState<string>();
  const [demo, setDemo] = useState<boolean | null>(null);
  const [range, setRange] = useState<7 | 28>(7);
  const day = selectedDay ?? today;
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setDemo(params.get('demo') === 'true');
    const date = params.get('date');
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) setDay(date);
  }, []);
  const { data, error, retry } = useStressMonitor(day, demo, range);
  const current = data?.current;
  return <div className={styles.page}><div className={styles.container}>
    <header className={styles.header}><Link href={demo ? '/?demo=true' : '/'} aria-label="Back to Home">‹</Link><h1>STRESS MONITOR</h1><a href="#stress-method" aria-label="About the stress calculation">ⓘ</a></header>
    <div className={styles.date}><button aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>‹</button><span>{day === today ? 'TODAY' : day}</span><button disabled={day >= today} aria-label="Next day" onClick={() => setDay(shiftDay(day, 1))}>›</button></div>
    {!data || !current ? <section className={styles.notice} role={error ? 'alert' : 'status'}>{error ?? 'Loading stress readings…'}{error && <button onClick={retry}>Retry</button>}</section> : <>
      {data.is_mock && <div className={styles.banner}>SYNTHETIC REPLAY · UNVALIDATED ESTIMATE <Link href="/stress">Live data →</Link></div>}
      <section className={styles.hero} aria-label="Latest stress reading"><div><div className={styles.eyebrow}>{data.is_mock ? 'LATEST SAMPLE' : 'LATEST READING'}</div><strong className={styles.score}>{current.latest_score?.toFixed(1) ?? '—'}<small>/ 3</small></strong></div>
        <div className={styles.latest}><strong style={{ color: current.latest_level ? stressColors[current.latest_level] : '#A6AFB7' }}>{current.latest_level?.toUpperCase() ?? 'UNAVAILABLE'}</strong><span>{current.latest_at ? stressTime(current.latest_at, data.timezone) : stressNote(current)}{current.stale && ' · stale'}</span></div></section>
      <p className={styles.caption}>{stressNote(current)}</p>
      <StressChart key={current.date} data={data} interactive />
      <div className={styles.legend}>{levels.map(level => <span key={level}><i style={{ background: stressColors[level] }} />{level}</span>)}<span><i className={styles.hatched} />Unscored</span></div>
      <p className={styles.caption}>{data.timezone} · Sleep and activity bands show context, not the cause of stress.</p>
      <section className={styles.notice}><strong>{data.is_mock ? 'Synthetic HR + nighttime HRV' : 'HR-based estimate'}</strong><p>{data.is_mock ? 'All readings and HRV coverage are synthetic. This replay illustrates the calculation and missing-data states.' : 'HRV contributions are unavailable because measurement coverage and window timing are unverified. Sleep and daytime scores use valid heart-rate windows.'}</p><p>{current.baseline_leaks ? 'The limited-history reference includes the scored day and may include later dates. These estimates are retrospective.' : 'The personal reference uses earlier days.'} {current.low_confidence && 'The reference is still low confidence.'} Exercise, recovery buffers, and missing HR stay unscored.</p></section>
      <section className={styles.breakdown} aria-label="Daily stress time"><h2>DAILY BREAKDOWN <small>HOURS : MINUTES</small></h2>
        <div className={styles.durationBar}>{levels.map(level => <span key={level} style={{ width: `${current.elapsed_minutes ? current.minutes[level] / current.elapsed_minutes * 100 : 0}%`, background: stressColors[level] }} />)}<span className={styles.hatched} style={{ flex: 1 }} /></div>
        <div className={styles.totals}>{levels.map(level => <div key={level}><span><i style={{ background: stressColors[level] }} />{level}</span><strong>{current.scored_minutes ? stressDuration(current.minutes[level]) : '—'}</strong></div>)}<div><span><i className={styles.hatched} />Unscored</span><strong>{stressDuration(current.unscored_minutes)}</strong></div></div>
        <p className={styles.caption}>{Math.round(current.coverage * 100)}% scored · {stressDuration(current.elapsed_minutes)} elapsed · Average {current.average?.toFixed(1) ?? '—'}. Future time is excluded.</p>
        <div className={styles.averages}><div><span>SLEEP AVERAGE</span><strong>{current.sleep_stress?.toFixed(1) ?? '—'}<small> / 3</small></strong></div><div><span>NON-ACTIVITY AVERAGE</span><strong>{current.non_activity_stress?.toFixed(1) ?? '—'}<small> / 3</small></strong></div></div>
      </section>
      <section className={styles.trends}><div className={styles.trendHeader}><h2>STRESS TRENDS</h2><div>{([7, 28] as const).map(value => <button key={value} aria-pressed={range === value} onClick={() => setRange(value)}>{value === 7 ? 'W' : 'M'}</button>)}</div></div>
        <svg viewBox="0 0 360 160" role="img" aria-label="Daily proportion of low, medium, high and unscored time"><defs><pattern id={pattern} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="6" stroke="#8D969E" strokeOpacity=".35" strokeWidth="2" /></pattern></defs>
          {data.days.map((item, i) => { const width = 332 / data.days.length, left = 16 + i * width; let bottom = 127;
            return <g key={item.date}><title>{item.date}: {Math.round(item.coverage * 100)}% scored; average {item.average?.toFixed(1) ?? 'unavailable'}</title><rect x={left} y="17" width={width - 4} height="110" fill={`url(#${pattern})`} />{levels.map(level => { const height = item.elapsed_minutes ? item.minutes[level] / item.elapsed_minutes * 110 : 0; bottom -= height; return <rect key={level} x={left} y={bottom} width={width - 4} height={height} fill={stressColors[level]} />; })}{(range === 7 || i % 7 === 0 || i === data.days.length - 1) && <text x={left + (width - 4) / 2} y="146" textAnchor="middle">{item.date.slice(8)}</text>}</g>;
          })}</svg>
        <p className={styles.caption}>{data.days[0].date} – {day} · Each bar shows the proportion of elapsed time. Hatched areas are unscored.</p>
      </section>
      <section className={styles.context}><h2>SLEEP & ACTIVITIES</h2>{current.overlays.length ? current.overlays.map((item, i) => <div key={`${item.start}-${i}`}><span className={styles.contextIcon}>{item.kind === 'sleep' ? <svg width="21" height="21" viewBox="0 0 20 20" aria-hidden="true"><path d="M15 1a8 8 0 1 1-12 12A8 8 0 0 0 15 1" fill="currentColor" /></svg> : <ActivityIcon name={item.name} size={21} />}</span><strong>{item.name}</strong><span>{stressTime(item.start, data.timezone)} – {stressTime(item.end, data.timezone)}</span></div>) : <p className={styles.caption}>No recorded sleep or activities in this window.</p>}</section>
      <details className={styles.method} id="stress-method"><summary>How this estimate works</summary><p>This is an independent, unvalidated wellness estimate. WHOOP and Bevel do not publish enough detail to reproduce their scores exactly.</p><p>Filtered HR samples become minute medians, then five-minute windows. The personal HR reference pools sleep and recorded sedentary periods using a 14-day median and robust spread. At least three reference days are required; fewer than seven are marked low confidence. With at least 14 available days, references use prior days only; shorter histories use an explicitly retrospective reference.</p><p>Awake estimates use standardized HR. Verified sleep RMSSD can contribute during sleep, with a small previous-night context term during waking hours. Unknown HRV coverage excludes both contributions. The app maps standardized features to 0–3 using a logistic curve, then applies causal smoothing within continuous sleep or awake segments.</p><p>Low is below 1, medium from 1 to below 2, and high from 2 to 3. These bands, weights and curve parameters are engineering choices, not diagnostic thresholds. Caffeine, heat, posture and illness can raise HR. Synthetic tests verify calculations, not real-world accuracy.</p><p>Missing data and vigorous exercise/recovery remain unscored. Readings older than 15 minutes are withheld from the current score; the timestamp is the measurement time, not the last sync.</p><a href="https://www.whoop.com/us/en/thelocker/introducing-stress-monitor-a-new-way-to-monitor-manage-stress/" target="_blank" rel="noreferrer">WHOOP methodology</a><a href="https://www.bevel.health/blog/stress-monitor" target="_blank" rel="noreferrer">Bevel methodology</a><a href="https://pubmed.ncbi.nlm.nih.gov/38873876/" target="_blank" rel="noreferrer">Peer-reviewed HRV measurement guidance</a></details>
      <a className={styles.preview} href={data.is_mock ? '/stress' : '/stress?demo=true'}>{data.is_mock ? 'Return to connected data' : 'Explore synthetic demo'} →</a>
    </>}
  </div></div>;
}
