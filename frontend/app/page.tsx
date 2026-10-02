'use client';

/**
 * Dashboard — Home page (/)
 * Exact WHOOP app dashboard:
 * - Top header with Avatar, streak, `< TODAY >` pill, and strap battery
 * - "WHOOP" centered wordmark
 * - Three horizontal dials: SLEEP, RECOVERY, STRAIN with exact WHOOP layout, fonts & colors
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
  green:  '#22E600', // Crisp WHOOP electric lime green
  yellow: '#F5C518',
  red:    '#FF3B3B',
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
  const recoveryColor = RECOVERY_COLOR[recovery.status] ?? '#00F076';
  const sleepColor = '#4EA5B7'; // Whoop sleep teal/cyan
  const strainColor = '#3078F0'; // Whoop strain blue

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
            <div className={styles.streakBadge}>
              <span className={styles.flame}>🔥</span>
              <span className={styles.streakNum}>6</span>
            </div>
          </div>

          <div className={styles.datePill}>
            <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transform: 'rotate(180deg)' }}>
              <path d="M1 1.5L4.5 5L1 8.5" />
            </svg>
            <span className={styles.pillText}>TODAY</span>
            <svg width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 1.5L4.5 5L1 8.5" />
            </svg>
          </div>

          <div className={styles.headerRight}>
            <span className={styles.batteryPct}>94%</span>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#22E600" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={styles.batteryIcon}>
              <rect x="2" y="7" width="16" height="10" rx="2" ry="2" />
              <line x1="20" y1="11" x2="20" y2="13" />
            </svg>
          </div>
        </header>

        {/* -- WHOOP Wordmark -------------------------------- */}
        <div className={styles.brandBar}>
          <span className={styles.whoopLogo}>WHOOP</span>
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
              displayText={recovery.score == null ? '—' : undefined}
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

        {/* -- Health Monitor & Stress Monitor (2 Columns) --- */}
        <div className={styles.monitorsGrid}>
          {/* HEALTH MONITOR */}
          <div className={styles.monitorCard} onClick={() => router.push('/recovery')} role="button" tabIndex={0}>
            <div className={styles.cardHeaderRow}>
              <span className={styles.cardTitle}>HEALTH MONITOR</span>
              <svg className={styles.cardChevronSvg} width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
            </div>
            <div className={styles.monitorBody}>
              <div className={styles.checkIconBox}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#2BD67E" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div className={styles.monitorTextStack}>
                <span className={styles.monitorHighlight} style={{ color: '#2BD67E' }}>
                  WITHIN RANGE
                </span>
                <span className={styles.monitorSubtext}>5/5 Metrics</span>
              </div>
            </div>
          </div>

          {/* STRESS MONITOR */}
          <div className={styles.monitorCard} onClick={() => router.push('/strain')} role="button" tabIndex={0}>
            <div className={styles.cardHeaderRow}>
              <span className={styles.cardTitle}>STRESS MONITOR</span>
              <svg className={styles.cardChevronSvg} width="6" height="10" viewBox="0 0 6 10" fill="none" stroke="#8E95A2" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 1.5L4.5 5L1 8.5" />
              </svg>
            </div>
            <div className={styles.monitorBody}>
              <div className={styles.stressScoreBadge}>0.4</div>
              <div className={styles.monitorTextStack}>
                <span className={styles.monitorHighlight} style={{ color: '#2BD67E' }}>
                  LOW
                </span>
                <span className={styles.monitorSubtext}>7:30 AM</span>
              </div>
            </div>
          </div>
        </div>

        {/* -- My Day Section -------------------------------- */}
        <section className={styles.myDaySection}>
          <h2 className={styles.myDayTitle}>My Day</h2>

          {/* Daily Outlook Banner */}
          <div className={styles.outlookBanner}>
            <div className={styles.outlookLeft}>
              <div className={styles.whoopIconPill}>W</div>
              <div className={styles.outlookContent}>
                <span className={styles.sunIcon}>☼</span>
                <span className={styles.outlookLabel}>Your Daily Outlook</span>
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
            <div className={styles.activityItem}>
              <div className={styles.activityLeftPart}>
                <div className={styles.sleepBadge}>
                  <span className={styles.moonIcon}>☽</span>
                  <span className={styles.sleepTimeText}>{sleepHours}:{sleepMinutes}</span>
                </div>
                <span className={styles.activityName}>SLEEP</span>
              </div>

              <div className={styles.activityTimeline}>
                <div className={styles.timeStack}>
                  <span className={styles.timeVal}>{sleep.sleep_start ? formatTime(sleep.sleep_start) : '12:35 AM'}</span>
                  <span className={styles.timeVal}>{sleep.sleep_end ? formatTime(sleep.sleep_end) : '7:26 AM'}</span>
                </div>
                <div className={styles.timelineBar} />
              </div>
            </div>

            {/* Action Buttons */}
            <div className={styles.actionButtonsRow}>
              <button className={styles.whoopBtn}>
                <span className={styles.plusSign}>+</span>
                <span>ADD ACTIVITY</span>
              </button>
              <button className={styles.whoopBtn}>
                <span className={styles.timerIcon}>⏱</span>
                <span>START ACTIVITY</span>
              </button>
            </div>
          </div>
        </section>
      </div>

      {/* Floating WHOOP Action Button */}
      <div className={styles.floatingActionBtn}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#121417" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </div>
    </div>
  );
}
