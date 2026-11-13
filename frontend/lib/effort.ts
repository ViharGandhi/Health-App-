/** Workout effort on a 1–10 scale, grouped like Apple Watch: Easy, Moderate, Hard, All Out. */
export interface EffortBand { label: 'Easy' | 'Moderate' | 'Hard' | 'All Out'; from: number; to: number; color: string }

export const EFFORT_BANDS: EffortBand[] = [
  { label: 'Easy', from: 1, to: 3, color: '#00D7A1' },
  { label: 'Moderate', from: 4, to: 6, color: '#FFDE00' },
  { label: 'Hard', from: 7, to: 8, color: '#FFA21A' },
  { label: 'All Out', from: 9, to: 10, color: '#FF0026' },
];

export function effortBand(effort: number): EffortBand {
  return EFFORT_BANDS.find(band => effort <= band.to) ?? EFFORT_BANDS[EFFORT_BANDS.length - 1];
}

/**
 * Suggested effort from a workout's heart-rate Strain (0–21). Strain's bands (Light <10,
 * Moderate 10–14, High 14–18, All Out 18+) line up with the effort bands, so each Strain
 * band is spread evenly over its effort numbers. It is only a starting point: how the
 * session felt is the rating that counts.
 */
export function estimateEffort(strain: number | null | undefined): number | null {
  if (strain == null || !Number.isFinite(strain) || strain < 0) return null;
  const spread = (value: number, low: number, high: number, first: number, count: number) =>
    first + Math.min(count - 1, Math.floor((value - low) / (high - low) * count));
  if (strain < 10) return spread(strain, 0, 10, 1, 3);
  if (strain < 14) return spread(strain, 10, 14, 4, 3);
  if (strain < 18) return spread(strain, 14, 18, 7, 2);
  return spread(Math.min(strain, 21), 18, 21, 9, 2);
}
