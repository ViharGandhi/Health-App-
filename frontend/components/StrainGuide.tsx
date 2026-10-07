'use client';

import { useEffect, useRef } from 'react';
import shared from '@/app/recovery/page.module.css';

export default function StrainGuide({ onClose }: { onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null, overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden'; panel.current?.querySelector('button')?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') { event.preventDefault(); panel.current?.querySelector('button')?.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', key); previous?.focus(); };
  }, [onClose]);
  return <div className={shared.modalBackdrop} onClick={onClose}><div ref={panel} role="dialog" aria-modal="true" aria-labelledby="strain-guide-title" className={shared.modal} onClick={event => event.stopPropagation()}>
    <button aria-label="Close Strain guide" onClick={onClose}>×</button><h2 id="strain-guide-title">Understanding Strain</h2>
    <p>The 0–21 value is this app&apos;s cardio estimate. HR reserve uses your age-based maximum heart rate and the median resting HR from the last seven nights. Banister TRIMP counts effort at 20%+ HR reserve; the saturating curve uses L = 90 by default. It approximates WHOOP-style cardio Strain; WHOOP&apos;s formula is proprietary.</p>
    <p>The day starts at your latest main wake time, with local midnight as the fallback. Duplicate, impossible, and isolated spike readings are removed. Gaps up to five minutes are bridged; longer gaps add no time or load. Coverage is the fraction of the day window with counted HR time; below 60% is flagged.</p>
    <p>Zone charts show only logged activity time. Display zones use 50–60%, 60–70%, 70–80%, 80–90%, and 90%+ of maximum heart rate. The full day&apos;s cardio load includes effort outside logged activities. Zone boundaries do not set TRIMP weights.</p>
    <p>Activity badges use the same 0–21 curve on each workout&apos;s load. Overlapping intervals go to the first workout by start time; workout scores are not additive. Muscular Load is unavailable. Strength activity time and synced Steps retain their existing sources.</p>
    <p>W shows daily readings. For duration metrics, M shows four weekly totals and 6M shows weekly bars with monthly averages of complete weekly totals. Strain and Steps use daily bars. Today is excluded from average Day Strain. Missing values are excluded from averages; a week with missing zone readings has no total.</p>
    <p>Hover, tap, or use arrow keys to select a period. Tap the selected bar again or press Escape to clear it. Comparisons use the preceding equal period. A missing or zero prior value has no relative percentage comparison.</p>
    <p>Default Recovery-based target bands are 14–18 at 67%+ Recovery, 10–14 at 34–66%, and 4–10 below 34%. A missing Recovery score has no target. Adding activities and changing a step goal remain unavailable. Missing age prevents load and zone calculations; default resting HR or sex coefficients are disclosed.</p>
  </div></div>;
}
