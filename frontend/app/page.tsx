'use client';

/**
 * Dashboard — Home page (/)
 * Ojas dashboard with sample data and metric detail links.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import CircleDial from '@/components/CircleDial';
import MockBanner from '@/components/MockBanner';
import MetricNav from '@/components/MetricNav';
import { api } from '@/lib/api';
import type { DashboardData } from '@/lib/types';
import styles from './page.module.css';

const RECOVERY_COLOR: Record<string, string> = {
  green:  '#16EC06',
  yellow: '#FFDE00',
  red:    '#FF0026',
};

function formatTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  if (dateStr.includes('AM') || dateStr.includes('PM')) {
    return dateStr;
  }
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const h = d.getHours();
  const m = d.getMinutes().toString().padStart(2, '0');
  const ampm = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${h12}:${m} ${ampm}`;
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState(false);
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [action, setAction] = useState<'add' | 'timer' | 'unavailable' | null>(null);
  const [activityName, setActivityName] = useState('');
  const [activityMinutes, setActivityMinutes] = useState('30');
  const [demoActivities, setDemoActivities] = useState<{ name: string; minutes: number }[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    api.getDashboard()
      .then(setData)
      .catch(() => setError(true));
    try {
      const saved = window.localStorage.getItem('ojas-demo-activities');
      if (saved) setDemoActivities(JSON.parse(saved));
    } catch { /* Ignore invalid local demo storage. */ }
  }, []);

  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const openAction = (next: 'add' | 'timer') => {
    setAction(data?.is_mock ? next : 'unavailable');
  };

  const addDemoActivity = () => {
    const minutes = Number(activityMinutes);
    if (!activityName.trim() || !Number.isFinite(minutes) || minutes <= 0) return;
    const next = [...demoActivities, { name: activityName.trim(), minutes }];
    setDemoActivities(next);
    window.localStorage.setItem('ojas-demo-activities', JSON.stringify(next));
    setActivityName('');
    setAction(null);
  };

  const stopTimer = () => {
    const next = [...demoActivities, {
      name: activityName.trim() || 'Timed activity',
      minutes: Math.max(0.1, Math.round((elapsed / 60) * 10) / 10),
    }];
    setDemoActivities(next);
    window.localStorage.setItem('ojas-demo-activities', JSON.stringify(next));
    setStartedAt(null);
    setElapsed(0);
    setActivityName('');
    setAction(null);
  };

  const removeDemoActivity = (index: number) => {
    const next = demoActivities.filter((_, position) => position !== index);
    setDemoActivities(next);
    window.localStorage.setItem('ojas-demo-activities', JSON.stringify(next));
  };

  if (error) {
    return (
      <div className={styles.errorState}>
        <p>Could not connect to backend.</p>
        <p className="text-secondary" style={{ fontSize: 13, marginTop: 8 }}>
          Make sure the FastAPI server is running on port 8000.
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.loading}>
        <div className={styles.loadingDials}>
          <div className="skeleton" style={{ width: 94, height: 94, borderRadius: '50%' }} />
          <div className="skeleton" style={{ width: 116, height: 116, borderRadius: '50%' }} />
          <div className="skeleton" style={{ width: 94, height: 94, borderRadius: '50%' }} />
        </div>
      </div>
    );
  }

  const { recovery, sleep, strain } = data;
  const recoveryColor = RECOVERY_COLOR[recovery.status] ?? '#16EC06';
  const sleepColor = '#7BA1BB';
  const strainColor = '#0093E7';

  const sleepHours = Math.floor(sleep.total_sleep_hours);
  const sleepMinutes = Math.round((sleep.total_sleep_hours % 1) * 60).toString().padStart(2, '0');

  return (
    <div className={styles.pageWrapper}>
      <MockBanner isMock={data.is_mock} />

      <div className={styles.container}>
        <MetricNav active="overview" isMock={data.is_mock}>

        {/* -- Three Dials: SLEEP | RECOVERY | STRAIN --------- */}
        <section className={styles.dialsSection} aria-label="Fitness Dials">
          {/* SLEEP DIAL (Left) */}
          <div className={styles.dialCol}>
            <CircleDial
              label="SLEEP"
              value={sleep.score}
              maxValue={100}
              color={sleepColor}
              unit="%"
              size={94}
              onClick={() => router.push('/sleep')}
              showChevron
            />
          </div>

          {/* RECOVERY DIAL (Center — Primary & Larger) */}
          <div className={styles.dialColCenter}>
            <CircleDial
              label="RECOVERY"
              value={recovery.score}
              maxValue={100}
              color={recoveryColor}
              unit="%"
              size={116}
              onClick={() => router.push('/recovery')}
              showChevron
              isPrimary
            />
          </div>

          {/* STRAIN DIAL (Right) */}
          <div className={styles.dialCol}>
            <CircleDial
              label="STRAIN"
              value={strain.score_21}
              maxValue={21}
              color={strainColor}
              size={94}
              onClick={() => router.push('/strain')}
              showChevron
            />
          </div>
        </section>

        <div className={styles.insightCard}>
          <h2>{data.is_mock ? 'Sample day' : 'Your day'}</h2>
          <p>{data.is_mock
            ? 'Explore the sample Sleep, Recovery, and Strain readings. Connect a supported device when Google Health access is available.'
            : 'Open each metric to see the measurements behind today’s scores.'}</p>
        </div>

        {/* -- My Day Section -------------------------------- */}
        <section className={styles.myDaySection}>
          <h2 className={styles.myDayTitle}>My Day</h2>

          {/* Daily Outlook Banner */}
          <button type="button" className={styles.outlookBanner} onClick={() => setOutlookOpen((open) => !open)} aria-expanded={outlookOpen}>
            <div className={styles.outlookLeft}>
              <div className={styles.whoopIconPill}>O</div>
              <div className={styles.outlookContent}>
                <span className={styles.sunIcon}>☼</span>
                <span className={styles.outlookLabel}>Your Daily Outlook</span>
              </div>
            </div>
            <span className={styles.outlookChevron}>›</span>
          </button>
          {outlookOpen && (
            <div className={styles.outlookDetail}>
              <strong>{data.is_mock ? 'Demo outlook' : 'Today’s overview'}</strong>
              <p>Sleep {Math.round(sleep.score)}%, Recovery {Math.round(recovery.score)}%, Strain {strain.score_21.toFixed(1)}. Open a metric for its breakdown.</p>
              {data.is_mock && <small>Sample values only. Activity entries below do not change calculated scores.</small>}
            </div>
          )}

          {/* Today's Activities */}
          <div className={styles.activitiesContainer}>
            <div className={styles.activitiesHeaderRow}>
              <span className={styles.activitiesSectionTitle}>TODAY&apos;S ACTIVITIES</span>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#8E95A2" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            </div>

            {/* Sleep Row */}
            <button type="button" className={styles.activityItem} onClick={() => router.push('/sleep')}>
              <div className={styles.activityLeftPart}>
                <div className={styles.sleepBadge}>
                  <span className={styles.moonIcon}>☽</span>
                  <span className={styles.sleepTimeText}>{sleepHours}:{sleepMinutes}</span>
                </div>
                <span className={styles.activityName}>SLEEP</span>
              </div>

              <div className={styles.activityTimeline}>
                <div className={styles.timeStack}>
                  <span className={styles.timeVal}>{formatTime(sleep.sleep_start)}</span>
                  <span className={styles.timeVal}>{formatTime(sleep.sleep_end)}</span>
                </div>
                <div className={styles.timelineBar} />
              </div>
            </button>

            {demoActivities.map((activity, index) => (
              <div className={styles.demoActivity} key={`${activity.name}-${index}`}>
                <span>{activity.name}</span><span>{activity.minutes} min · DEMO</span>
                <button type="button" onClick={() => removeDemoActivity(index)} aria-label={`Remove ${activity.name}`}>×</button>
              </div>
            ))}

            {/* Action Buttons */}
            <div className={styles.actionButtonsRow}>
              <button type="button" className={styles.whoopBtn} onClick={() => openAction('add')}>
                <span className={styles.plusSign}>+</span>
                <span>ADD ACTIVITY</span>
              </button>
              <button type="button" className={styles.whoopBtn} onClick={() => openAction('timer')}>
                <span className={styles.timerIcon}>⏱</span>
                <span>START ACTIVITY</span>
              </button>
            </div>
          </div>
        </section>
      <button type="button" className={styles.floatingActionBtn} onClick={() => openAction('add')} aria-label="Add activity">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>
        </MetricNav>
      </div>

      {action && (
        <div className={styles.sheetBackdrop} onClick={() => setAction(null)}>
          <section className={styles.actionSheet} onClick={(event) => event.stopPropagation()} aria-label="Activity action">
            <div className={styles.sheetHeader}>
              <h2>{action === 'add' ? 'Add demo activity' : action === 'timer' ? 'Demo activity timer' : 'Activity logging unavailable'}</h2>
              <button type="button" onClick={() => setAction(null)} aria-label="Close">×</button>
            </div>
            {action === 'unavailable' ? <p>Activity logging is available in demo mode only until a device integration is ready.</p> : (
              <>
                <label>Activity name<input value={activityName} onChange={(event) => setActivityName(event.target.value)} placeholder="Walking" /></label>
                {action === 'add' ? (
                  <>
                    <label>Duration in minutes<input type="number" min="1" value={activityMinutes} onChange={(event) => setActivityMinutes(event.target.value)} /></label>
                    <button type="button" className={styles.sheetSubmit} onClick={addDemoActivity} disabled={!activityName.trim() || Number(activityMinutes) <= 0}>Add to My Day</button>
                  </>
                ) : (
                  <>
                    <div className={styles.timerReadout}>{Math.floor(elapsed / 60).toString().padStart(2, '0')}:{(elapsed % 60).toString().padStart(2, '0')}</div>
                    <button type="button" className={styles.sheetSubmit} onClick={startedAt === null ? () => setStartedAt(Date.now()) : stopTimer}>{startedAt === null ? 'Start timer' : 'Stop and save'}</button>
                  </>
                )}
                <p>Demo entries do not alter Sleep, Recovery, or Strain calculations.</p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
