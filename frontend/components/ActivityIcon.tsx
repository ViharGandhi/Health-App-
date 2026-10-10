import { activityKind } from '@/lib/activity';

export default function ActivityIcon({ name, type, size = 24 }: { name: string; type?: string | null; size?: number }) {
  const kind = activityKind(name, type);
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
    {kind === 'walking' ? <>
      <circle cx="13.5" cy="3" r="1.8" fill="currentColor" stroke="none" />
      <path d="m13 6-2 7 3 4 1 5M11 13l-2 5-3 4M12 7l-4 5-3 1m7-5 4 5 3 1" strokeWidth="2" />
      <path d="m12 6 2 1-2 7-2-1Z" fill="currentColor" stroke="none" />
    </> : kind === 'running' ? <>
      <circle cx="16.5" cy="3" r="1.8" fill="currentColor" stroke="none" />
      <path d="m14 6-4 7 6 3 2 6M10 13l-3 5-5-1m10-9-4-2-3 3m8-2 4 4 4-2" strokeWidth="2.2" />
      <path d="m13 5 3 2-4 7-3-2Z" fill="currentColor" stroke="none" />
    </> : kind === 'strength' ? <>
      <circle cx="12" cy="8" r="1.8" fill="currentColor" stroke="none" />
      <path d="M2 3h20M3 1v4m18-4v4M5 3l2 7 5 2 5-2 2-7M12 11v6m0 0-5 1-1 4m6-5 5 1 1 4" />
      <path d="M10 11h4v6h-4Z" fill="currentColor" stroke="none" />
    </> : kind === 'cycling' ? <>
      <circle cx="5" cy="17" r="4" /><circle cx="19" cy="17" r="4" /><circle cx="15" cy="3" r="1.6" fill="currentColor" stroke="none" /><path d="m12 6-4 6 6 1-2 6m0-13 5 5h3M8 12l-3 5" />
    </> : kind === 'swimming' ? <>
      <circle cx="18" cy="8" r="1.7" fill="currentColor" stroke="none" /><path d="m3 13 6-6 4 4 2 3M9 7 6 3H2m0 15q2-2 5 0t5 0 5 0 5 0M2 22q2-2 5 0t5 0 5 0 5 0" />
    </> : kind === 'yoga' ? <>
      <circle cx="12" cy="4" r="1.7" fill="currentColor" stroke="none" /><path d="M12 8v7m0-6-5 5H3m9-5 5 5h4m-9 1-7 4 7 2 7-2-7-4" />
    </> : kind === 'rowing' ? <>
      <circle cx="13" cy="4" r="1.7" fill="currentColor" stroke="none" /><path d="m12 8-3 5 6 2 3 4M10 10l7 2m-2-5 7 14M2 19h17l3-3H4Z" />
    </> : kind === 'tennis' ? <>
      <ellipse cx="15" cy="7" rx="5" ry="6" transform="rotate(30 15 7)" /><path d="m12 12-7 10M13 3l4 8m-5-5 7-1" />
    </> : kind === 'football' || kind === 'basketball' ? <>
      <circle cx="12" cy="12" r="10" />{kind === 'football' ? <path d="m12 7 5 4-2 6H9l-2-6Zm0 0V2m5 9 5-2m-7 8 3 3m-9-3-3 3m1-9L2 9" /> : <path d="M2 12h20M12 2v20M5 5q14 7 0 14M19 5q-14 7 0 14" />}
    </> : <>
      <circle cx="12" cy="4" r="1.7" fill="currentColor" stroke="none" /><path d="M12 8v7M4 9l8 2 8-2m-8 6-5 7m5-7 5 7" />
    </>}
  </svg>;
}
