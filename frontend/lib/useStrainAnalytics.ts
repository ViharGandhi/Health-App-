'use client';

import { useEffect, useState } from 'react';
import { api } from './api';
import type { StrainAnalytics, StrainMetric, StrainRange } from './types';

export function useStrainAnalytics(range: StrainRange = 'W', metric: StrainMetric = 'strain', endDate?: string) {
  const [data, setData] = useState<StrainAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [demo, setDemo] = useState<boolean | null>(null);
  useEffect(() => { setDemo(new URLSearchParams(window.location.search).get('demo') === 'true'); }, []);
  useEffect(() => {
    if (demo == null) return;
    let active = true;
    setData(null); setError(null);
    api.getStrainAnalytics(range, metric, endDate, demo).then(value => { if (active) setData(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Strain unavailable. Please retry.'); });
    return () => { active = false; };
  }, [range, metric, endDate, demo, attempt]);
  return { data, error, demo: demo ?? false, retry: () => setAttempt(value => value + 1) };
}
