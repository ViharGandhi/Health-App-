import type { StrainMetric } from '@/lib/types';

export default function StrainMetricIcon({ metric, size = 22 }: { metric: StrainMetric; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {metric === 'zones_1_3' || metric === 'zones_4_5' ? <><path d="M20 5a5 5 0 0 0-8 1 5 5 0 0 0-8-1C0 9 7 16 12 21 17 16 24 9 20 5Z" /><path d="M3 11h4l2-3 3 7 2-4h7" /></>
      : metric === 'strength' ? <><path d="M8 10h8M8 14h8M4 8H2v8h2m16-8h2v8h-2" /><rect x="4" y="5" width="4" height="14" rx="1" /><rect x="16" y="5" width="4" height="14" rx="1" /></>
      : metric === 'steps' ? <><path d="m10 3 4 3-2 5 4 5 5 3v3H9l-6-6 2-6 5-7Z" /><path d="m8 10 2 5 5 4M14 6l3-3 2 3-2 5" /></>
      : <><path d="M6 6H2v5h4m12-5h4v5h-4M7 4l3 15h4l3-15" /><path d="M6 8h12m-7 2h2v5h-2Z" /></>}
  </svg>;
}
