'use client';

import { useEffect, useRef } from 'react';
import type { HealthData } from '@/lib/types';
import { healthDate, healthMetrics, monitorReading } from '@/lib/health';
import styles from '@/app/health/page.module.css';

export default function HealthReport({ data, onClose }: { data: HealthData; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className={styles.reportDialog} onCancel={onClose} aria-labelledby="health-report-title">
    <div className={styles.reportActions}><button onClick={onClose} aria-label="Close Health report">×</button></div>
    <h2 id="health-report-title">Health report</h2>
    <p>{healthDate(data.date, { month: 'long', day: 'numeric', year: 'numeric' })} · {data.is_mock ? 'Illustrative sample data' : 'Connected device readings'}</p>
    <table><thead><tr><th>Measurement</th><th>Reading</th><th>Personal reference</th></tr></thead><tbody>
      {healthMetrics.slice(0, 5).map(metric => {
        const point = data.metrics[metric.key]?.find(item => item.date === data.date);
        const reading = monitorReading(metric, point);
        const value = metric.key === 'skin_temperature' ? reading.formatted : point?.value?.toFixed(metric.digits) ?? '—';
        return <tr key={metric.key}><td>{metric.key === 'skin_temperature' ? reading.hasBaseline ? 'Skin temperature change' : 'Skin temperature' : metric.title.toLowerCase()}</td><td>{value}{value === '—' ? '' : ` ${reading.unit}`}
          {metric.key === 'skin_temperature' && point?.value != null && <small className={styles.recordedTemperature}>Recorded {point.value.toFixed(1)} °C</small>}</td><td>{point?.baseline != null ? `Median ${point.baseline.toFixed(metric.digits)} ${metric.unit}` : reading.comparison}</td></tr>;
      })}
    </tbody></table>
    <p>References are medians of the prior 14 calendar days, excluding the reading date, and require at least seven readings. Missing readings are left blank. Temperature change is relative to that personal median.</p>
    <p>Wearable measurements and personal comparisons are not medical reference limits.</p>
    <div className={styles.reportActions}><button className={styles.printButton} onClick={() => window.print()}>Print / Save as PDF</button></div>
  </dialog>;
}
