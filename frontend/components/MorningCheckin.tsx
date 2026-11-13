'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import RatingScale from './RatingScale';

const OPTIONS = [{ value: 1, label: 'Awful' }, { value: 2, label: 'Poor' }, { value: 3, label: 'Okay' }, { value: 4, label: 'Good' }, { value: 5, label: 'Great' }];
const FIT_DAYS = 42;

/** One-tap morning wellness rating, saved per day so Recovery can later be compared with how you felt. */
export default function MorningCheckin({ day, isMock }: { day: string; isMock: boolean }) {
  const [feeling, setFeeling] = useState<number | null>(null);
  const [count, setCount] = useState<number | null>(null);
  const [busy, setBusy] = useState(!isMock);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (isMock) return;
    let active = true;
    const start = new Date(`${day}T12:00:00`);
    start.setDate(start.getDate() - 399);
    api.getCheckins(`${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`, day).then(result => {
      if (!active) return;
      setFeeling(result.checkins.find(item => item.date === day)?.feeling ?? null);
      setCount(result.checkins.length);
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Saved check-in unavailable.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [day, isMock]);

  const select = async (value: number) => {
    setError(null);
    if (isMock) { setFeeling(value); return; }
    const previous = feeling;
    setFeeling(value); setBusy(true);
    try {
      await api.saveCheckin({ date: day, feeling: value });
      if (previous == null) setCount(total => (total ?? 0) + 1);
    } catch (reason) { setFeeling(previous); setError(reason instanceof Error ? reason.message : 'Could not save. Please retry.'); }
    finally { setBusy(false); }
  };
  const status = isMock ? 'Sample data: check-ins are not saved.'
    : feeling == null ? 'Answer with how you feel, not with what the score says.'
    : `Saved. ${count != null && count < FIT_DAYS ? `${count} of about ${FIT_DAYS} mornings needed to compare Recovery with how you feel.` : 'Enough mornings to start comparing Recovery with how you feel.'}`;
  return <RatingScale title="MORNING CHECK-IN" question="How do you feel this morning?" options={OPTIONS} value={feeling} busy={busy}
    onSelect={select} status={status} error={error} />;
}
