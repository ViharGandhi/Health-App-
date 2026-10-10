'use client';

import Link from 'next/link';
import HealthMetricIcon from './HealthMetricIcon';
import StrainMetricIcon from './StrainMetricIcon';
import RecoveryMetricIcon from './RecoveryMetricIcon';
import { dashboardValue } from '@/lib/activity';
import type { HomeMetrics, StrainMetric } from '@/lib/types';
import styles from './HomeDashboard.module.css';
import StressMonitorCard from './StressMonitorCard';
import type { StressData } from '@/lib/stress';

export default function HomeDashboard({ data, onInfo, stress, stressError, stressHref }: { data: HomeMetrics; onInfo: (message: string) => void; stress: StressData | null; stressError: string | null; stressHref: string }) {
  const rows = data.rows;
  function metric(row: typeof rows[number]) {
    const delta = row.value != null && row.previous != null ? dashboardValue(row.value, row.key, row.unit) === dashboardValue(row.previous, row.key, row.unit) ? 0 : row.value - row.previous : null;
    const arrow = delta == null ? '' : Math.abs(delta) < .05 ? '•' : delta > 0 ? '▲' : '▼';
    const content = <><span className={styles.icon}>{['steps', 'strength', 'zones_1_3', 'zones_4_5', 'strain'].includes(row.key)
      ? <StrainMetricIcon metric={row.key as StrainMetric} size={21} />
      : ['performance', 'consistency', 'asleep_minutes'].includes(row.key) ? <RecoveryMetricIcon metric="sleep_performance" size={21} /> : <HealthMetricIcon metric={row.key} size={21} />}</span><span className={styles.name}>{row.title}</span>
      <span className={styles.values}><strong>{dashboardValue(row.value, row.key, row.unit)}</strong><small>{dashboardValue(row.previous, row.key, row.unit)}</small></span>
      <span className={styles.arrow} style={{ color: delta == null || Math.abs(delta) < .05 ? '#9BA4AD' : delta > 0 ? '#00DCA0' : '#F5AC22' }}>{arrow}</span></>;
    return data.is_mock ? <button className={styles.row} key={row.key} onClick={() => onInfo(`${row.title}: synthetic preview. The smaller value is the prior 30-day average; weekly duration rows compare complete seven-day totals. Open the live tab for your connected trends.`)}>{content}</button>
      : <Link className={styles.row} key={row.key} href={row.href}>{content}</Link>;
  }
  return <section className={styles.dashboard} aria-label="My Dashboard"><div className={styles.heading}><h2>My Dashboard</h2><button onClick={() => onInfo('Dashboard customization is not available yet. These metrics follow the reference order.')}>CUSTOMIZE <span>✎</span></button></div>
    {rows.slice(0, 4).map(metric)}
    <StressMonitorCard data={stress} error={stressError} href={stressHref} />
    {rows.slice(4).map(metric)}
    <p className={styles.note}>Smaller values: prior 30 days. Weekly time totals compare with complete prior weeks. {data.is_mock && 'All values in this tab are sample data.'}</p>
  </section>;
}
