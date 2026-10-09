"""Properties on documented domains; arbitrary raw HR is subject to spike filtering."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import math

import pytest
from hypothesis import given, settings, strategies as st

from strain import calculate_strain, strain_score
from sleepscore import SleepCalculator, SleepData
from sleep_efficiency import SleepEfficiencyCalculator
from sleep_need import SleepNeedNight, calculate_sleep_need
from recovery_score import calculate_recovery, recovery_from_history
from sleep_stage_ranges import SleepNight, StageSegment, stage_stats
from test_recovery_score import DAY, reference_history


settings.register_profile('analytics_audit', max_examples=200, derandomize=True, deadline=None)
settings.load_profile('analytics_audit')
finite = lambda lo, hi: st.floats(lo, hi, allow_nan=False, allow_infinity=False)
BASE = datetime(2026, 10, 7, 7, tzinfo=timezone.utc)


def cardio(hr, minutes, age, rhr):
    samples = [(BASE + timedelta(minutes=i), hr) for i in range(minutes + 1)]
    return calculate_strain(samples, [], {'start': BASE, 'end': samples[-1][0]}, age, [rhr], 'm')


@given(finite(30, 230), finite(30, 230), st.integers(1, 240), st.integers(18, 100), finite(40, 85))
def test_constant_hr_strain_monotonic_and_bounded(a, b, minutes, age, rhr):
    low, high = sorted((a, b))
    left, right = cardio(low, minutes, age, rhr), cardio(high, minutes, age, rhr)
    assert 0 <= left['strain'] <= right['strain'] < 21


@given(finite(30, 230), st.integers(1, 120), st.integers(1, 120))
def test_strain_monotonic_in_observed_duration(hr, a, b):
    small, large = sorted((a, b))
    assert cardio(hr, small, 30, 56)['strain'] <= cardio(hr, large, 30, 56)['strain']


@given(finite(0, 1e8))
def test_strain_mapping_never_returns_twenty_one(load):
    assert math.isfinite(strain_score(load)) and 0 <= strain_score(load) < 21


@given(finite(.01, 1.1), finite(.01, 1.1))
def test_sleep_duration_monotonic_until_oversleep_penalty(a, b):
    a, b = sorted((a, b))
    assert 0 <= SleepCalculator.compute_duration_score(a * 7.5, 7.5) <= SleepCalculator.compute_duration_score(b * 7.5, 7.5) <= 100


@given(finite(180, 660), finite(.01, 1.5), st.integers(18, 100))
def test_sleep_component_directions_and_total_bounds(need, ratio, age):
    asleep = need * ratio * 60
    sleep = SleepData(asleep, asleep * .2, asleep * .2, asleep * .6, 1200,
                      asleep + 1200, None, None, 2)
    calc = lambda s: SleepCalculator.calculate_score(s, need / 60, 40, 60, 75, 40, 60, age)
    assert 0 <= calc(sleep) <= 100
    assert calc(replace(sleep, deep_sleep_duration=sleep.deep_sleep_duration + 600)) >= calc(sleep)
    assert calc(replace(sleep, rem_sleep_duration=sleep.rem_sleep_duration + 600)) >= calc(sleep)
    assert calc(replace(sleep, core_sleep_duration=sleep.core_sleep_duration + 600)) >= calc(sleep)
    assert calc(replace(sleep, in_bed_duration=sleep.in_bed_duration + 600)) <= calc(sleep)
    assert calc(replace(sleep, awake_duration=sleep.awake_duration + 600)) <= calc(sleep)
    assert calc(replace(sleep, interruption_count=3)) <= calc(sleep)
    assert SleepCalculator.compute_sleeping_hrv_score(41, 40) >= SleepCalculator.compute_sleeping_hrv_score(40, 40)
    assert SleepCalculator.compute_sleeping_hr_score(61, 60) <= SleepCalculator.compute_sleeping_hr_score(60, 60)
    assert SleepCalculator.compute_hr_dip_score(61, 75) <= SleepCalculator.compute_hr_dip_score(60, 75)


@given(finite(.00001, 1e6), finite(.00001, 1e6))
def test_recovery_percent_monotonic_in_hrv_signal(a, b):
    a, b = sorted((a, b))
    calc = lambda value: calculate_recovery([40.] * 60, [40.] * 7, value,
                                           [55.] * 60, 55., 450., 450.)
    low, high = calc(a), calc(b)
    assert 0 <= low.percent <= high.percent <= 100
    assert low.components['z_hrv'] <= high.components['z_hrv']


@given(finite(0, 100), finite(0, 1000), finite(0, 900))
def test_sleep_need_limits(strain, actual, nap):
    result = calculate_sleep_need(strain, [SleepNeedNight(actual, strain)] * 7, nap)
    assert 360 <= result.total_need_min <= 660
    assert 0 <= result.sleep_debt_min <= 240


@given(st.lists(st.integers(1, 180), min_size=4, max_size=4))
def test_stage_partition_and_efficiency_limits(amounts):
    amounts[1] += 180  # Enough asleep time for a main sleep.
    cursor, segments = BASE, []
    for name, minutes in zip(('awake', 'light', 'deep', 'rem'), amounts):
        end = cursor + timedelta(minutes=minutes)
        segments.append(StageSegment(cursor, end, name))
        cursor = end
    night = SleepNight('synthetic', BASE.date(), BASE, cursor, 'STAGES', 'SUCCEEDED', True, tuple(segments))
    stats, status = stage_stats(night)
    assert status == 'ok'
    assert sum(stats.pct[k] for k in ('awake', 'light', 'deep', 'rem')) == pytest.approx(100)
    shuffled, status = stage_stats(replace(night, segments=tuple(reversed(segments))))
    assert shuffled == stats
    efficiency = SleepEfficiencyCalculator.calculate_single_night(sum(amounts[1:]) * 60, sum(amounts) * 60)
    assert 0 < efficiency <= 100


@given(st.permutations(range(12)))
def test_unique_hr_sample_permutations_do_not_change_strain(order):
    samples = [(BASE + timedelta(minutes=i), 135. + i) for i in range(12)]
    window = {'start': BASE, 'end': samples[-1][0]}
    calc = lambda values: calculate_strain(values, [], window, 30, [56.], 'm')
    assert calc([samples[i] for i in order]) == calc(samples)


@given(st.permutations(range(6)))
def test_daily_join_permutations_with_unique_dates(order):
    history = reference_history()
    history['hrv'][-6:] = [history['hrv'][-6:][i] for i in order]
    assert recovery_from_history(history, DAY, 450, 450) == recovery_from_history(reference_history(), DAY, 450, 450)


@pytest.mark.parametrize('minutes,inbed', [(0, 0), (1, 0), (100, 99), (math.nan, 100), (100, math.inf)])
def test_efficiency_invalid_denominators_are_withheld(minutes, inbed):
    assert SleepEfficiencyCalculator.calculate_single_night(minutes, inbed) is None
