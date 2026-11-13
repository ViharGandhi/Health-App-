"""Strain cross-check on real Fitbit Air days. Read-only; production code is called, never changed.

Run from the repo root:  .venv/Scripts/python -I validation/fitbit_air/strain_check.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT), str(Path(__file__).parent)]
from strain import StrainConfig, calculate_strain, clean_samples, strain_score  # noqa: E402
import real_data  # noqa: E402

AGE, SEX = 30, 'm'  # Assumed profile: the cached account's age is not stored.
CONFIG = StrainConfig()
OUT = Path(__file__).with_name('strain_results.json')


def banister(hrr: float, sex: str = SEX) -> float:
    a, b = (.64, 1.92) if sex == 'm' else (.86, 1.67)
    return hrr * a * math.exp(b * hrr) if hrr >= CONFIG.min_hrr else 0.


def step_weight(hrr, in_workout):
    """Production rule: 20% HRR floor in logged workouts, 40% outside."""
    return 1. if hrr >= (CONFIG.min_hrr if in_workout else CONFIG.incidental_min_hrr) else 0.


def reference_load(samples, rest, hr_max, sessions=(), max_gap=CONFIG.max_gap_s, weight=step_weight):
    """Independent integral on a 1-second grid: linear HR between samples, gaps above max_gap skipped."""
    load = 0.
    for (t1, h1), (t2, h2) in zip(samples, samples[1:]):
        span = (t2 - t1).total_seconds()
        if not 0 < span <= max_gap:
            continue
        in_workout = any(s['start'] <= t1 + (t2 - t1) / 2 <= s['end'] for s in sessions)
        steps = max(1, round(span))
        for k in range(steps):
            hr = h1 + (h2 - h1) * (k + .5) / steps
            hrr = max(0., min(1.1, (hr - rest) / (hr_max - rest)))
            load += hrr * .64 * math.exp(1.92 * hrr) * weight(hrr, in_workout) * span / steps / 60
    return load


def days(samples):
    tz = samples[0][0].tzinfo
    first = samples[0][0].date() + timedelta(days=1)
    last = samples[-1][0].date() - timedelta(days=1)
    day = first
    while day <= last:
        start = datetime.combine(day, time.min, tzinfo=tz)
        yield day, {'start': start, 'end': start + timedelta(days=1), 'source': 'local_midnight'}
        day += timedelta(days=1)


def run(samples, sessions, window, rest, **changes):
    args = dict(age=AGE, resting_hrs=rest, sex=SEX, config=CONFIG)
    args.update(changes)
    return calculate_strain(samples, sessions, window, **args)


def downsample(samples, every_s):
    kept, last = [], None
    for stamp, bpm in samples:
        if last is None or (stamp - last).total_seconds() >= every_s:
            kept.append((stamp, bpm))
            last = stamp
    return kept


def drop_blocks(samples, fraction, rng, block_min=5):
    if not samples:
        return samples
    start, end = samples[0][0], samples[-1][0]
    total = (end - start).total_seconds() / 60
    blocks = set()
    while len(blocks) * block_min < fraction * total:
        blocks.add(rng.randrange(int(total // block_min)))
    return [(s, b) for s, b in samples if int((s - start).total_seconds() / 60 // block_min) not in blocks]


def spikes(samples, rate, rng, size=60):
    return [(s, b + size if rng.random() < rate else b) for s, b in samples]


def cadence_lock(samples, sessions, rng, bpm=150, seconds=30, per_hour=4):
    """Optical HR locking onto step cadence: short runs of a plausible but wrong value outside workouts."""
    out = list(samples)
    if not out:
        return out
    hours = (out[-1][0] - out[0][0]).total_seconds() / 3600
    for _ in range(int(hours * per_hour)):
        at = out[0][0] + timedelta(seconds=rng.uniform(0, hours * 3600))
        if any(s['start'] <= at <= s['end'] for s in sessions):
            continue
        out = [(s, bpm if at <= s <= at + timedelta(seconds=seconds) else b) for s, b in out]
    return out


def main():
    account = real_data.accounts_with_heart_rate()[0]
    samples = real_data.heart_rate(account)
    sessions = real_data.exercises(account)
    rhr = real_data.daily(account, 'daily-resting-heart-rate', 'dailyRestingHeartRate', 'beatsPerMinute')
    gaps = sorted((b[0] - a[0]).total_seconds() for a, b in zip(samples, samples[1:]))
    report = {'profile': {'age': AGE, 'sex': SEX, 'assumed': True}, 'samples': len(samples),
              'cadence_s': {'median': median(gaps), 'p90': gaps[int(.9 * len(gaps))], 'p99': gaps[int(.99 * len(gaps))],
                            'gaps_over_300s': sum(g > 300 for g in gaps)},
              'sessions': len(sessions), 'days': []}
    rng = random.Random(7)
    for day, window in days(samples):
        inside = [p for p in samples if window['start'] <= p[0] < window['end']]
        rest = [rhr[d] for d in sorted(rhr) if day - timedelta(days=6) <= d <= day]
        base = run(inside, sessions, window, rest)
        hr_rest, hr_max = base['params']['hr_rest'], base['params']['hr_max']
        cleaned = clean_samples(inside, window, CONFIG)
        ref = reference_load(cleaned, hr_rest, hr_max, sessions)
        row = {'day': day.isoformat(), 'samples': len(inside), 'coverage': round(base['coverage'], 3),
               'hr_rest': hr_rest, 'hr_max': hr_max, 'strain': round(base['strain'], 2), 'load': round(base['load'], 2),
               'reference_load': round(ref, 2), 'reference_strain': round(strain_score(ref, CONFIG), 2),
               'removed_by_spike_filter': len(inside) - len(cleaned),
               'workouts': [(w['name'], round(w['strain'], 1)) for w in base['workouts']]}
        for every in (5, 15, 60):
            row[f'strain_every_{every}s'] = round(run(downsample(inside, every), sessions, window, rest)['strain'], 2)
        for fraction in (.1, .3, .5):
            r = run(drop_blocks(inside, fraction, rng), sessions, window, rest)
            row[f'missing_{int(fraction * 100)}pct'] = {'strain': round(r['strain'], 2), 'coverage': round(r['coverage'], 2), 'low_coverage': r['low_coverage']}
        row['spikes_1pct'] = round(run(spikes(inside, .01, rng), sessions, window, rest)['strain'], 2)
        row['spikes_5pct'] = round(run(spikes(inside, .05, rng), sessions, window, rest)['strain'], 2)
        row['cadence_lock'] = round(run(cadence_lock(inside, sessions, rng), sessions, window, rest)['strain'], 2)
        for delta in (-10, -5, 5, 10):
            row[f'hr_max_{delta:+d}'] = round(run(inside, sessions, window, rest, hr_max=hr_max + delta)['strain'], 2)
        for delta in (-5, 5):
            row[f'hr_rest_{delta:+d}'] = round(run(inside, sessions, window, [hr_rest + delta])['strain'], 2)
        for error in (-.05, .05):  # wrist PPG bias during exercise (Bent et al. 2020 report ~5-10% MAPE)
            biased = [(s, b * (1 + error) if any(w['start'] <= s <= w['end'] for w in sessions) else b) for s, b in inside]
            row[f'workout_hr_bias_{int(error * 100):+d}pct'] = round(run(biased, sessions, window, rest)['strain'], 2)
        report['days'].append(row)
        print(json.dumps(row))
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: v for k, v in report.items() if k != 'days'}))


if __name__ == '__main__':
    main()
