"""Quantify proposed behaviors without changing production scoring/selection."""
from pathlib import Path
import json
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from sleepscore import SleepCalculator, SleepData

OUT = Path(__file__).resolve().parent
rng = random.Random(20261009)


def alternatives(sleep, need, age, hrv, sleeping_hr=None, waking_hr=None):
    calc = lambda **kw: SleepCalculator.calculate_score(sleep, need, hrv_baseline=41.2, sleeping_hr_baseline=60., age=age, **kw)
    current = calc()
    return {'current_defaults': current, 'defaulted_weight': .28, 'defaulted_points': 14.,
            'available_points_without_defaults': current - 14.,
            'renormalized_available': (current - 14.) / .72,
            'join_available_daily_hrv_only': calc(sleeping_hrv=hrv),
            'hypothetical_all_three_joined': calc(sleeping_hrv=hrv, sleeping_hr=sleeping_hr, waking_hr=waking_hr)
                if sleeping_hr is not None and waking_hr is not None else None,
            'withhold_below_75pct_coverage': None}


profiles = []
for row in json.loads((OUT / 'baseline/adversarial-profiles.json').read_text()):
    data = row['inputs']
    actual = data['sleep_minutes'] * 60
    sleep = SleepData(actual, actual * .2, actual * .2, actual * .6,
                      540 * 60 - actual, 540 * 60, None, None, 0)
    hrv = row['recovery']['today_hrv']
    profiles.append({'profile': row['profile'], 'inputs': data,
        'original_connected_score': row['sleep_score'],
        **alternatives(sleep, row['sleep_need']['total_need_min'] / 60, data['age'], hrv),
        'joined_fields_actually_available_in_fixture': ['daily_hrv'],
        'unavailable': ['nrem_hr', 'overnight_hr', 'current_day_awake_hr']})

random_nights = []
for i in range(1000):
    need = rng.uniform(6, 11)
    actual = need * rng.uniform(.4, 1.3) * 3600
    awake = rng.uniform(0, 90) * 60
    deep, rem = rng.uniform(.05, .25), rng.uniform(.1, .3)
    age = rng.randrange(18, 101)
    sleep = SleepData(actual, actual * deep, actual * rem, actual * (1 - deep - rem),
                      awake, actual + awake, None, None, rng.randrange(11))
    hrv, sleeping_hr, waking_hr = rng.uniform(10, 150), rng.uniform(42, 90), rng.uniform(55, 110)
    random_nights.append({'night': i, 'inputs': {'need_hours': need, 'asleep_seconds': actual, 'awake_seconds': awake,
        'deep_fraction': deep, 'rem_fraction': rem, 'age': age, 'hrv': hrv, 'sleeping_hr': sleeping_hr,
        'waking_hr': waking_hr, 'interruptions': sleep.interruption_count},
        **alternatives(sleep, need, age, hrv, sleeping_hr, waking_hr)})
keys = ['current_defaults', 'available_points_without_defaults', 'renormalized_available',
        'join_available_daily_hrv_only', 'hypothetical_all_three_joined']
summary = {key: {'min': min(r[key] for r in random_nights), 'max': max(r[key] for r in random_nights),
    'mean': sum(r[key] for r in random_nights) / 1000} for key in keys}
(OUT / 'sleep-component-options.json').write_text(json.dumps({'seed': 20261009, 'profiles': profiles,
    'random_nights': random_nights, 'summary': summary, 'coverage_threshold_is_only_an_example': .75,
    'warning': 'Candidate daily HRV is not yet verified as comparable sleeping HRV; all-three random joins are hypothetical.'}, indent=2))
print(json.dumps({'profiles': [{k: row[k] for k in ('profile', 'current_defaults', 'join_available_daily_hrv_only', 'renormalized_available')}
                             for row in profiles], 'random_summary': summary}, indent=2))
