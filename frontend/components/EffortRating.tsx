'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { EFFORT_BANDS, effortBand } from '@/lib/effort';
import styles from './EffortRating.module.css';

/**
 * Apple Watch-style workout effort (1–10). Effort load = effort × minutes (session RPE),
 * kept apart from heart-rate Day Strain. `estimate` comes from the workout's Strain and is
 * only saved when the user keeps it or picks a number.
 */
export default function EffortRating({ activityId, date, minutes, isMock, estimate }: {
  activityId: string; date: string; minutes: number | null; isMock: boolean; estimate: number | null;
}) {
  const [rpe, setRpe] = useState<number | null>(null);
  const [busy, setBusy] = useState(!isMock);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (isMock) return;
    let active = true;
    api.getEfforts(date, date).then(result => {
      if (active) setRpe(result.ratings.find(rating => rating.activity_id === activityId)?.rpe ?? null);
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Saved effort unavailable.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [activityId, date, isMock]);

  const save = async (value: number) => {
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

  const shown = rpe ?? estimate;
  const band = shown == null ? null : effortBand(shown);
  const status = minutes == null ? 'This workout has no recorded duration, so its effort load cannot be calculated.'
    : rpe != null ? `Effort ${rpe} × ${Math.round(minutes)} min = effort load ${Math.round(rpe * minutes)}.${isMock ? ' Sample data: not saved.' : ' Saved.'}`
    : estimate != null ? 'Estimated from your heart rate. Keep it, or tap the number that matches how it felt.'
    : 'Tap the number that matches how hard the whole workout felt.';
  return <section className={styles.card} aria-label="Workout effort">
    <div className={styles.header}>
      <h2>EFFORT</h2>
      {band && shown != null && <p className={rpe == null ? styles.estimated : undefined}>
        <strong style={{ color: band.color }}>{shown}</strong><span>{band.label}{rpe == null ? ' · estimated' : ''}</span>
      </p>}
    </div>
    <div className={styles.scale} role="radiogroup" aria-label="How hard was this workout overall?">
      {Array.from({ length: 10 }, (_, i) => i + 1).map(value => {
        const filled = shown != null && value <= shown;
        return <button key={value} type="button" role="radio" aria-checked={rpe === value}
          aria-label={`${value}, ${effortBand(value).label}`} disabled={busy || minutes == null} onClick={() => save(value)}
          className={`${filled ? styles.filled : ''} ${rpe == null && filled ? styles.ghost : ''}`}
          style={{ height: 22 + value * 4, '--band': effortBand(value).color } as React.CSSProperties}>
          <span>{value}</span>
        </button>;
      })}
    </div>
    <div className={styles.legend}>{EFFORT_BANDS.map(item => <span key={item.label} style={{ flexGrow: item.to - item.from + 1 }}>
      <i style={{ background: item.color }} />{item.label}</span>)}</div>
    <p className={styles.status} role="status">{status}</p>
    <div className={styles.actions}>
      {rpe == null && estimate != null && minutes != null && <button type="button" onClick={() => save(estimate)} disabled={busy}>Keep estimate</button>}
      {rpe != null && <button type="button" onClick={clear} disabled={busy}>Clear</button>}
    </div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    <p className={styles.note}>Effort load is shown on its own. Day Strain stays heart-rate only.</p>
  </section>;
}
