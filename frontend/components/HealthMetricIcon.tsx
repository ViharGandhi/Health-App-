import RecoveryMetricIcon from './RecoveryMetricIcon';

export default function HealthMetricIcon({ metric, size = 23 }: { metric: string; size?: number }) {
  if (metric === 'hrv' || metric === 'deep_sleep_hrv') return <RecoveryMetricIcon metric="hrv" size={size} />;
  if (metric === 'rhr' || metric === 'nrem_hr' || metric === 'heart_rate') return <RecoveryMetricIcon metric="rhr" size={size} />;
  if (metric === 'respiratory_rate' || metric === 'vo2_max') return <RecoveryMetricIcon metric="respiratory_rate" size={size} />;
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {metric === 'skin_temperature' ? <><path d="M9 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0Z" /><path d="M12 8v10M18 6h3m-3 4h3" /><circle cx="12" cy="18" r="1" /></>
      : <><path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13Z" /><path d="m9 17 6-6" /><circle cx="9" cy="11" r="1" /><circle cx="15" cy="17" r="1" /></>}
  </svg>;
}
