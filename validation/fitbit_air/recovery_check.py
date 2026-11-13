"""Recovery Monte Carlo with Fitbit-Air-like nightly noise. Production code is called, never changed.

Noise levels come from a real Fitbit Air week in the local cache (robust SDs):
ln HRV 0.12, resting HR 3.0 bpm, breathing rate 1.2 /min, skin temperature 0.31 C.
Run from the repo root:  .venv/Scripts/python -I validation/fitbit_air/recovery_check.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from recovery_score import recovery_from_history  # noqa: E402

DAY = date(2026, 11, 13)
OUT = Path(__file__).with_name('recovery_results.json')
NOISE = {'hrv': .12, 'rhr': 3.0, 'rr': 1.2, 'temp': .31}
CENTER = {'hrv': math.log(35), 'rhr': 68., 'rr': 15.4, 'temp': 33.8}
PHI, RHO = .3, -.3  # day-to-day carry-over; ln HRV vs resting HR correlation (real week: -0.27)
N = 2000


def person(rng, days=70, noise=NOISE, effects=None, missing=0.):
    """Daily values oldest -> newest ending on DAY. effects: {offset_from_DAY: {metric: shift}}."""
    effects = effects or {}
    out = {'hrv': [], 'rhr': [], 'respiratory_rate': [], 'skin_temperature': []}
    e_h = e_r = 0.
    for i in range(days - 1, -1, -1):
        when = DAY - timedelta(days=i)
        z1, z2 = rng.gauss(0, 1), rng.gauss(0, 1)
        e_h = PHI * e_h + math.sqrt(1 - PHI ** 2) * z1
        e_r = PHI * e_r + math.sqrt(1 - PHI ** 2) * (RHO * z1 + math.sqrt(1 - RHO ** 2) * z2)
        shift = effects.get(i, {})
        if i and rng.random() < missing:
            continue
        values = {'hrv': math.exp(CENTER['hrv'] + noise['hrv'] * e_h + shift.get('hrv', 0)),
                  'rhr': CENTER['rhr'] + noise['rhr'] * e_r + shift.get('rhr', 0),
                  'respiratory_rate': CENTER['rr'] + rng.gauss(0, noise['rr']) + shift.get('rr', 0),
                  'skin_temperature': CENTER['temp'] + rng.gauss(0, noise['temp']) + shift.get('temp', 0)}
        for metric, value in values.items():
            out[metric].append({'date': when.isoformat(), 'value': value, 'method': 'WITH_SLEEP' if metric == 'rhr' else None})
    return out


def score(history, sleep=(450, 450)):
    return recovery_from_history(history, DAY, *sleep, age=30)


def summary(results):
    ok = [r for r in results if r.percent is not None]
    percents = [r.percent for r in ok]
    return {'n': len(results), 'scored': len(ok),
            'mean_percent': round(mean(percents), 1) if ok else None,
            'sd_percent': round(pstdev(percents), 1) if ok else None,
            'sd_z': round(pstdev([r.z for r in ok]), 3) if ok else None,
            'green_67_plus': round(sum(p >= 67 for p in percents) / max(1, len(ok)), 3),
            'red_below_34': round(sum(p < 34 for p in percents) / max(1, len(ok)), 3),
            'below_normal_zone': round(sum(r.zone == 'below_normal' for r in ok) / max(1, len(ok)), 3),
            'above_normal_zone': round(sum(r.zone == 'above_normal' for r in ok) / max(1, len(ok)), 3),
            'illness_flag': round(sum(r.illness_flag for r in results) / len(results), 3)}


def experiment(name, rng, **kwargs):
    sleep = kwargs.pop('sleep', (450, 450))
    days = kwargs.pop('days', 70)
    result = summary([score(person(rng, days=days, **kwargs), sleep) for _ in range(N)])
    print(name, json.dumps(result))
    return result


def main():
    rng = random.Random(2026)
    s_h, s_r = NOISE['hrv'], NOISE['rhr']
    report = {'noise': NOISE, 'n_per_experiment': N, 'experiments': {}}
    ex = report['experiments']
    # 1. Calibration with nothing going on: a calibrated percent is uniform (33% green, 34% red).
    ex['null_60_day_reference'] = experiment('null', rng)
    ex['null_14_day_reference'] = experiment('null_14d', rng, days=8 + 14)
    ex['null_28_day_reference'] = experiment('null_28d', rng, days=8 + 28)
    ex['null_low_noise'] = experiment('null_low_noise', rng, noise={**NOISE, 'hrv': .07, 'rhr': 1.5})
    ex['null_20pct_missing'] = experiment('null_missing', rng, missing=.2)
    # 2. One bad night (alcohol, late meal): HRV and RHR worse by d typical night-to-night SDs.
    for d in (.5, 1, 2):
        ex[f'one_bad_night_{d}sd'] = experiment(f'bad_night_{d}', rng, effects={0: {'hrv': -d * s_h, 'rhr': d * s_r}})
        ex[f'one_good_night_{d}sd'] = experiment(f'good_night_{d}', rng, effects={0: {'hrv': d * s_h, 'rhr': -d * s_r}})
    # 3. Accumulated fatigue: 4 nights in a row at -1 SD.
    ex['four_bad_nights_1sd'] = experiment('fatigue_4n', rng, effects={i: {'hrv': -s_h, 'rhr': s_r} for i in range(4)})
    # 4. Illness signal (temperature and breathing rate up; HRV down, RHR up).
    ex['fever_mild'] = experiment('fever_mild', rng, effects={0: {'temp': .5, 'rr': 1.0, 'hrv': -s_h, 'rhr': 2 * s_r}})
    ex['fever_clear'] = experiment('fever_clear', rng, effects={0: {'temp': 1.0, 'rr': 2.0, 'hrv': -2 * s_h, 'rhr': 3 * s_r}})
    # 5. HRV sensor artefact: one night reads 50% high, everything else normal.
    ex['hrv_artefact_plus50pct'] = experiment('hrv_artefact', rng, effects={0: {'hrv': math.log(1.5)}})
    # 6. Short sleep against need (sleep penalty).
    ex['null_short_sleep_5h_of_7_5h'] = experiment('short_sleep', rng, sleep=(300, 450))
    OUT.write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
