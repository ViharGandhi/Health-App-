'use client';

import Link from 'next/link';
import HealthMetricIcon from './HealthMetricIcon';
import StrainMetricIcon from './StrainMetricIcon';
import RecoveryMetricIcon from './RecoveryMetricIcon';
import { dashboardValue } from '@/lib/activity';
import type { HomeMetrics, StrainMetric } from '@/lib/types';
import styles from './HomeDashboard.module.css';

export default function HomeDashboard({ data, onInfo }: { data: HomeMetrics; onInfo: (message: string) => void }) {
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
    <section className={styles.stress} aria-label="Stress Monitor"><div className={styles.stressHeader}><strong>STRESS MONITOR</strong><button aria-label="About Stress Monitor" onClick={() => onInfo('Daytime stress is not calculated by this app. The demo trace is a synthetic layout example; it is not a health assessment.')}>›</button></div>
      <div className={styles.stressStatus}><span>{data.is_mock ? 'Synthetic preview · 14:41' : 'No daytime data'}</span><strong style={{ color: data.is_mock ? '#00DCA0' : '#9BA4AD' }}>{data.is_mock ? 'SAMPLE  2.0' : 'UNAVAILABLE'}</strong></div>
      <div className={styles.stressChart}><svg viewBox="0 0 350 220" role="img" aria-label={data.is_mock ? 'Synthetic daytime stress example' : 'Daytime stress chart unavailable'}><defs><linearGradient id="homeStress" x1="0" y1="1" x2="1" y2="0"><stop stopColor="#7BA1BB" /><stop offset=".7" stopColor="#00DCA0" /><stop offset="1" stopColor="#F7CA52" /></linearGradient></defs>
        {[0, 1, 2, 3].map(i => <g key={i}><line x1="25" x2="340" y1={190 - i * 50} y2={190 - i * 50} stroke="#FFFFFF15" /><text x="3" y={194 - i * 50} fill="#9DA6AD" fontSize="9">{i}.0</text></g>)}
        {[25, 125, 225, 340].map(x => <line key={x} x1={x} x2={x} y1="40" y2="190" stroke="#FFFFFF0B" />)}
        {data.is_mock ? <><rect x="25" y="40" width="170" height="150" fill="#7BA1BB14" /><text x="108" y="28" fill="#FFF" fontSize="17">☾</text><text x="304" y="28" fontSize="17">🚶</text><path d="M25 170 32 168 38 175 42 163 47 168 54 165 58 173 63 168 70 176 77 170 85 179 93 174 100 178 106 168 115 172 123 169 133 171 143 169 152 173 160 170 172 172 181 164 187 173 194 163 200 155 206 175 211 161 216 170 224 110 229 176 238 178 242 169 247 173 254 177 M289 148 294 102 299 111 303 91 308 103 313 83 318 94 323 104 327 80 332 56 336 113 340 86" fill="none" stroke="url(#homeStress)" strokeWidth="2" /></>
          : <text x="185" y="120" textAnchor="middle" fill="#8F9BA5" fontSize="12">No stress readings available</text>}
        {['02:47', '07:00', '11:00', '14:41'].map((t, i) => <text key={t} x={[25, 125, 225, 340][i]} y="211" textAnchor={i === 3 ? 'end' : 'start'} fill="#9DA6AD" fontSize="9">{data.is_mock ? t : '—'}</text>)}
      </svg></div>
    </section>
    {rows.slice(4).map(metric)}
    <p className={styles.note}>Smaller values: prior 30 days. Weekly time totals compare with complete prior weeks. {data.is_mock && 'All values in this tab are sample data.'}</p>
  </section>;
}
