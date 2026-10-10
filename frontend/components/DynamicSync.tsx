'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { api } from '@/lib/api';
import { DynamicSyncSchedule } from '@/lib/dynamicSyncSchedule';

let schedule: DynamicSyncSchedule | undefined;
let appSession: string | undefined;
let reloadSession: string | undefined;

export default function DynamicSync() {
  const pathname = usePathname();
  const [message, setMessage] = useState('');
  const [lastSynced, setLastSynced] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('demo') === 'true') return;
    appSession ??= crypto.randomUUID();
    schedule ??= new DynamicSyncSchedule(async (force, homeVisit) => {
      const session = force && !homeVisit ? (reloadSession ??= crypto.randomUUID()) : appSession!;
      const result = await api.syncDynamic(force, session, homeVisit);
      if (!result.connected) return true;
      return result.synced || Boolean('data_updated' in result && result.data_updated);
    });
    let active = true;
    let timer: number | undefined;
    const armTimer = (failed = false) => {
      if (!active) return;
      if (timer) window.clearTimeout(timer);
      const remaining = failed || schedule!.pending || schedule!.lastSuccess == null ? 30000
        : Math.max(1, 900000 - (Date.now() - schedule!.lastSuccess));
      timer = window.setTimeout(() => { void check(); }, document.hidden ? 900000 : remaining);
    };
    const check = async (homeVisit = false) => {
      let failed = false;
      try {
        const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
        if (navigation?.type === 'reload' && !schedule!.reloadHandled) await schedule!.reload(!document.hidden);
        else if (homeVisit) await schedule!.visit(!document.hidden);
        else await schedule!.check(!document.hidden);
        if (active) setMessage('');
      } catch {
        failed = true;
        if (active) setMessage('Sync failed. Your saved stats are still available.');
      } finally { armTimer(failed); }
    };
    const synced = (event: Event) => {
      const completed = (event as CustomEvent<{ completed?: number }>).detail?.completed;
      const timestamp = completed ? completed * 1000 : Date.now();
      schedule!.lastSuccess = timestamp;
      if (active) { setLastSynced(timestamp); setConnected(true); }
      armTimer();
    };
    const statusChanged = (event: Event) => {
      const completed = (event as CustomEvent<{ completed: number | null }>).detail.completed;
      if (completed != null) {
        schedule!.lastSuccess = completed * 1000;
        if (active) { setLastSynced(completed * 1000); setConnected(true); }
      }
    };
    const returned = () => { if (!document.hidden) void check(pathname === '/'); };
    window.addEventListener('ojas:dynamic-sync', synced);
    window.addEventListener('ojas:sync-status', statusChanged);
    document.addEventListener('visibilitychange', returned);
    window.addEventListener('focus', returned);
    void api.getDataStatus().then(status => {
      if (!active) return;
      setConnected(true);
      const timestamp = status.last_synced_at ? Date.parse(status.last_synced_at) : null;
      setLastSynced(current => current == null ? timestamp : timestamp == null ? current : Math.max(current, timestamp));
      if (schedule!.lastSuccess == null) schedule!.lastSuccess = timestamp;
      void check(pathname === '/');
    }).catch(() => { if (active) void check(pathname === '/'); });
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', returned);
      window.removeEventListener('focus', returned);
      window.removeEventListener('ojas:dynamic-sync', synced);
      window.removeEventListener('ojas:sync-status', statusChanged);
    };
  }, [pathname]);
  if (!connected && !message) return null;
  const label = lastSynced == null ? 'Not synced yet' : `Last synced: ${new Date(lastSynced).toLocaleString([], {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })}`;
  return <div style={{ margin: '8px 16px', fontSize: 12, color: '#AEB8C1' }}>
    {connected && <p style={{ margin: 0 }}>{label}</p>}
    {message && <p role="status" style={{ margin: '4px 0 0' }}>{message}</p>}
  </div>;
}
