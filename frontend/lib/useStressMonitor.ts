'use client';

import { useEffect, useState } from 'react';
import { api } from './api';
import type { StressData } from './stress';

export function useStressMonitor(day: string, demo: boolean | null, days: 7 | 28 = 7) {
  const [data, setData] = useState<StressData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision(v => v + 1);
    const visibleRefresh = () => { if (document.visibilityState === 'visible') refresh(); };
    const timer = window.setInterval(visibleRefresh, 60000);
    window.addEventListener('ojas:dynamic-sync', refresh);
    document.addEventListener('visibilitychange', visibleRefresh);
    return () => { window.clearInterval(timer); window.removeEventListener('ojas:dynamic-sync', refresh); document.removeEventListener('visibilitychange', visibleRefresh); };
  }, []);
  useEffect(() => {
    if (demo == null) return;
    let active = true;
    setData(previous => previous?.current.date === day && previous.is_mock === demo ? previous : null); setError(null);
    api.getStress(day, demo, days).then(value => { if (active) setData(value); })
      .catch(reason => { if (active) { setData(null); setError(reason instanceof Error ? reason.message : 'Stress data could not be loaded.'); } });
    return () => { active = false; };
  }, [day, demo, days, revision]);
  return { data, error, retry: () => setRevision(v => v + 1) };
}
