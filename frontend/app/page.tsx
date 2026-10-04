'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import CircleDial from '@/components/CircleDial';
import RecoveryDemoSwitch from '@/components/RecoveryDemoSwitch';
import { api } from '@/lib/api';
import { useRecoveryAnalytics } from '@/lib/useRecoveryAnalytics';
import { BLUE, dateLabel, localDay, recoveryColor, shiftDay } from '@/lib/recovery';
import type { StrainData } from '@/lib/types';
import styles from './page.module.css';

function formatTime(value?: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: false });
}
function duration(minutes: number | null): string {
  if (minutes == null) return '—';
  const rounded = Math.round(minutes);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}
function UnavailableDialog({ message, onClose }: { message: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className={styles.dialog} onCancel={onClose}><h2>Not available yet</h2><p>{message}</p><button onClick={onClose}>Close</button></dialog>;
}
function Chevron({ reverse = false }: { reverse?: boolean }) {
  return <svg width="7" height="12" viewBox="0 0 7 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={reverse ? { transform: 'rotate(180deg)' } : undefined}><path d="m2 2 4 4-4 4" /></svg>;
}

export default function DashboardPage() {
  const router = useRouter();
  const [day, setDay] = useState<string>();
  const [strain, setStrain] = useState<StrainData | null>(null);
  const [strainError, setStrainError] = useState(false);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const { data, error, demo, changeDemo } = useRecoveryAnalytics('W', day);
  useEffect(() => {
    let active = true;
    setStrain(null); setStrainError(false);
    api.getStrain(day).then(value => { if (active) setStrain(value); }).catch(() => { if (active) setStrainError(true); });
    return () => { active = false; };
  }, [day]);
  const activityMessage = 'Activity logging and live workout recording are not connected yet. Recorded device activities are listed here when available.';
  if (error || strainError) return <div className={styles.errorState} role="alert">Could not load your overview. Please try again.</div>;
  if (!data || !strain) return <div className={styles.pageWrapper}><div className={styles.loading} role="status">Loading your overview…</div></div>;
  const current = data.current;
  const sleep = data.sleep;
  const monitor = data.health_monitor;
  const allWithin = monitor.assessed === monitor.expected && monitor.within === monitor.assessed;
  const monitorColor = allWithin ? '#00DCA0' : '#AEB8C1';
  const recoveryHref = `/recovery${day ? `?date=${day}` : ''}`;
  return <div className={styles.pageWrapper}><div className={styles.container}>
    <header className={styles.topHeader}>
      <div className={styles.headerLeft}><Link className={styles.avatarCircle} href="/health" aria-label="Your health"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg></Link><span className={styles.streakBadge} title="Activity streak unavailable">🔥 <span>—</span></span></div>
      <div className={styles.datePill}><button aria-label="Previous day" onClick={() => setDay(shiftDay(data.range_end, -1))}><Chevron reverse /></button><span>{data.range_end === localDay() ? 'TODAY' : dateLabel(data.range_end)}</span><button aria-label="Next day" disabled={data.range_end >= localDay()} onClick={() => setDay(shiftDay(data.range_end, 1))}><Chevron /></button></div>
      <div className={styles.headerRight} title="Device battery unavailable"><span>—</span><svg width="18" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="7" y="3" width="10" height="18" rx="3" /><path d="M10 0h4m-4 24h4" /></svg></div>
    </header>
    <div className={styles.brandBar}>OJAS</div>
    <section className={styles.dialsSection} aria-label="Daily scores">
      <CircleDial label="SLEEP" value={sleep?.performance ?? 0} displayText={sleep?.performance == null ? '—' : undefined} maxValue={100} color={BLUE} unit="%" size={94} onClick={() => router.push('/sleep')} />
      <CircleDial label="RECOVERY" value={current.score ?? 0} displayText={current.score == null ? '—' : undefined} maxValue={100} color={recoveryColor(current.zone, current.status)} unit="%" size={94} onClick={() => router.push(recoveryHref)} />
      <CircleDial label="STRAIN" value={strain.score_21} displayText={strain.avg_hr == null ? '—' : undefined} maxValue={21} color="#009FE8" size={94} onClick={() => router.push('/strain')} />
    </section>
    <div className={styles.monitorsGrid}>
      <Link className={styles.monitorCard} href="/health"><div className={styles.cardHeaderRow}><span>HEALTH MONITOR</span><Chevron /></div><div className={styles.monitorBody}><span className={styles.checkIconBox} style={{ color: monitorColor }}>{allWithin ? '✓' : '—'}</span><span className={styles.monitorTextStack}><strong style={{ color: monitorColor }}>{allWithin ? 'WITHIN RANGE' : monitor.assessed < monitor.expected ? 'BUILDING RANGE' : 'OUTSIDE RANGE'}</strong><small>{monitor.assessed < monitor.expected ? `${monitor.assessed}/${monitor.expected} Metrics assessed` : `${monitor.within}/${monitor.expected} Metrics${allWithin ? '' : ' within'}`}</small></span></div></Link>
      <button className={styles.monitorCard} onClick={() => setUnavailable('Daytime Stress Monitor has no calculation or data source connected. Sleep Stress is available in the Sleep section.')}><div className={styles.cardHeaderRow}><span>STRESS MONITOR</span><Chevron /></div><div className={styles.monitorBody}><span className={styles.stressScoreBadge}>—</span><span className={styles.monitorTextStack}><strong>UNAVAILABLE</strong><small>No daytime data</small></span></div></button>
    </div>
    <section className={styles.myDaySection}><div className={styles.myDayHeader}><h2>My Day</h2><button className={styles.addButton} aria-label="Add activity" onClick={() => setUnavailable(activityMessage)}>+</button></div>
      <Link className={styles.outlookBanner} href={recoveryHref}><span><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="5" /><path d="M12 0v3m0 18v3M0 12h3m18 0h3M3 3l2 2m14 14 2 2M3 21l2-2M19 5l2-2" /></svg>Your Daily Outlook</span><Chevron /></Link>
      <div className={styles.activitiesContainer}><div className={styles.activitiesHeaderRow}><span>{data.range_end === localDay() ? "TODAY'S ACTIVITIES" : 'ACTIVITIES'}</span><Link href="/strain" aria-label="View activity details">↗</Link></div>
        <Link href="/sleep" className={styles.activityItem}><div className={styles.activityLeftPart}><div className={styles.sleepBadge}><svg width="21" height="21" viewBox="0 0 24 24" fill="currentColor"><path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5z" /></svg><strong>{duration(sleep?.asleep_minutes ?? null)}</strong></div><span className={styles.activityName}>SLEEP</span></div><div className={styles.activityTimeline}><div className={styles.timeStack}><span>{formatTime(sleep?.bed_time)}</span><span>{formatTime(sleep?.wake_time)}</span></div><i /></div></Link>
        {strain.workouts.map((workout, index) => <Link href="/strain" className={styles.activityItem} key={`${workout.activity_name}-${index}`}><div className={styles.activityLeftPart}><div className={`${styles.sleepBadge} ${styles.workoutBadge}`} title="Duration recorded in heart-rate zones"><svg width="20" height="25" viewBox="0 0 24 30" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="13" cy="4" r="2" /><path d="m11 8-3 7 5 4-2 9M11 8l5 5h4M8 15l-4 4m9 0 5 8" /></svg><strong>{Math.round(Object.values(workout.zone_minutes).reduce((sum, minutes) => sum + minutes, 0))}<small>min</small></strong></div><span className={styles.activityName}>{workout.activity_name}</span></div><div className={`${styles.activityTimeline} ${styles.workoutTimeline}`} title="Activity start and end times are not supplied"><div className={styles.timeStack}><span>—</span><span>—</span></div><i /></div></Link>)}
        <div className={styles.actionButtonsRow}><button onClick={() => setUnavailable(activityMessage)}><span>＋</span>ADD ACTIVITY</button><button onClick={() => setUnavailable(activityMessage)}><span>◷</span>START ACTIVITY</button></div>
      </div>
    </section>
    <p className={styles.estimateNote}>{current.estimated ? `Estimated Recovery · ${current.confidence ?? 'building reference'}${current.confidence ? ' confidence' : ''}` : 'Prototype Recovery estimate'}{data.is_mock ? ' · Synthetic sample vitals and sleep; activity uses the existing demo fixture.' : ''}</p>
    {data.is_mock && <RecoveryDemoSwitch value={demo} onChange={changeDemo} />}
    {unavailable && <UnavailableDialog message={unavailable} onClose={() => setUnavailable(null)} />}
  </div></div>;
}
