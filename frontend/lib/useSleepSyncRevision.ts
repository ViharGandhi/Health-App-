'use client';

import { useEffect, useState } from 'react';

/** Refresh an open sleep view after all of today's saved results are ready. */
export function useSleepSyncRevision() {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const update = () => setRevision(value => value + 1);
    window.addEventListener('ojas:sleep-sync', update);
    return () => window.removeEventListener('ojas:sleep-sync', update);
  }, []);
  return revision;
}
