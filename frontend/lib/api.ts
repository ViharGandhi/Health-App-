/**
 * api.ts
 * All fetch calls to the Python FastAPI backend.
 * Automatically uses mock data when no device is connected (handled server-side).
 */

import type { DashboardData, RecoveryData, RecoveryAnalytics, RecoveryDemo, RecoveryRange, SleepData, StrainData, AuthStatus, HealthData, SleepConsistencyScore, SleepStressHistory, SleepStageRangeHistory, SleepHeartRate } from './types';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

async function apiFetch<T>(path: string, day?: string): Promise<T> {
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const age = window.localStorage.getItem('ojas_age');
  const res = await fetch(`${BACKEND_URL}${path}`, {
    credentials: 'include', // send session cookie
    headers: { 'Content-Type': 'application/json', 'X-User-Date': day ?? localDate, ...(age ? { 'X-User-Age': age } : {}) },
    cache: 'no-store',
    signal: AbortSignal.timeout(120000),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  /** Fetch all three scores at once */
  getDashboard: (): Promise<DashboardData> =>
    apiFetch<DashboardData>('/api/dashboard'),

  getRecovery: (demo: RecoveryDemo = 'estimate'): Promise<RecoveryData> =>
    apiFetch<RecoveryData>(`/api/recovery?demo=${demo}`),

  getRecoveryAnalytics: (timeframe: RecoveryRange = 'W', endDate?: string, demo: RecoveryDemo = 'estimate'): Promise<RecoveryAnalytics> => {
    const params = new URLSearchParams({ timeframe, demo });
    if (endDate) params.set('end_date', endDate);
    return apiFetch<RecoveryAnalytics>(`/api/recovery/analytics?${params}`);
  },

  getHealth: (timeframe: 'W' | 'M' | '6M' | '1Y' = 'W'): Promise<HealthData> =>
    apiFetch<HealthData>(`/api/health?timeframe=${timeframe}`),

  getHealthHeartRate: (): Promise<import('./types').HealthHeartRateData> =>
    apiFetch<import('./types').HealthHeartRateData>('/api/health/heart-rate'),

  /** Sleep score + stages */
  getSleep: (): Promise<SleepData> =>
    apiFetch<SleepData>('/api/sleep'),

  getSleepAnalytics: (timeframe: 'W' | 'M' | '6M' = 'W'): Promise<import('./types').SleepAnalytics> =>
    apiFetch<import('./types').SleepAnalytics>(`/api/sleep/analytics?timeframe=${timeframe}`),

  getSleepStress: (timeframe: 'W' | 'M' | '6M' = 'W'): Promise<SleepStressHistory> =>
    apiFetch<SleepStressHistory>(`/api/sleep/stress?timeframe=${timeframe}`),

  getSleepStageRanges: (): Promise<SleepStageRangeHistory> =>
    apiFetch<SleepStageRangeHistory>('/api/sleep/stages/typical-ranges?days=10'),

  getSleepHeartRate: (nightDate?: string, sleepId?: string): Promise<SleepHeartRate> => {
    const params = new URLSearchParams();
    if (nightDate) params.set('night_date', nightDate);
    if (sleepId) params.set('sleep_id', sleepId);
    return apiFetch<SleepHeartRate>(`/api/sleep/heart-rate?${params}`);
  },

  /** Sleep consistency trend history */
  getSleepConsistencyTrend: (timeframe: string = 'W'): Promise<import('./types').SleepTrend> =>
    apiFetch<import('./types').SleepTrend>(`/api/sleep/consistency?timeframe=${timeframe}`),

  getSleepConsistencyScore: (timeframe: 'W' | 'M' | '6M' | 'Y' = 'W'): Promise<SleepConsistencyScore> =>
    apiFetch<SleepConsistencyScore>(`/api/sleep/consistency/score?timeframe=${timeframe}`),

  /** Sleep efficiency trend history */
  getSleepEfficiencyTrend: (timeframe: string = 'W'): Promise<import('./types').SleepTrend> =>
    apiFetch<import('./types').SleepTrend>(`/api/sleep/efficiency?timeframe=${timeframe}`),



  /** Strain score + zones */
  getStrain: (day?: string): Promise<StrainData> =>
    apiFetch<StrainData>('/api/strain', day),

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
