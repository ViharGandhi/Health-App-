'use client';

import { useEffect, useRef } from 'react';
import type { RecoveryData } from '@/lib/types';
import RecoveryMetricIcon from './RecoveryMetricIcon';
import styles from '@/app/recovery/page.module.css';

export function RecoveryInfo({ data, onClose }: { data?: RecoveryData; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.querySelector('button')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') { event.preventDefault(); panel.current?.querySelector('button')?.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); document.body.style.overflow = previousOverflow; previous?.focus(); };
  }, [onClose]);
  return <div className={styles.modalBackdrop} onClick={onClose}><div ref={panel} role="dialog" aria-modal="true" aria-labelledby="recovery-info-title" className={styles.modal} onClick={event => event.stopPropagation()}>
    <button aria-label="Close Recovery guide" onClick={onClose}>×</button><h2 id="recovery-info-title">Understanding Recovery</h2>
    {data?.is_mock && !data.estimated && <p>You are viewing the older prototype demo formula. Switch to New estimate in the demo selector to preview the calculator described below.</p>}
    <p>The new estimate compares your recent daily RMSSD and resting heart rate with your own earlier readings. Above normal means higher than usual; it is not necessarily better.</p>
    <p>The scoring reference covers 60 days and excludes the seven days immediately before the current day. A small sleep-duration penalty applies only when both a completed sleep and its pre-sleep need are available.</p>
    <p>Typical ranges show a median ± one robust standard deviation. They describe your recorded variation, not medical limits. Resting-heart-rate comparisons use the same reported calculation method.</p>
    <p>Historical Recovery uses the available HRV/RHR signals without missing historical sleep need. Gaps remain blank. Percentage is withheld at low confidence; score and zone stay blank while the reference is building.</p>
    {data?.components && <div className={styles.components}>
      <div><span>HRV signal z · {data.components.z_rhr == null ? '100%' : '60%'}</span><strong>{data.components.z_hrv?.toFixed(2) ?? '—'}</strong></div>
      <div><span>RHR signal z · {data.components.z_rhr == null ? 'Unavailable' : '40%'}</span><strong>{data.components.z_rhr?.toFixed(2) ?? '—'}</strong></div>
      <div><span>Sleep adjustment z</span><strong>{data.components.sleep_adj.toFixed(2)}</strong></div>
      <div><span>Combined z</span><strong>{data.z?.toFixed(2) ?? '—'}</strong></div>
      <div><span>Reference / recent nights</span><strong>{data.baseline_days ?? 0} / {data.recent_nights ?? 0}</strong></div>
    </div>}
    {data?.illness_flag && <p className={styles.note}>A breathing-rate or skin-temperature deviation capped this estimate. This flag is not an illness diagnosis.</p>}
    <p className={styles.note}>An experimental app estimate, not a validated clinical score or WHOOP&apos;s proprietary algorithm.</p>
  </div></div>;
}

export function RecoveryLearnMore({ onOpen }: { onOpen: () => void }) {
  return <section className={styles.learnMore}><div className={styles.learnHeader}><span>LEARN MORE</span><button onClick={onOpen}>VIEW ALL →</button></div>
    <div className={styles.learnCards}>{[{ metric: 'hrv' as const, label: 'HRV: understand your personal pattern' }, { metric: 'rhr' as const, label: 'Resting heart rate: read your trends' }].map(item => <button key={item.metric} onClick={onOpen} className={styles.learnCard}>
      <div className={styles.learnVisual}><RecoveryMetricIcon metric={item.metric} size={48} /><span>GUIDE</span></div><strong>{item.label}</strong>
    </button>)}</div>
  </section>;
}
