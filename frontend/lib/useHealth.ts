'use client';

import { useEffect, useState } from 'react';
import { api } from './api';
import type { HealthData } from './types';
import type { HealthRange } from './health';

export function useHealth(range: HealthRange = 'W') {
  const [data, setData] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    api.getHealth(range).then(result => { if (active) setData(result); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Health measurements unavailable.'); });
    return () => { active = false; };
  }, [range, attempt]);
  return { data, error, retry: () => setAttempt(value => value + 1) };
}
