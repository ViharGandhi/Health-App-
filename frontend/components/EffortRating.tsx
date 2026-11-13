'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import RatingScale from './RatingScale';

const WORDS = ['', 'very easy', 'easy', 'moderate', 'somewhat hard', 'hard', 'hard', 'very hard', 'very hard', 'near max', 'maximal'];

/** Session RPE for a strength activity. Muscular load = effort × minutes, kept apart from cardio Strain. */
export default function EffortRating({ activityId, date, minutes, isMock }: { activityId: string; date: string; minutes: number | null; isMock: boolean }) {
  const [rpe, setRpe] = useState<number | null>(null);
  const [busy, setBusy] = useState(!isMock);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (isMock) return;
    let active = true;
    api.getEfforts(date, date).then(result => {
      if (active) setRpe(result.ratings.find(rating => rating.activity_id === activityId)?.rpe ?? null);
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Saved rating unavailable.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [activityId, date, isMock]);

  const select = async (value: number) => {
    setError(null);
    if (isMock || minutes == null) { setRpe(value); return; }
    const previous = rpe;
    setRpe(value); setBusy(true);
    try { await api.saveEffort({ activity_id: activityId, date, rpe: value, minutes }); }
    catch (reason) { setRpe(previous); setError(reason instanceof Error ? reason.message : 'Could not save. Please retry.'); }
    finally { setBusy(false); }
  };
  const clear = async () => {
    setBusy(true); setError(null);
    try { if (!isMock) await api.deleteEffort(activityId); setRpe(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not clear. Please retry.'); }
    finally { setBusy(false); }
  };
  const load = rpe != null && minutes != null ? Math.round(rpe * minutes) : null;
  const status = rpe == null ? (minutes == null ? 'This session has no recorded duration, so its load cannot be calculated.' : 'Tap how hard the whole session felt.')
    : `Effort ${rpe} (${WORDS[rpe]}) × ${Math.round(minutes ?? 0)} min = muscular load ${load ?? '—'}.${isMock ? ' Sample data: ratings are not saved.' : ' Saved to your account.'}`;
  return <RatingScale title="SESSION EFFORT" question="How hard was this session overall?" value={rpe} busy={busy || minutes == null}
    options={Array.from({ length: 10 }, (_, i) => ({ value: i + 1 }))} onSelect={select} status={status} error={error}>
    <p style={{ marginTop: 8, fontSize: 10, color: 'var(--text-tertiary)', display: 'flex', justifyContent: 'space-between' }}><span>1 very easy</span><span>5 hard</span><span>10 maximal</span></p>
    {rpe != null && <button type="button" onClick={clear} disabled={busy} style={{ marginTop: 6, border: 0, background: 'none', color: 'var(--text-secondary)', font: 'inherit', fontSize: 11, textDecoration: 'underline', cursor: 'pointer', padding: 0 }}>Clear rating</button>}
    <p style={{ marginTop: 8, fontSize: 10, lineHeight: 1.5, color: 'var(--text-tertiary)' }}>Muscular load is shown on its own. Day Strain stays heart-rate only.</p>
  </RatingScale>;
}
