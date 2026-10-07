import type { SleepStressNight } from './types';

export function sleepStressStatus(night?: SleepStressNight): string {
  if (!night) return 'No overnight readings available.';
  if (night.status === 'insufficient_baseline') {
    return `Building your baseline: ${night.nights_available ?? 0}/${night.config_snapshot?.baseline_nights_min ?? 7} qualifying previous nights. Keep wearing and syncing your Fitbit overnight.${night.alignment_verified === false ? ' HRV measurement timing also needs verification before a percentage can be shown.' : ''}`;
  }
  if (night.status === 'timing_unverified') return 'Overnight readings received. HRV measurement timing needs verification before a percentage can be shown.';
  if (night.status === 'no_valid_windows') return 'Not enough overlapping sleep, HRV and heart-rate readings.';
  if (night.status === 'pending_processing') return 'Fitbit is still processing this sleep.';
  if (night.status === 'short_sleep') return 'At least three hours of main sleep are needed.';
  return 'Unmeasured time is excluded.';
}
