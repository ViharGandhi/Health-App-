export function activityKind(name: string, type?: string | null) {
  const value = `${type ?? ''} ${name}`.toLowerCase();
  if (/weight|strength|resistance|powerlift/.test(value)) return 'strength';
  if (/walk|hike/.test(value)) return 'walking';
  if (/run|jog/.test(value)) return 'running';
  if (/cycl|bik/.test(value)) return 'cycling';
  if (/swim/.test(value)) return 'swimming';
  if (/yoga|pilates/.test(value)) return 'yoga';
  if (/row/.test(value)) return 'rowing';
  if (/tennis/.test(value)) return 'tennis';
  if (/soccer|football/.test(value)) return 'football';
  if (/basketball/.test(value)) return 'basketball';
  return 'activity';
}

export function activityHref(id: string, day: string, demo: boolean) {
  return `/activity?${new URLSearchParams({ id, date: day, ...(demo ? { demo: 'true' } : {}) })}`;
}

export function clockDuration(minutes: number | null, seconds = false) {
  if (minutes == null) return '—';
  const total = Math.round(minutes * (seconds ? 60 : 1));
  return seconds ? `${Math.floor(total / 3600)}:${String(Math.floor(total / 60) % 60).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
    : `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export function dashboardValue(value: number | null, key: string, unit = '') {
  if (value == null) return '—';
  if (unit === 'duration') return clockDuration(value);
  const digits = key === 'respiratory_rate' || key === 'strain' ? 1 : 0;
  return `${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}${unit}`;
}

export const ZONE_COLORS = ['#FFFFFF', '#B0C5CF', '#48A1C5', '#58BAA0', '#FFAE61', '#FF6A29'];
