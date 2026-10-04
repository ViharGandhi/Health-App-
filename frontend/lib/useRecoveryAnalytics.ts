'use client';

import { useEffect, useState } from 'react';
import { api } from './api';
import type { RecoveryAnalytics, RecoveryDemo, RecoveryRange } from './types';

export function useRecoveryAnalytics(range: RecoveryRange = 'W', endDate?: string) {
  const [data, setData] = useState<RecoveryAnalytics | null>(null);
  const [error, setError] = useState(false);
  const [demo, setDemo] = useState<RecoveryDemo>('estimate');
  useEffect(() => {
    if (window.localStorage.getItem('ojas_recovery_demo') === 'legacy') setDemo('legacy');
  }, []);
  useEffect(() => {
    let active = true;
    setData(null);
    setError(false);
    api.getRecoveryAnalytics(range, endDate, demo).then(value => { if (active) setData(value); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [range, endDate, demo]);
  const changeDemo = (value: RecoveryDemo) => {
    window.localStorage.setItem('ojas_recovery_demo', value);
    setDemo(value);
  };
  return { data, error, demo, changeDemo };
}
