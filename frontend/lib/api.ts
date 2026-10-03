/**
 * api.ts
 * All fetch calls to the Python FastAPI backend.
 * Automatically uses mock data when no device is connected (handled server-side).
 */

import type { DashboardData, RecoveryData, SleepData, StrainData, AuthStatus, HealthData, SleepConsistencyScore, SleepStressHistory } from './types';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

async function apiFetch<T>(path: string): Promise<T> {
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const age = window.localStorage.getItem('ojas_age');
  const res = await fetch(`${BACKEND_URL}${path}`, {
    credentials: 'include', // send session cookie
    headers: { 'Content-Type': 'application/json', 'X-User-Date': localDate, ...(age ? { 'X-User-Age': age } : {}) },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  /** Fetch all three scores at once */
  getDashboard: (): Promise<DashboardData> =>
    apiFetch<DashboardData>('/api/dashboard'),

  /** Recovery signals, with a prototype score in demo mode */
  getRecovery: (): Promise<RecoveryData> =>
    apiFetch<RecoveryData>('/api/recovery'),

  getHealth: (timeframe: 'W' | '6M' | '1Y' = 'W'): Promise<HealthData> =>
    apiFetch<HealthData>(`/api/health?timeframe=${timeframe}`),

  /** Sleep score + stages */
  getSleep: (): Promise<SleepData> =>
    apiFetch<SleepData>('/api/sleep'),

  getSleepStress: (timeframe: 'W' | 'M' | '6M' = 'W'): Promise<SleepStressHistory> =>
    apiFetch<SleepStressHistory>(`/api/sleep/stress?timeframe=${timeframe}`),

  /** Sleep consistency trend history */
  getSleepConsistencyTrend: (timeframe: string = 'W'): Promise<import('./types').SleepTrend> =>
    apiFetch<import('./types').SleepTrend>(`/api/sleep/consistency?timeframe=${timeframe}`),

  getSleepConsistencyScore: (timeframe: 'W' | 'M' | 'Y' = 'W'): Promise<SleepConsistencyScore> =>
    apiFetch<SleepConsistencyScore>(`/api/sleep/consistency/score?timeframe=${timeframe}`),

  /** Sleep efficiency trend history */
  getSleepEfficiencyTrend: (timeframe: string = 'W'): Promise<import('./types').SleepTrend> =>
    apiFetch<import('./types').SleepTrend>(`/api/sleep/efficiency?timeframe=${timeframe}`),



  /** Strain score + zones */
  getStrain: (): Promise<StrainData> =>
    apiFetch<StrainData>('/api/strain'),

  /** Auth: is the user connected to their Fitbit? */
  getAuthStatus: (): Promise<AuthStatus> =>
    apiFetch<AuthStatus>('/api/auth/status'),

  /** Start Google OAuth flow (redirects browser to Google) */
  startLogin: () => {
    window.location.href = `${BACKEND_URL}/api/auth/login`;
  },

  /** Disconnect â€” clear session, return to mock mode */
  disconnect: async (): Promise<void> => {
    await fetch(`${BACKEND_URL}/api/auth/disconnect`, {
      method: 'POST',
      credentials: 'include',
    });
  },
};
