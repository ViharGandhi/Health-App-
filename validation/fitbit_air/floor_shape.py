"""Step at 40% HRR vs. a ramp from 30% to 40% for everyday heart rate: level and sensitivity."""
import sys
from datetime import timedelta
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / 'backend'), str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
from strain import clean_samples, strain_score
import real_data, strain_check as sc

def ramp(hrr, in_workout):
    if in_workout:
        return 1. if hrr >= .2 else 0.
    return max(0., min(1., (hrr - .3) / .1))

account = real_data.accounts_with_heart_rate()[0]
S, W = real_data.heart_rate(account), real_data.exercises(account)
rhr = real_data.daily(account, 'daily-resting-heart-rate', 'dailyRestingHeartRate', 'beatsPerMinute')
print('day         rule  strain  rest-5  rest+5  max-10  max+10')
for day, window in sc.days(S):
    inside = [p for p in S if window['start'] <= p[0] < window['end']]
    rest = [rhr[d] for d in sorted(rhr) if day - timedelta(days=6) <= d <= day]
    base = sc.run(inside, W, window, rest)
    r, m = base['params']['hr_rest'], base['params']['hr_max']
    cleaned = clean_samples(inside, window, sc.CONFIG)
    for name, weight in (('step', sc.step_weight), ('ramp', ramp)):
        f = lambda rr, mm: strain_score(sc.reference_load(cleaned, rr, mm, W, weight=weight))
        print(day, f'{name:5s}', *(f'{x:6.1f}' for x in (f(r, m), f(r - 5, m), f(r + 5, m), f(r, m - 10), f(r, m + 10))))
