"""Statistical and reference checks from validation/fitbit_air, sized to run in seconds.

Noise levels match a real Fitbit Air week: ln HRV 0.12, resting HR 3 bpm,
breathing 1.2 /min, skin temperature 0.31 C (robust SDs).
"""
import math
import random
from datetime import date, datetime, timedelta, timezone
from statistics import pstdev

import pytest

from recovery_score import recovery_from_history
from strain import StrainConfig, calculate_strain

DAY = date(2026, 11, 13)


def person(rng, effects=None, days=70):
    effects = effects or {}
    out = {'hrv': [], 'rhr': [], 'respiratory_rate': [], 'skin_temperature': []}
    for i in range(days - 1, -1, -1):
        shift = effects.get(i, {})
        z = rng.gauss(0, 1)
        values = {'hrv': math.exp(math.log(35) + .12 * z + shift.get('hrv', 0)),
                  'rhr': 68 + 3 * (-.3 * z + math.sqrt(1 - .09) * rng.gauss(0, 1)) + shift.get('rhr', 0),
                  'respiratory_rate': 15.4 + rng.gauss(0, 1.2) + shift.get('rr', 0),
                  'skin_temperature': 33.8 + rng.gauss(0, .31) + shift.get('temp', 0)}
        for metric, value in values.items():
            out[metric].append({'date': (DAY - timedelta(days=i)).isoformat(), 'value': value,
                                'method': 'WITH_SLEEP' if metric == 'rhr' else None})
    return out


def scores(effects=None, n=400, seed=3):
    rng = random.Random(seed)
    return [recovery_from_history(person(rng, effects), DAY, 450, 450, age=30) for _ in range(n)]


def test_percent_is_calibrated_on_ordinary_days():
    results = scores()
    assert .85 < pstdev(r.z for r in results) < 1.15
    green = sum(r.percent >= 67 for r in results) / len(results)
    red = sum(r.percent < 34 for r in results) / len(results)
    assert .24 < green < .42 and .24 < red < .42


def test_illness_flag_rarely_fires_on_ordinary_days_and_catches_clear_fever():
    assert sum(r.illness_flag for r in scores()) / 400 < .05
    fever = scores({0: {'temp': 1., 'rr': 2.}}, seed=4)
    assert sum(r.illness_flag for r in fever) / 400 > .75


def test_one_clearly_bad_night_usually_reads_below_normal():
    bad = scores({0: {'hrv': -.12, 'rhr': 3.}}, seed=5)
    assert sum(r.zone == 'below_normal' for r in bad) / 400 > .6


BASE = datetime(2026, 10, 7, 6, tzinfo=timezone.utc)
WINDOW = {'start': BASE, 'end': BASE + timedelta(hours=14), 'source': 'local_midnight'}


def wavy_day(cadence_s=3):
    """Hours of everyday HR plus a 40-minute run, sampled like Fitbit Air (2-3 s)."""
    samples, t = [], 0
    while t < 14 * 3600:
        minute = t / 60
        bpm = 85 + 12 * math.sin(minute / 9) + (75 if 300 <= minute < 340 else 0)
        samples.append((BASE + timedelta(seconds=t), bpm))
        t += cadence_s
    return samples


RUN = {'start': BASE + timedelta(minutes=300), 'end': BASE + timedelta(minutes=340), 'activity_name': 'Run'}


def reference_load(samples, rest, hr_max, config=StrainConfig()):
    """Independent 1-second integral of Banister TRIMP with the workout-aware floor."""
    load = 0.
    for (t1, h1), (t2, h2) in zip(samples, samples[1:]):
        span = (t2 - t1).total_seconds()
        inside = RUN['start'] <= t1 + (t2 - t1) / 2 <= RUN['end']
        floor = config.min_hrr if inside else config.incidental_min_hrr
        for k in range(int(span)):
            hrr = max(0., min(1.1, (h1 + (h2 - h1) * (k + .5) / span - rest) / (hr_max - rest)))
            load += hrr * .64 * math.exp(1.92 * hrr) / 60 if hrr >= floor else 0.
    return load


def test_load_matches_an_independent_integral():
    result = calculate_strain(wavy_day(), [RUN], WINDOW, 30, [60] * 7)
    reference = reference_load(wavy_day(), 60, 208 - .7 * 30)
    assert result['load'] == pytest.approx(reference, rel=.01)


def test_strain_barely_depends_on_sampling_cadence():
    scores_by_cadence = [calculate_strain(wavy_day(c), [RUN], WINDOW, 30, [60] * 7)['strain'] for c in (1, 3, 15)]
    assert max(scores_by_cadence) - min(scores_by_cadence) < .3


def test_thin_night_hrv_is_set_aside_for_the_past_week():
    rng = random.Random(8)
    history = person(rng)
    full = recovery_from_history(history, DAY, 450, 450, age=30, today_hrv_windows=36)
    unknown = recovery_from_history(history, DAY, 450, 450, age=30)
    thin = recovery_from_history(history, DAY, 450, 450, age=30, today_hrv_windows=35)
    without_today = {**history, 'hrv': [p for p in history['hrv'] if p['date'] != DAY.isoformat()]}
    expected = recovery_from_history(without_today, DAY, 450, 450, age=30)
    assert full.components == unknown.components and not full.rejected_readings['hrv_today_low_coverage']
    assert thin.components['z_hrv'] == expected.components['z_hrv']
    assert thin.rejected_readings['hrv_today_low_coverage'] == 1 and thin.data_quality_flag


def test_night_window_count_reads_the_main_sleep_that_ended_today(tmp_path):
    from health_database import HealthDatabase
    from health_normalized_reads import night_hrv_windows
    db = HealthDatabase(tmp_path / 'health.sqlite3')
    user = db.ensure_account('provider-user')['user_id']
    wake = int(datetime(2026, 11, 13, 1, 30, tzinfo=timezone.utc).timestamp())  # 07:00 at +05:30
    assert night_hrv_windows(db, user, DAY) is None
    with db.connect() as conn:
        conn.execute('INSERT INTO sleep_sessions(user_id,provider_sleep_id,start_ts,end_ts,end_offset_min,is_main_sleep) VALUES (?,?,?,?,?,1)',
                     (user, 'night', wake - 8 * 3600, wake, 330))
        conn.executemany('INSERT INTO hrv_samples(user_id,ts,rmssd_ms) VALUES (?,?,?)',
                         [(user, wake - 8 * 3600 + i * 300, 30.) for i in range(20)] + [(user, wake + 3600, 30.)])
    assert night_hrv_windows(db, user, DAY) == 20
    assert night_hrv_windows(db, user, DAY - timedelta(days=1)) is None
