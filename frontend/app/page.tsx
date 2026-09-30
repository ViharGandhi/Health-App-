'use client';

/**
 * Dashboard — Home page (/)
 * WHOOP-style dark UI with three circle dials, health/stress monitors,
 * My Day section, Today's Activities, and Tonight's Sleep.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import CircleDial from '@/components/CircleDial';
import MockBanner from '@/components/MockBanner';
import { api } from '@/lib/api';
import type { DashboardData } from '@/lib/types';
import styles from './page.module.css';

const RECOVERY_COLOR: Record<string, string> = {
  green:  '#04d98b',
  yellow: '#f5c518',
  red:    '#ff3b3b',
};

function formatTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  const h = d.getHours();
  const m = d.getMinutes().toString().padStart(2, '0');
  const ampm = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${h12}:${m} ${ampm}`;
}

function formatDay(): string {
  const d = new Date();
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  return days[d.getDay()];
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getDashboard()
      .then(setData)
      .catch(() => setError(true));
  }, []);

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
          {[0, 1, 2].map(i => (
            <div key={i} className="skeleton" style={{ width: 110, height: 110, borderRadius: '50%' }} />
          ))}
        </div>
      </div>
    );
  }

  const { recovery, sleep, strain } = data;
  const recoveryColor = RECOVERY_COLOR[recovery.status] ?? RECOVERY_COLOR.green;
  const sleepColor = '#04d98b';
  const strainColor = '#00a1e4';

  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });

  return (
    <div className={styles.pageWrapper}>
      <MockBanner isMock={data.is_mock} />

      <div className="page">
        {/* -- WHOOP Brand ----------------------------------- */}
        <div className={styles.brandHeader}>
          <span className={styles.brandName}>WHOOP</span>
        </div>

        {/* -- Three Dials ----------------------------------- */}
        <div className={`${styles.dialsRow} fade-in`}>
          <CircleDial
            label="SLEEP"
            value={sleep.score}
            maxValue={100}
            color={sleepColor}
            unit="%"
            size={110}
            onClick={() => router.push('/sleep')}
            showChevron
          />
          <CircleDial
            label="RECOVERY"
            value={recovery.score}
            maxValue={100}
            color={recoveryColor}
            unit="%"
            size={130}
            onClick={() => router.push('/recovery')}
            showChevron
            isPrimary
          />
          <CircleDial
            label="STRAIN"
            value={strain.score_21}
            maxValue={21}
            color={strainColor}
            size={110}
            onClick={() => router.push('/strain')}
            showChevron
          />
        </div>

        {/* -- Health & Stress Monitors ---------------------- */}
        <div className={`${styles.monitorsRow} fade-in fade-in-delay-1`}>
          <div className={styles.monitorCard} onClick={() => router.push('/recovery')}>
            <div className={styles.monitorHeader}>
              <span className={styles.monitorTitle}>HEALTH MONITOR</span>
              <span className={styles.monitorChevron}>›</span>
            </div>
            <div className={styles.monitorContent}>
              <span className={styles.monitorIcon}>✅</span>
              <div className={styles.monitorInfo}>
                <span className={styles.monitorStatus} style={{ color: '#04d98b' }}>WITHIN RANGE</span>
                <span className={styles.monitorSub}>5/5 Metrics</span>
              </div>
            </div>
          </div>

          <div className={styles.monitorCard} onClick={() => router.push('/strain')}>
            <div className={styles.monitorHeader}>
              <span className={styles.monitorTitle}>STRESS MONITOR</span>
            </div>
            <div className={styles.monitorContent}>
              <span className={styles.monitorIcon}>📊</span>
              <div className={styles.monitorInfo}>
                <span className={styles.monitorStatus} style={{ color: '#f5c518' }}>HIGH</span>
                <span className={styles.monitorSub}>{strain.score_21.toFixed(1)} · {timeStr}</span>
              </div>
            </div>
          </div>
        </div>

        {/* -- My Day ---------------------------------------- */}
        <div className={`${styles.myDaySection} fade-in fade-in-delay-1`}>
          <h2 className={styles.myDayTitle}>My Day</h2>
          <div className={styles.dividerLine} />
          
          <div className={styles.dailyOutlook}>
            <span className={styles.outlookIcon}>✨</span>
            <span className={styles.outlookText}>Your Daily Outlook</span>
          </div>
        </div>

        {/* -- Today's Activities ----------------------------- */}
        <div className={`${styles.activitiesSection} fade-in fade-in-delay-2`}>
          <p className={styles.activitiesHeader}>TODAY&apos;S ACTIVITIES</p>

          {/* Sleep Activity */}
          <div className={styles.activityRow}>
            <div className={styles.activityLeft}>
              <div className={styles.activityIconWrap} style={{ background: 'rgba(4,217,139,0.15)' }}>
                <span className={styles.activityIcon}>🌙</span>
              </div>
              <div className={styles.activityMeta}>
                <span className={styles.activityValue}>{sleep.total_sleep_hours.toFixed(0)}:{Math.round((sleep.total_sleep_hours % 1) * 60).toString().padStart(2, '0')}</span>
                <span className={styles.activityLabel}>SLEEP</span>
              </div>
            </div>
            <div className={styles.activityRight}>
              <span className={styles.activityTime}>[{formatDay()}] {sleep.sleep_start ? formatTime(sleep.sleep_start) : '10:50 PM'}</span>
              <span className={styles.activityTimeSub}>{sleep.sleep_end ? formatTime(sleep.sleep_end) : '8:48 AM'}</span>
            </div>
          </div>

          {/* Running/Workout Activity */}
          {strain.workouts.length > 0 ? (
            strain.workouts.map((w, i) => (
              <div key={i} className={styles.activityRow}>
                <div className={styles.activityLeft}>
                  <div className={styles.activityIconWrap} style={{ background: 'rgba(0,161,228,0.15)' }}>
                    <span className={styles.activityIcon}>🏃</span>
                  </div>
                  <div className={styles.activityMeta}>
                    <span className={styles.activityValue}>{w.strain.toFixed(1)}</span>
                    <span className={styles.activityLabel}>{w.activity_name.toUpperCase()}</span>
                  </div>
                </div>
                <div className={styles.activityRight}>
                  <span className={styles.activityTime}>{timeStr}</span>
                </div>
              </div>
            ))
          ) : (
            <div className={styles.activityRow}>
              <div className={styles.activityLeft}>
                <div className={styles.activityIconWrap} style={{ background: 'rgba(0,161,228,0.15)' }}>
                  <span className={styles.activityIcon}>🏃</span>
                </div>
                <div className={styles.activityMeta}>
                  <span className={styles.activityValue}>{strain.score_21.toFixed(1)}</span>
                  <span className={styles.activityLabel}>ACTIVITY</span>
                </div>
              </div>
              <div className={styles.activityRight}>
                <span className={styles.activityTime}>{timeStr}</span>
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className={styles.activityActions}>
            <button className={styles.actionBtn}>
              <span className={styles.actionPlus}>+</span> ADD ACTIVITY
            </button>
            <button className={styles.actionBtn}>
              <span className={styles.actionTimer}>⏱</span> START ACTIVITY
            </button>
          </div>
        </div>

        {/* -- Tonight's Sleep -------------------------------- */}
        <div className={`${styles.tonightSection} fade-in fade-in-delay-3`}>
          <p className={styles.tonightHeader}>TONIGHT&apos;S SLEEP</p>
          <div className={styles.tonightCard}>
            <div className={styles.tonightInfo}>
              <span className={styles.tonightLabel}>Sleep Need</span>
              <span className={styles.tonightValue}>{sleep.sleep_need_hours.toFixed(1)}h</span>
            </div>
            {sleep.sleep_debt_hours > 0 && (
              <div className={styles.tonightInfo}>
                <span className={styles.tonightLabel}>Sleep Debt</span>
                <span className={styles.tonightValue} style={{ color: '#ff3b3b' }}>{sleep.sleep_debt_hours.toFixed(1)}h</span>
              </div>
            )}
            <div className={styles.tonightInfo}>
              <span className={styles.tonightLabel}>Recommended</span>
              <span className={styles.tonightValue}>{(sleep.sleep_need_hours + sleep.sleep_debt_hours).toFixed(1)}h</span>
            </div>
          </div>
        </div>

        {/* -- Training Recommendation ----------------------- */}
        <div className={`${styles.recCard} fade-in fade-in-delay-3`}>
          <div className={styles.recHeader}>
            <span className={styles.recPill} style={{ 
              background: `${recoveryColor}20`, 
              color: recoveryColor 
            }}>
              {recovery.status === 'green' ? '✅ Peak' : recovery.status === 'yellow' ? '⚠️ Moderate' : '🛑 Rest'}
            </span>
            <span className={styles.recScore}>{Math.round(recovery.score)}%</span>
          </div>
          <p className={styles.recText}>{recovery.training_recommendation}</p>
        </div>
      </div>
    </div>
  );
}
