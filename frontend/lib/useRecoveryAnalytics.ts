'use client';

import { useEffect, useState } from 'react';
import { api } from './api';
import type { RecoveryAnalytics, RecoveryDemo, RecoveryRange } from './types';

export function useRecoveryAnalytics(range: RecoveryRange = 'W', endDate?: string) {
  const [data, setData] = useState<RecoveryAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<RecoveryDemo>('estimate');
  const [sleepRevision, setSleepRevision] = useState(0);
  useEffect(() => {
    const update = () => setSleepRevision(value => value + 1);
    window.addEventListener('ojas:sleep-sync', update);
    return () => window.removeEventListener('ojas:sleep-sync', update);
  }, []);
  useEffect(() => {
    if (window.localStorage.getItem('ojas_recovery_demo') === 'legacy') setDemo('legacy');
  }, []);
  useEffect(() => {
    let active = true;
    setError(null);
    api.getRecoveryAnalytics(range, endDate, demo).then(value => { if (active) setData(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Recovery unavailable. Please retry.'); });
    return () => { active = false; };
  }, [range, endDate, demo, sleepRevision]);
  const changeDemo = (value: RecoveryDemo) => {
    window.localStorage.setItem('ojas_recovery_demo', value);
    setDemo(value);
  };
  return { data, error, demo, changeDemo };
}
