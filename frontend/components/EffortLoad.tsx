'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { EffortHistory } from '@/lib/types';

function shift(day: string, days: number) {
  const value = new Date(`${day}T12:00:00`);
  value.setDate(value.getDate() + days);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

/** Effort load from rated workouts (effort × minutes, session RPE), shown apart from cardio Strain. */
export default function EffortLoad({ day, isMock, className }: { day: string; isMock: boolean; className?: string }) {
  const [history, setHistory] = useState<EffortHistory | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (isMock) return;
    let active = true;
    api.getEfforts(shift(day, -27), day).then(value => { if (active) setHistory(value); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [day, isMock]);
  if (isMock) return <p className={className}>Effort load: rate a workout's effort on its activity page (effort × minutes). Sample data is not saved.</p>;
  if (failed) return <p className={className}>Effort load is unavailable right now.</p>;
  if (!history) return null;
  if (!history.ratings.length) return <p className={className}>Effort load: no rated workouts in the last 28 days. Rate a workout's effort on its activity page to track it.</p>;
  const sum = (from: string) => Object.entries(history.daily_load).filter(([date]) => date >= from && date <= day).reduce((total, [, load]) => total + load, 0);
  const week = sum(shift(day, -6)), weekly28 = sum(shift(day, -27)) / 4;
  return <p className={className}>Effort load (effort × minutes): today {(history.daily_load[day] ?? 0).toLocaleString('en-US')} · last 7 days {week.toLocaleString('en-US')} · 4-week weekly average {Math.round(weekly28).toLocaleString('en-US')}. Not included in Day Strain.</p>;
}
