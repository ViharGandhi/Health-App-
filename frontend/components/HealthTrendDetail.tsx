'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { healthChange, healthDate, healthMetrics, type HealthRange } from '@/lib/health';
import { useHealth } from '@/lib/useHealth';
import MockBanner from './MockBanner';
import HealthHeader from './HealthHeader';
import HealthGuide from './HealthGuide';
import HealthMetricIcon from './HealthMetricIcon';
import HealthTrendChart, { type HealthSelection } from './HealthTrendChart';
import styles from '@/app/recovery/page.module.css';
import healthStyles from '@/app/health/page.module.css';

export default function HealthTrendDetail({ slug }: { slug: string }) {
  const router = useRouter();
  const metric = healthMetrics.find(item => item.slug === slug)!;
  const [range, setRange] = useState<HealthRange>('W');
  const [selection, setSelection] = useState<HealthSelection | null>(null);
  const [info, setInfo] = useState(false);
  const closeInfo = useCallback(() => setInfo(false), []);
  const { data, error, retry } = useHealth(range);
  const points = data?.metrics[metric.key] ?? [];
  const count = points.filter(point => point.value != null).length;
  const average = data?.averages[metric.key] ?? null;
  const previous = data?.previous_averages[metric.key] ?? null;
  const change = healthChange(average, previous, metric);
  const value = selection ? selection.value : average;
  const prior = range === 'W' ? 'week' : range === 'M' ? 'month' : '6 months';
  const latest = points.findLast(point => point.value != null);
  const methods = new Set(points.filter(point => point.value != null && point.method).map(point => point.method));
  const chosenPoint = selection && range !== '6M' ? points.find(point => selection.label === healthDate(point.date, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })) : null;
  return <div className={styles.page}>
    <MockBanner isMock={data?.is_mock ?? false} />
    <div className={styles.detailContainer}>
      <HealthHeader onInfo={() => setInfo(true)} />
      <div className={styles.selector}><HealthMetricIcon metric={metric.key} /><select aria-label="Health metric" value={slug} onChange={event => router.push(`/health/${event.target.value}`)}>
        {healthMetrics.map(item => <option key={item.slug} value={item.slug}>{item.title}</option>)}
      </select></div>
      <div className={styles.stats}><div><div className={styles.eyebrow}>{selection ? selection.label : 'AVERAGE'}</div><div className={styles.average} style={selection ? { color: '#67AEE6' } : undefined}>{value == null ? '—' : value.toFixed(metric.digits)}<small>{value == null ? '' : metric.unit}</small></div></div>
        <div className={styles.tabs} role="group" aria-label="Health history range">{(['W', 'M', '6M'] as const).map(item => <button key={item} aria-pressed={range === item} onClick={() => { if (item !== range) { setSelection(null); setRange(item); } }}>{item}</button>)}</div>
      </div>
      {error ? <div className={styles.loading} role="alert"><p>{error}</p><button className="btn btn-primary" onClick={retry}>Retry</button><Link className={healthStyles.connect} href="/connect">Connect account</Link></div>
        : !data ? <div className={styles.loading} role="status">Loading your health trend…</div> : <>
          <div className={styles.period}><span className={`${styles.change} ${healthStyles.change}`}>{change == null ? 'Prior period unavailable' : `${change} vs. prior ${prior}`}</span>
            <span className={healthStyles.periodLabel}>{healthDate(data.range_start)} – {healthDate(data.range_end, { month: 'short', day: 'numeric', year: 'numeric' })}</span></div>
          <p className={styles.description}>{average == null ? 'No measurements were recorded during this period.' : `Your average ${metric.title.toLowerCase()} was ${average.toFixed(metric.digits)} ${metric.unit}, using ${count} recorded ${count === 1 ? 'day' : 'days'}.`}
            {average != null && previous != null ? ` The prior ${prior} averaged ${previous.toFixed(metric.digits)} ${metric.unit}.` : average != null ? ' Earlier readings are needed for a period comparison.' : ''}</p>
          {range !== '6M' && points.some(point => point.baseline != null) && <div className={styles.typicalLegend}><span className={healthStyles.medianLine} />PRIOR 14-DAY MEDIAN</div>}
          <HealthTrendChart key={`${slug}-${range}-${data.range_end}`} points={points} metric={metric.key} unit={metric.unit} digits={metric.digits} range={range} onSelect={setSelection} />
          <div className={healthStyles.coverage}><span>{count} / {points.length} days recorded</span><span>{latest ? `Latest: ${healthDate(latest.date)}` : 'No readings'}</span></div>
          <p className={styles.note}>{range === '6M' ? 'Faint line: daily readings. Horizontal lines: monthly averages. Select a month to see its coverage.' : 'Hover, tap, or use arrow keys to select a date. Gaps are not filled.'}
            {range !== '6M' && !points.some(point => point.baseline != null) ? ' Personal reference building: seven earlier readings within 14 days are needed.' : ''}</p>
          {metric.key === 'rhr' && methods.size > 1 && <p className={styles.note}>This period includes different device RHR calculation methods. Its average combines the recorded estimates; select a date to see its method.</p>}
          {chosenPoint?.method && <p className={styles.note}>Selected RHR method: {chosenPoint.method === 'WITH_SLEEP' ? 'includes sleep data' : chosenPoint.method === 'ONLY_WITH_AWAKE_DATA' ? 'awake data only' : chosenPoint.method}.</p>}
          {chosenPoint?.estimated && <p className={styles.note}>The device marked this reading as estimated.</p>}
          <section className={healthStyles.meaning}><h2>HOW TO READ THIS</h2><p>{metric.meaning}</p>
            <p>Personal reference lines describe your prior readings; they are not medical limits.</p></section>
          <p className={styles.demoFooter}>{data.is_mock ? 'ILLUSTRATIVE SAMPLE DATA' : 'CONNECTED DEVICE MEASUREMENTS'}</p>
        </>}
    </div>
    {info && <HealthGuide metric={metric} onClose={closeInfo} />}
  </div>;
}
