'use client';

import type { HealthData } from '@/lib/types';
import styles from '@/app/health/page.module.css';

export default function HealthMonitorHeart({ initial }: { initial: HealthData }) {
  const resting = initial.metrics.rhr?.find(point => point.date === initial.date)?.value;
  return <section className={styles.monitorHeart} aria-label="Nightly resting heart rate">
    <div className={styles.bpmCircle}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 21 3 12C-3 5 7-2 12 5c5-7 15 0 9 7Z" /></svg>
      <strong>{resting == null ? '—' : Math.round(resting)}</strong><span>RESTING BPM</span>
    </div>
    <p className={styles.sampleCaption}>{initial.date} · {initial.is_mock ? 'Sample resting heart rate' : 'Saved daily resting heart rate'}</p>
  </section>;
}
