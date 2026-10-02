'use client';

/**
 * Dashboard — Home page (/)
 * Ojas dashboard with a dark fitness overview:
 * - Top header with Avatar, streak, `< TODAY >` pill, and strap battery
 * - Ojas name above three Sleep, Recovery, and Strain dials
 * - Health Monitor & Stress Monitor side-by-side
 * - My Day with "Your Daily Outlook" and "Today's Activities"
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import CircleDial from '@/components/CircleDial';
import MockBanner from '@/components/MockBanner';
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
          <div className="skeleton" style={{ width: 94, height: 94, borderRadius: '50%' }} />
          <div className="skeleton" style={{ width: 116, height: 116, borderRadius: '50%' }} />
          <div className="skeleton" style={{ width: 94, height: 94, borderRadius: '50%' }} />
        </div>
      </div>
    );
  }

  const { recovery, sleep, strain } = data;
  const recoveryColor = data.is_mock ? RECOVERY_COLOR[recovery.status] ?? '#8E95A2' : '#67AEE6';
  const sleepColor = '#7BA1BB';
  const strainColor = '#0093E7';

  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });

  const sleepHours = Math.floor(sleep.total_sleep_hours);
  const sleepMinutes = Math.round((sleep.total_sleep_hours % 1) * 60).toString().padStart(2, '0');

  return (
    <div className={styles.pageWrapper}>
      <MockBanner isMock={data.is_mock} />

      <div className={styles.container}>
        {/* -- Status Header (WHOOP top bar) ---------------- */}
        <header className={styles.topHeader}>
          <div className={styles.headerLeft}>
            <div className={styles.avatarCircle}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
          </div>

          <div className={styles.datePill}><span className={styles.pillText}>TODAY</span></div>

          <button className={styles.headerRight} type="button" onClick={() => router.push('/connect')} aria-label="Connection settings">
            <span className={styles.batteryPct}>{data.is_mock ? 'DEMO' : 'FITBIT'}</span>
          </button>
        </header>

        {/* -- Ojas name -------------------------------- */}
        <div className={styles.brandBar}>
          <span className={styles.whoopLogo}>OJAS</span>
        </div>

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
              displayText={!data.is_mock && sleep.total_sleep_hours <= 0 ? '—' : undefined}
            />
          </div>

          {/* RECOVERY DIAL (Center — Primary & Larger) */}
          <div className={styles.dialColCenter}>
            <CircleDial
              label="RECOVERY"
              value={recovery.score ?? 0}
              maxValue={100}
              color={recoveryColor}
              unit="%"
              size={116}
              onClick={() => router.push('/recovery')}
              showChevron
              isPrimary
              displayText={recovery.score === null ? '—' : undefined}
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
              displayText={!data.is_mock ? '—' : undefined}
            />
          </div>
        </section>

        {/* -- Health Monitor & Stress Monitor (2 Columns) --- */}
        <div className={styles.monitorsGrid}>
          {/* HEALTH MONITOR */}
          <div className={styles.monitorCard} onClick={() => router.push('/health')} onKeyDown={(event) => { if (event.key === 'Enter') router.push('/health'); }} role="button" tabIndex={0}>
            <div className={styles.cardHeaderRow}>
              <span className={styles.cardTitle}>HEALTH MONITOR</span>
              <svg className={styles.cardChevronSvg} width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
            </div>
            <div className={styles.monitorBody}>
              <div className={styles.monitorTextStack}>
                <span className={styles.monitorHighlight}>EXPLORE VITALS</span>
                <span className={styles.monitorSubtext}>{data.is_mock ? 'Sample trends' : 'Your measured trends'}</span>
              </div>
            </div>
          </div>

          {/* RECOVERY SIGNALS */}
          <div className={styles.monitorCard} onClick={() => router.push('/recovery')} onKeyDown={(event) => { if (event.key === 'Enter') router.push('/recovery'); }} role="button" tabIndex={0}>
            <div className={styles.cardHeaderRow}>
              <span className={styles.cardTitle}>RECOVERY SIGNALS</span>
              <svg className={styles.cardChevronSvg} width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
            </div>
            <div className={styles.monitorBody}>
              <div className={styles.monitorTextStack}>
                <span className={styles.monitorHighlight}>{recovery.today_hrv == null ? 'NO READING' : `${Math.round(recovery.today_hrv)} ms`}</span>
                <span className={styles.monitorSubtext}>Today’s HRV</span>
              </div>
            </div>
          </div>
        </div>

        {/* -- My Day Section -------------------------------- */}
        <section className={styles.myDaySection}>
          <h2 className={styles.myDayTitle}>My Day</h2>

          {/* Daily Outlook Banner */}
          <div className={styles.outlookBanner} role="button" tabIndex={0} onClick={() => router.push('/recovery')} onKeyDown={(event) => { if (event.key === 'Enter') router.push('/recovery'); }}>
            <div className={styles.outlookLeft}>
              <div className={styles.whoopIconPill}>O</div>
              <div className={styles.outlookContent}>
                <span className={styles.sunIcon}>☼</span>
                <span className={styles.outlookLabel}>Your Recovery Signals</span>
              </div>
            </div>
            <span className={styles.outlookChevron}>›</span>
          </div>

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
            <div className={styles.activityItem} role="button" tabIndex={0} onClick={() => router.push('/sleep')} onKeyDown={(event) => { if (event.key === 'Enter') router.push('/sleep'); }}>
              <div className={styles.activityLeftPart}>
                <div className={styles.sleepBadge}>
                  <span className={styles.moonIcon}>☽</span>
                  <span className={styles.sleepTimeText}>{!data.is_mock && sleep.total_sleep_hours <= 0 ? '—' : `${sleepHours}:${sleepMinutes}`}</span>
                </div>
                <span className={styles.activityName}>{!data.is_mock && sleep.total_sleep_hours <= 0 ? 'NO SLEEP RECORD' : 'SLEEP'}</span>
              </div>

              <div className={styles.activityTimeline}>
                <div className={styles.timeStack}>
                  <span className={styles.timeVal}>{formatTime(sleep.sleep_start)}</span>
                  <span className={styles.timeVal}>{formatTime(sleep.sleep_end)}</span>
                </div>
                <div className={styles.timelineBar} />
              </div>
            </div>

            {/* Action Buttons */}
            <div className={styles.actionButtonsRow}>
              <button className={styles.whoopBtn} onClick={() => router.push('/strain')}>VIEW ACTIVITIES</button>
            </div>
          </div>
        </section>
      </div>

    </div>
  );
}
