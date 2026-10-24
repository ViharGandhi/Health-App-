"""Sleep score vitals compared with the mean of available prior 60-day readings."""
from datetime import date, timedelta
from statistics import mean

from validity import valid_metric
from sleep_rhr import METHOD as RHR_METHOD

WINDOW_DAYS = 60


def sleep_vitals(history, day, age=None):
    start, end = day - timedelta(days=WINDOW_DAYS), day - timedelta(days=1)
    result = {'baseline_window_days': WINDOW_DAYS,
              'baseline_start': start.isoformat(), 'baseline_end': end.isoformat()}
    for metric in ('hrv', 'rhr'):
        dated = {p['date']: p for p in history.get(metric, [])
                 if valid_metric(metric, p.get('value'), age)}
        current = dated.get(day.isoformat(), {})
        method = current.get('method') or RHR_METHOD
        values = [p['value'] for stamp, p in dated.items()
                  if start.isoformat() <= stamp <= end.isoformat()
                  and (metric != 'rhr' or p.get('method') == method)]
        result[metric] = current.get('value')
        result[metric + '_baseline'] = mean(values) if values else None
        result[metric + '_baseline_nights'] = len(values)
    return result


async def load_sleep_vitals(client, day, age=None):
    history = await client.get_health_history(day - timedelta(days=WINDOW_DAYS), day, ('hrv', 'rhr'))
    return sleep_vitals(history, day, age)
