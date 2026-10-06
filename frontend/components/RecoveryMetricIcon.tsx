import type { RecoveryMetric } from '@/lib/types';

export default function RecoveryMetricIcon({ metric, size = 23 }: { metric: RecoveryMetric; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {metric === 'hrv' || metric === 'recovery' ? <path d="M2 11h4l3-6 3 13 3-7h7M7 11l-2 4H2m15-4 2-4h3" />
      : metric === 'rhr' ? <><path d="M20 4c-3-2-6 0-8 2-2-2-5-4-8-2-4 3-2 7 0 9l8 8 8-8c2-2 4-6 0-9Z" /><path d="M5 11h3l2-3 3 7 2-4h4" /></>
      : metric === 'respiratory_rate' ? <><path d="M10 3v8l-4 4m8-12v8l4 4M8 7C5 7 2 13 2 17c0 4 6 4 8 1V7m6 0c3 0 6 6 6 10 0 4-6 4-8 1V7" /></>
      : <path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z" />}
  </svg>;
}
