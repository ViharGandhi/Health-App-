/**
 * api.ts
 * All fetch calls to the Python FastAPI backend.
 * Automatically uses mock data when no device is connected (handled server-side).
 */

import type { DashboardData, RecoveryData, RecoveryAnalytics, RecoveryDemo, RecoveryRange, SleepData, StrainData, AuthStatus, HealthData, SleepConsistencyScore, SleepStressHistory, SleepStageRangeHistory, SleepHeartRate, EffortHistory, EffortRating, MorningCheckin, TrainingLoad } from './types';
import { RequestCache } from './requestCache';
import { trackSyncActivity } from './syncActivity';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const responses = new RequestCache();
let accountFingerprint: string | undefined;

/** Whole years on `day` (YYYY-MM-DD) for a YYYY-MM-DD birth date. */
export function ageOn(birthDate: string, day: string): number {
  const [by, bm, bd] = birthDate.split('-').map(Number), [y, m, d] = day.split('-').map(Number);
  return y - by - (m < bm || (m === bm && d < bd) ? 1 : 0);
}

// Age from the saved birth date, so it stays right after each birthday; older saves kept only an age.
function storedAge(): string | null {
  const birthDate = window.localStorage.getItem('ojas_birth_date');
  if (!birthDate) return window.localStorage.getItem('ojas_age');
  const today = new Date();
  return String(ageOn(birthDate, `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`));
}

// The user's own max heart rate replaces the age estimate in Strain.
function maxHrHeader(): Record<string, string> {
  const value = window.localStorage.getItem('ojas_max_hr');
  return value ? { 'X-User-Max-HR': value } : {};
}

// Ratings and check-ins the user enters; never cached so a save shows at once.
async function inputFetch<T>(method: 'GET' | 'PUT' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const today = new Date();
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method, credentials: 'include', cache: 'no-store', signal: AbortSignal.timeout(30000),
    headers: { 'Content-Type': 'application/json', 'X-User-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone,
      'X-User-Date': `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}` },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : 'Could not save. Please retry.');
  }
  return res.json() as Promise<T>;
}

async function apiFetch<T>(path: string, day?: string): Promise<T> {
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const age = storedAge();
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const headers = { 'Content-Type': 'application/json', 'X-User-Date': day ?? localDate, 'X-User-Timezone': timezone, ...(age ? { 'X-User-Age': age } : {}), ...maxHrHeader() };
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
  // Training load reflects effort ratings, which must show as soon as they are saved.
  if (path.startsWith('/api/auth/') || path.startsWith('/api/data/') || path.startsWith('/api/training-load')) return fetchData();
  return responses.get(JSON.stringify([BACKEND_URL, path, headers]), fetchData, path.startsWith('/api/stress?') ? 30000 : 120000);
}

export const api = {
  getStress: (day: string, demo = false, days: 7 | 28 = 7): Promise<import('./stress').StressData> =>
    apiFetch<import('./stress').StressData>(`/api/stress?demo=${demo}&days=${days}`, day),

  /** Fetch all three scores at once */
  getDashboard: (): Promise<DashboardData> =>
    apiFetch<DashboardData>('/api/dashboard'),

  getRecovery: (demo: RecoveryDemo = 'estimate'): Promise<RecoveryData> =>
    apiFetch<RecoveryData>(`/api/recovery?demo=${demo}`),

  getRecoveryAnalytics: (timeframe: RecoveryRange = 'W', endDate?: string, demo: RecoveryDemo = 'estimate', sample = false): Promise<RecoveryAnalytics> => {
    const params = new URLSearchParams({ timeframe, demo });
    if (sample) params.set('sample', 'true');
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

  getHomeMetrics: (day?: string, demo = false): Promise<import('./types').HomeMetrics> =>
    apiFetch<import('./types').HomeMetrics>(`/api/home/metrics?demo=${demo}`, day),

  getActivity: (id: string, day?: string, demo = false, source = 'home'): Promise<import('./types').ActivityData> =>
    apiFetch<import('./types').ActivityData>(`/api/activity?${new URLSearchParams({ id, demo: String(demo), source })}`, day),

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

  getEfforts: (start?: string, end?: string) =>
    inputFetch<EffortHistory>('GET', `/api/effort?${new URLSearchParams({ ...(start ? { start } : {}), ...(end ? { end } : {}) })}`),

  saveEffort: (rating: { activity_id: string; date: string; rpe: number; minutes: number }) =>
    inputFetch<EffortRating>('PUT', '/api/effort', rating),

  deleteEffort: (id: string) => inputFetch<{ deleted: boolean }>('DELETE', `/api/effort/${encodeURIComponent(id)}`),

  getCheckins: (start?: string, end?: string) =>
    inputFetch<{ checkins: MorningCheckin[] }>('GET', `/api/checkins?${new URLSearchParams({ ...(start ? { start } : {}), ...(end ? { end } : {}) })}`),

  saveCheckin: (checkin: MorningCheckin) => inputFetch<MorningCheckin>('PUT', '/api/checkins', checkin),

  getTrainingLoad: (demo = false) => apiFetch<TrainingLoad>(`/api/training-load?demo=${demo}`),

  getProfile: () => inputFetch<{ birth_date: string | null; age: number | null }>('GET', '/api/profile'),

  saveProfile: (birthDate: string) => inputFetch<{ birth_date: string | null; age: number | null }>('PUT', '/api/profile', { birth_date: birthDate }),

  getDataStatus: () => apiFetch<{ last_synced_at: string | null; stored_ranges: number }>('/api/data/status'),

  recalculateSleepAwakeHeartRate: async (): Promise<{ sleep: SleepData }> => trackSyncActivity(async () => {
    const today = new Date();
    const age = storedAge();
    const response = await fetch(`${BACKEND_URL}/api/sleep/awake-heart-rate/recalculate`, {
      method: 'POST', credentials: 'include', signal: AbortSignal.timeout(180000),
      headers: {
        'X-User-Date': `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
        'X-User-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone,
        ...(age ? { 'X-User-Age': age } : {}),
        ...maxHrHeader(),
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail || 'Could not recalculate awake heart rate. Try again.');
    }
    const result = await response.json();
    responses.clear();
    window.dispatchEvent(new CustomEvent('ojas:sleep-sync'));
    return result;
  }),

  syncNow: async () => {
    await api.syncDynamic(true, crypto.randomUUID());
  },

  syncDynamic: async (force: boolean, session: string, homeVisit = false) => trackSyncActivity(async () => {
    const today = new Date();
    const age = storedAge();
    const response = await fetch(`${BACKEND_URL}/api/data/sync?${new URLSearchParams({ force: String(force), session, home_visit: String(homeVisit) })}`, {
      method: 'POST', credentials: 'include', signal: AbortSignal.timeout(120000),
      headers: { 'X-User-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone,
        'X-User-Date': `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
        ...(age ? { 'X-User-Age': age } : {}), ...maxHrHeader() },
    });
    if (response.status === 401) return { synced: false, connected: false };
    if (!response.ok) throw new Error('Activity sync failed. Saved stats are still available.');
    const result = await response.json() as { synced: boolean; data_updated?: boolean; sleep_updated?: boolean; cursor: string | null; completed: number | null };
    window.dispatchEvent(new CustomEvent('ojas:sync-status', { detail: { completed: result.completed } }));
    if (result.synced || result.data_updated) {
      responses.clear();
      window.dispatchEvent(new CustomEvent('ojas:dynamic-sync', { detail: { completed: result.completed } }));
      if (result.sleep_updated) window.dispatchEvent(new CustomEvent('ojas:sleep-sync'));
    }
    return { ...result, connected: true };
  }),

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
