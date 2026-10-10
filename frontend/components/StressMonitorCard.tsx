import Link from 'next/link';
import StressChart from './StressChart';
import { stressColors, stressTime, stressNote, type StressData } from '@/lib/stress';
import styles from './StressMonitor.module.css';

export default function StressMonitorCard({ data, error, href }: { data: StressData | null; error: string | null; href: string }) {
  const day = data?.current;
  return <section className={styles.card} aria-label="Stress Monitor">
    <Link className={styles.heading} href={href}><strong>STRESS MONITOR</strong><span aria-hidden="true">›</span></Link>
    <div className={styles.status}><span>{day?.latest_at && data ? `Last ${data.is_mock ? 'sample' : 'reading'} ${stressTime(day.latest_at, data.timezone)}` : error ? 'Could not load readings' : data ? 'No stress reading available' : 'Loading readings…'}</span>
      <strong style={{ color: day?.latest_level ? stressColors[day.latest_level] : '#A5ADB4' }}>{day?.latest_level?.toUpperCase() ?? 'UNAVAILABLE'} <b>{day?.latest_score?.toFixed(1) ?? '—'}</b></strong></div>
    {data ? <StressChart data={data} /> : <p className={styles.note} role={error ? 'alert' : 'status'}>{error ?? 'Loading your stress timeline…'}</p>}
    <p className={styles.note}>{data?.is_mock ? 'SYNTHETIC DATA · UNVALIDATED ESTIMATE' : day ? stressNote(day) : 'Missing readings remain unscored.'}</p>
  </section>;
}
