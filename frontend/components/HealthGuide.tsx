'use client';

import { useEffect, useRef } from 'react';
import type { HealthMetric } from '@/lib/health';
import styles from '@/app/recovery/page.module.css';

export default function HealthGuide({ metric, onClose }: { metric?: HealthMetric; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.querySelector('button')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') { event.preventDefault(); panel.current?.querySelector('button')?.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', key); previous?.focus(); };
  }, [onClose]);
  return <div className={styles.modalBackdrop} onClick={onClose}><div ref={panel} role="dialog" aria-modal="true" aria-labelledby="health-guide-title" className={styles.modal} onClick={event => event.stopPropagation()}>
    <button onClick={onClose} aria-label="Close Health guide">×</button><h2 id="health-guide-title">{metric ? metric.title : 'Understanding Health'}</h2>
    {metric && <p>{metric.meaning}</p>}
    <p>Daily vitals come from your device. Each personal reference is the median of the prior 14 calendar days, excluding the selected day. At least seven earlier readings are needed. It is a reference line, not a medical limit.</p>
    <p>Weekly and monthly averages use recorded days only. Six-month charts show a faint daily trace and monthly averages, with the number of recorded days available when selected. Missing readings stay blank.</p>
    <p>The Monitor checks for the latest synced heart-rate reading every minute and shows its measurement time. Fitbit cloud sync can delay readings; this is not a live device feed. The trace shows 15-minute medians in the recorded local time. Hover, tap, or use the arrow keys to explore medians; Escape returns to the latest synced reading.</p>
    <p>Changes show the difference in the measurement’s own unit. Oxygen saturation uses percentage points. These comparisons describe change without assigning a health rating.</p>
    <p>The Monitor tiles show readings for the displayed night. While its baseline is building, skin temperature shows the measured temperature in °C. Once the baseline is available, the tile shows its difference from your prior 14-day median in °F; the detail chart retains the recorded absolute temperature in °C. The green badges show available median comparisons, not a normal-range assessment.</p>
  </div></div>;
}
