let pending = 0;
const listeners = new Set<() => void>();

export const getSyncActivity = () => pending > 0;
export const getServerSyncActivity = () => false;
export function subscribeSyncActivity(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export async function trackSyncActivity<T>(sync: () => Promise<T>): Promise<T> {
  pending += 1;
  listeners.forEach(listener => listener());
  try {
    return await sync();
  } finally {
    pending -= 1;
    listeners.forEach(listener => listener());
  }
}
