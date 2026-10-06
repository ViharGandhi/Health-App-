'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import MockBanner from '@/components/MockBanner';
import HealthGuide from '@/components/HealthGuide';
import HealthMetricIcon from '@/components/HealthMetricIcon';
import HealthMonitorHeart from '@/components/HealthMonitorHeart';
import HealthReport from '@/components/HealthReport';
import { healthDate, healthMetrics, monitorReading } from '@/lib/health';
import { useHealth } from '@/lib/useHealth';
import styles from './page.module.css';

const monitorTiles = [
  { key: 'respiratory_rate', title: 'RESPIRATORY RATE' },
  { key: 'spo2', title: 'BLOOD OXYGEN' },
  { key: 'rhr', title: 'RHR' },
  { key: 'hrv', title: 'HRV' },
  { key: 'skin_temperature', title: 'SKIN TEMP (FROM BASELINE)' },
] as const;

export default function HealthPage() {
  const { data, error, retry } = useHealth();
  const [info, setInfo] = useState(false);
  const [report, setReport] = useState(false);
  const closeInfo = useCallback(() => setInfo(false), []);
  return <div className={styles.monitor}>
    <MockBanner isMock={data?.is_mock ?? false} />
    <div className={styles.monitorBody}>
      <header className={styles.monitorHeader}>
        <Link href="/" aria-label="Back to Home"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m15 4-8 8 8 8" /></svg></Link>
        <h1>HEALTH MONITOR</h1><span />
      </header>
      {error ? <div className={styles.monitorState} role="alert"><p>{error}</p><button className="btn btn-primary" onClick={retry}>Retry</button><Link className={styles.connect} href="/connect">Connect account</Link></div>
        : !data ? <div className={styles.monitorState} role="status">Loading your health measurements…</div> : <>
          <HealthMonitorHeart initial={data} />
          <div className={styles.nightHeading}><h2>LAST NIGHT&apos;S METRICS</h2><button aria-label="Health guide" onClick={() => setInfo(true)}>?</button></div>
          <section className={styles.monitorGrid} aria-label="Last night's metrics">
            {monitorTiles.map(tile => {
              const metric = healthMetrics.find(item => item.key === tile.key)!;
              const point = data.metrics[tile.key]?.find(item => item.date === data.date);
              const reading = monitorReading(metric, point);
              return <Link key={tile.key} href={`/health/${metric.slug}`} className={styles.monitorTile}>
                <div className={styles.tileTitle}><HealthMetricIcon metric={tile.key} size={24} /><span>{tile.title}</span></div>
                <div className={styles.tileValue}>{reading.formatted}<small>{reading.formatted === '—' ? '' : reading.unit}</small></div>
                <span className={`${styles.baselineBadge} ${reading.hasBaseline ? styles.readyBadge : ''}`}>{reading.hasBaseline && <span aria-hidden="true">≈ </span>}{reading.comparison}</span>
              </Link>;
            })}
            <button className={styles.reportTile} onClick={() => setReport(true)}>
              <span className={styles.reportTitle}>SHARE YOUR HEALTH REPORT <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M4 12h15m-6-6 6 6-6 6" /></svg></span>
              <span className={styles.reportDescription}>Printable report for sharing with your doctor, physician, trainer, or anyone of your choosing.</span>
            </button>
          </section>
          <p className={styles.nightDate}>{healthDate(data.date, { month: 'short', day: 'numeric', year: 'numeric' })}{data.is_mock ? ' · Sample data' : ''}</p>
        </>}
    </div>
    {info && <HealthGuide onClose={closeInfo} />}
    {report && data && <HealthReport data={data} onClose={() => setReport(false)} />}
  </div>;
}
