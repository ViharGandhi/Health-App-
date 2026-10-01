'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import MetricNav from '@/components/MetricNav';
import MockBanner from '@/components/MockBanner';
import ShareButton from '@/components/ShareButton';
import { api } from '@/lib/api';
import type { SleepData } from '@/lib/types';
import styles from './page.module.css';

function duration(hours: number) {
  const totalMinutes = Math.round(hours * 60);
  return `${Math.floor(totalMinutes / 60)}:${String(totalMinutes % 60).padStart(2, '0')}`;
}

function minutes(value: number) {
  const total = Math.round(value);
  return `${Math.floor(total / 60)}h ${total % 60}m`;
}

export default function SleepPage() {
  const [data, setData] = useState<SleepData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getSleep().then(setData).catch(() => setError(true));
  }, []);

  if (error) return <div className="page" style={{ paddingTop: 24 }}>Could not load sleep data.</div>;
  if (!data) return <div className="page" style={{ paddingTop: 24 }}><div className="skeleton" style={{ height: 300, borderRadius: 16 }} /></div>;

  const hoursVsNeeded = data.sleep_need_hours > 0
    ? Math.min(100, Math.round(data.total_sleep_hours / data.sleep_need_hours * 100))
    : null;
  const stageRows = [
    ['DEEP', data.stages.deep_minutes],
    ['REM', data.stages.rem_minutes],
    ['LIGHT / CORE', data.stages.core_minutes],
    ['AWAKE', data.stages.awake_minutes],
  ] as const;
  const stageTotal = stageRows.reduce((total, [, value]) => total + value, 0);

  return <>
    <MockBanner isMock={data.is_mock} />
    <div className="page">
      <MetricNav active="sleep" isMock={data.is_mock}>
        <section className={styles.hero} aria-label="Sleep performance">
          <h1>SLEEP<br />PERFORMANCE</h1>
          <div className={styles.score}>{Math.round(data.score)}<span>%</span></div>
          <ShareButton metric="Sleep" value={`${Math.round(data.score)}%`} isMock={data.is_mock} />
          <div className={styles.hoursRow}>
            <div><strong>{duration(data.total_sleep_hours)}</strong><span>HOURS OF SLEEP</span></div>
            <div><strong>{duration(data.sleep_need_hours)}</strong><span>SLEEP NEEDED</span></div>
          </div>
        </section>

        <section className={styles.summary}>
          <h2>{data.is_mock ? 'Sample sleep' : 'Your sleep'}</h2>
          <p>{hoursVsNeeded === null ? 'Sleep need is unavailable.' : `You slept ${hoursVsNeeded}% of the estimated time needed.`} The score and need estimate use the current sleep algorithm.</p>
        </section>

        <section className={styles.section}>
          <h2>SLEEP ACTIVITY</h2>
          <div className={styles.activity}><span className={styles.moon}>☾ &nbsp;{duration(data.total_sleep_hours)}</span><strong>SLEEP</strong><span>{data.is_mock ? 'DEMO' : ''}</span></div>
        </section>

        <section className={styles.section}>
          <h2>SLEEP STATISTICS</h2>
          <div className={styles.statRow}><span>HOURS VS. NEEDED</span><strong>{hoursVsNeeded === null ? '—' : `${hoursVsNeeded}%`}</strong></div>
          <Link href="/sleep/consistency" className={styles.statRow}><span>SLEEP CONSISTENCY</span><strong>{data.consistency_score === null ? '—' : `${Math.round(data.consistency_score)}%`} ›</strong></Link>
          <Link href="/sleep/efficiency" className={styles.statRow}><span>SLEEP EFFICIENCY</span><strong>{Math.round(data.efficiency_pct)}% ›</strong></Link>
        </section>

        <section className={styles.section}>
          <h2>SLEEP STAGES <small>{duration(data.total_sleep_hours)} total</small></h2>
          <div className={styles.stages}>
            {stageRows.map(([label, value]) => <div key={label} className={styles.stage}>
              <span>{label}</span><strong>{minutes(value)}</strong><small>{stageTotal > 0 ? `${Math.round(value / stageTotal * 100)}% of recorded stages` : '—'}</small>
            </div>)}
          </div>
        </section>
      </MetricNav>
    </div>
  </>;
}
