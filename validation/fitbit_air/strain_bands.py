"""Where does real-day load come from? Minutes and load by heart-rate-reserve band."""
import sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / 'backend'), str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
from datetime import timedelta
from strain import StrainConfig, calculate_strain, clean_samples, strain_score
from dataclasses import replace
import real_data, strain_check as sc

account = real_data.accounts_with_heart_rate()[0]
samples, sessions = real_data.heart_rate(account), real_data.exercises(account)
rhr = real_data.daily(account, 'daily-resting-heart-rate', 'dailyRestingHeartRate', 'beatsPerMinute')
bands = [(0, .2), (.2, .3), (.3, .4), (.4, .5), (.5, .7), (.7, 1.2)]
for day, window in sc.days(samples):
    inside = [p for p in samples if window['start'] <= p[0] < window['end']]
    rest = [rhr[d] for d in sorted(rhr) if day - timedelta(days=6) <= d <= day]
    base = sc.run(inside, sessions, window, rest)
    r, m = base['params']['hr_rest'], base['params']['hr_max']
    cleaned = clean_samples(inside, window, sc.CONFIG)
    minutes = [0.] * len(bands); load = [0.] * len(bands)
    awake = []
    for (t1, h1), (t2, h2) in zip(cleaned, cleaned[1:]):
        span = (t2 - t1).total_seconds()
        if not 0 < span <= 300: continue
        hrr = ((h1 + h2) / 2 - r) / (m - r)
        i = next(i for i, (lo, hi) in enumerate(bands) if hrr < hi or i == len(bands) - 1)
        minutes[i] += span / 60; load[i] += sc.banister(max(0, min(1.1, hrr))) * span / 60
        if 10 <= t1.hour < 20: awake.append((h1 + h2) / 2)
    awake.sort()
    alt = {f'min_hrr_{x}': round(sc.run(inside, sessions, window, rest, config=replace(sc.CONFIG, min_hrr=x))['strain'], 1) for x in (.3, .4)}
    print(day, f'rest {r} max {m} strain {base["strain"]:.1f} workout_load {base["workout_load"]:.0f} incidental {base["incidental_load"]:.0f}',
          'daytime(10-20h) HR median', awake[len(awake)//2] if awake else None, alt)
    print('   minutes by HRR band', [f'{lo}-{hi}: {mi:.0f}min/{lo_:.0f}load' for (lo, hi), mi, lo_ in zip(bands, minutes, load)])
