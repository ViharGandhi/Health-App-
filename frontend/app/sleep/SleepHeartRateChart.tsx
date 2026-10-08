'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import { useSleepSyncRevision } from '@/lib/useSleepSyncRevision';
import { api } from '@/lib/api';
import type { SleepHeartRate, SleepStage, SleepStageRangeNight } from '@/lib/types';
import { LEFT, RIGHT, chartPosition, heartRatePaths, nearestReading, stageWindows } from '@/lib/sleepHeartRateChart';
import styles from './page.module.css';

const stageColors = { awake: '#E2E6EE', light: '#9B8AFB', deep: '#FF5CD1', rem: '#B040FF' };

export default function SleepHeartRateChart({ night, waiting, selectedStage }: { night?: SleepStageRangeNight; waiting: boolean; selectedStage: SleepStage | null }) {
  const [result, setResult] = useState<{ data: SleepHeartRate | null; loading: boolean; error: boolean }>({ data: null, loading: true, error: false });
  const [selected, setSelected] = useState<number | null>(null);
  const [inGap, setInGap] = useState(false);
  const sleepId = night?.sleep_id, nightDate = night?.night_date;
  const clipId = useId();
  const sleepRevision = useSleepSyncRevision();

  useEffect(() => {
    if (waiting) return;
    let cancelled = false;
    setResult({ data: null, loading: true, error: false });
    setSelected(null);
    setInGap(false);
    api.getSleepHeartRate(nightDate, sleepId).then(data => {
      if (!cancelled) setResult({ data, loading: false, error: false });
    }).catch(() => { if (!cancelled) setResult({ data: null, loading: false, error: true }); });
    return () => { cancelled = true; };
  }, [sleepId, nightDate, waiting, sleepRevision]);

  const data = result.data;
  const samples = useMemo(() => data?.samples.map(s => ({ time: Date.parse(s.timestamp), bpm: s.bpm })) ?? [], [data]);
  const start = Date.parse(data?.start ?? ''), end = Date.parse(data?.end ?? '');
  const min = Math.min(30, Math.floor(samples.reduce((low, s) => Math.min(low, s.bpm), Infinity) / 20) * 20);
  const step = Math.max(20, Math.ceil((samples.reduce((high, s) => Math.max(high, s.bpm), 110) - min) / 80) * 20);
  const max = min + step * 4;
  const paths = useMemo(() => heartRatePaths(samples, start, end, min, max), [samples, start, end, min, max]);
  const windows = stageWindows(data?.stage_intervals?.filter(s => s.stage === selectedStage) ?? [], start, end);
  const active = selected == null ? null : data?.samples[selected];
  const position = selected == null ? null : chartPosition(samples[selected], start, end, min, max);
  const empty = result.loading || waiting ? 'Loading heart rate…' : result.error ? 'Heart rate unavailable — try refreshing'
    : data?.status === 'no_sleep' ? 'No completed main sleep recorded' : 'No heart-rate readings for this sleep';

  return <div className={styles.hrChartContainer}>
    <div className={styles.hrYAxis} aria-hidden="true">
      {[max, max - step, max - 2 * step, max - 3 * step, min].map(value => <span key={value}>{value}</span>)}
    </div>
    <div className={styles.hrGraphBody}>
      <div className={styles.hrGridlines} aria-hidden="true">
        {[0, 1, 2, 3, 4].map(i => <div key={i} className={styles.hrGridline} />)}
      </div>
      {!!samples.length ? <>
        <svg id="sleep-heart-rate-chart" className={styles.hrSvg} viewBox="0 0 320 100" preserveAspectRatio="none"
          role="slider" tabIndex={0} aria-label="Sleep heart rate. Hover, tap, or use arrow keys for time and BPM."
          aria-valuemin={0} aria-valuemax={samples.length - 1} aria-valuenow={selected ?? 0}
          aria-valuetext={active ? `${active.local_time}, ${active.bpm} BPM` : 'Use arrow keys to inspect readings'}
          onPointerMove={event => {
            if (event.pointerType === 'touch' && !event.buttons) return;
            const bounds = event.currentTarget.getBoundingClientRect();
            const x = (event.clientX - bounds.left) / bounds.width * 320;
            const index = nearestReading(samples, start + (x - LEFT) / (RIGHT - LEFT) * (end - start));
            setSelected(index); setInGap(index == null);
          }}
          onPointerDown={event => {
            const bounds = event.currentTarget.getBoundingClientRect();
            const x = (event.clientX - bounds.left) / bounds.width * 320;
            const index = nearestReading(samples, start + (x - LEFT) / (RIGHT - LEFT) * (end - start));
            setSelected(index); setInGap(index == null);
          }}
          onPointerLeave={event => { if (event.pointerType !== 'touch') { setSelected(null); setInGap(false); } }}
          onBlur={() => { setSelected(null); setInGap(false); }}
          onKeyDown={event => {
            if (event.key === 'Escape') { setSelected(null); setInGap(false); return; }
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); setInGap(false);
            setSelected(index => event.key === 'Home' ? 0 : event.key === 'End' ? samples.length - 1
              : Math.max(0, Math.min(samples.length - 1, (index ?? (event.key === 'ArrowLeft' ? samples.length : -1)) + (event.key === 'ArrowLeft' ? -1 : 1))));
          }}>
          {selectedStage && <>
            <defs><clipPath id={clipId}>
              {windows.map((window, i) => <rect key={i} x={window.x} width={window.width} y="0" height="100" />)}
            </clipPath></defs>
            <g role="img" aria-label={`${selectedStage.toUpperCase()} sleep: ${windows.length} intervals highlighted`}>
              {windows.map((window, i) => <rect key={i} x={window.x} width={window.width} y="0" height="100"
                fill={stageColors[selectedStage]} opacity="0.12" />)}
            </g>
          </>}
          {[LEFT, RIGHT].map(x => <g key={x}>
            <line x1={x} y1="0" x2={x} y2="100" stroke="rgba(255,255,255,0.4)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={x} cy="100" r="2.2" fill="#FFFFFF" />
          </g>)}
          {paths.map((d, i) => <path key={i} d={d} fill="none" stroke="#62A4B7" opacity={selectedStage ? 0.3 : 1} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />)}
          {selectedStage && <g clipPath={`url(#${clipId})`}>
            {paths.map((d, i) => <path key={i} d={d} fill="none" stroke={stageColors[selectedStage]} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />)}
          </g>}
          {position && <g>
            <line x1={position.x} x2={position.x} y1="0" y2="100" stroke="rgba(255,255,255,0.3)" strokeDasharray="2 3" />
            <circle cx={position.x} cy={position.y} r="3" fill="#62A4B7" stroke="#FFFFFF" strokeWidth="1" />
          </g>}
        </svg>
        <div className={styles.hrChartHint}>{data?.is_mock ? 'DEMO · ' : ''}{selectedStage ? `${selectedStage.toUpperCase()}${windows.length ? '' : ' · No intervals'} · ` : ''}BPM · Hover or tap</div>
      </> : <div className={styles.hrChartEmpty} role="status">{empty}</div>}
      {(active || inGap) && <div className={styles.hrTooltip} role="tooltip"
        style={{ left: `${Math.max(17, Math.min(83, (position?.x ?? 160) / 320 * 100))}%` }}>
        {active ? <><strong>{active.bpm} BPM</strong><span>{active.local_time.slice(0, 10)} · {active.local_time.slice(11, -6)} · UTC{active.local_time.slice(-6)}</span></> : 'No reading in this gap'}
      </div>}
      <div className={styles.hrTimestamps}>
        <span className={styles.hrTimeStart} style={{ left: `${LEFT / 320 * 100}%` }}>{data?.start_local?.slice(11, 16) ?? '—'}</span>
        <span className={styles.hrTimeEnd} style={{ left: `${RIGHT / 320 * 100}%` }}>{data?.end_local?.slice(11, 16) ?? '—'}</span>
      </div>
    </div>
  </div>;
}
