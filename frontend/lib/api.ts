/**
 * api.ts
 * All fetch calls to the Python FastAPI backend.
 * Automatically uses mock data when no device is connected (handled server-side).
 */

import type { DashboardData, RecoveryData, RecoveryAnalytics, RecoveryDemo, RecoveryRange, SleepData, StrainData, AuthStatus, HealthData, SleepConsistencyScore, SleepStressHistory, SleepStageRangeHistory, SleepHeartRate } from './types';
import { RequestCache } from './requestCache';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const responses = new RequestCache();
let accountFingerprint: string | undefined;

async function apiFetch<T>(path: string, day?: string): Promise<T> {
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const age = window.localStorage.getItem('ojas_age');
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const headers = { 'Content-Type': 'application/json', 'X-User-Date': day ?? localDate, 'X-User-Timezone': timezone, ...(age ? { 'X-User-Age': age } : {}) };
  const fetchData = async () => {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    credentials: 'include', // send session cookie
    headers,
    cache: 'no-store',
    signal: AbortSignal.timeout(120000),
  });
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) responses.clear();
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
  };
  if (path.startsWith('/api/auth/') || path.startsWith('/api/data/')) return fetchData();
  return responses.get(JSON.stringify([BACKEND_URL, path, headers]), fetchData);
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
  getStrain: (day?: string, demo = false): Promise<StrainData> => {
    const params = new URLSearchParams({ demo: String(demo) });
    if (day) params.set('date', day);
    return apiFetch<StrainData>(`/api/strain?${params}`);
  },

  getStrainAnalytics: (timeframe: import('./types').StrainRange = 'W', metric: import('./types').StrainMetric = 'strain', endDate?: string, demo = false): Promise<import('./types').StrainAnalytics> => {
    const params = new URLSearchParams({ timeframe, metric, demo: String(demo) });
    if (endDate) params.set('end_date', endDate);
    return apiFetch<import('./types').StrainAnalytics>(`/api/strain/analytics?${params}`);
  },

  /** Auth: is the user connected to their Fitbit? */
  getAuthStatus: async (): Promise<AuthStatus> => {
    const status = await apiFetch<AuthStatus>('/api/auth/status');
    const fingerprint = JSON.stringify([status.connected, status.user_email]);
    if (accountFingerprint !== fingerprint) responses.clear();
    accountFingerprint = fingerprint;
    return status;
  },

  getDataStatus: () => apiFetch<{ last_synced_at: string | null; stored_ranges: number }>('/api/data/status'),

  syncNow: async () => {
    const response = await fetch(`${BACKEND_URL}/api/data/refresh`, { method: 'POST', credentials: 'include' });
    if (!response.ok) throw new Error('Could not refresh data. Check your connection and retry.');
    responses.clear();
  },

  /** Start Google OAuth flow (redirects browser to Google) */
  startLogin: () => {
    responses.clear();
    window.location.href = `${BACKEND_URL}/api/auth/login`;
  },

  /** Disconnect â€” clear session, return to mock mode */
  disconnect: async (): Promise<void> => {
    const response = await fetch(`${BACKEND_URL}/api/auth/disconnect`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) throw new Error('Could not disconnect. Please retry.');
    responses.clear();
    accountFingerprint = undefined;
  },
};
