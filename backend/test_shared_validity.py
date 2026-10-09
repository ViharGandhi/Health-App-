"""Existing HR bounds must apply before references/counts in every estimator."""
from datetime import date, timedelta
import math

from hypothesis import given, settings, strategies as st
import pytest

from health_trends import valid_health_value
from recovery_score import calculate_recovery, recovery_from_history
from recovery import RecoveryCalculator
from sleepscore import SleepCalculator
from strain import calculate_strain

DAY = date(2026, 10, 7)


@pytest.mark.parametrize('rhr', [29., 231., 1000., float('inf'), float('nan'), '55'])
def test_rejected_rhr_does_not_enter_recovery_or_legacy_components(rhr):
    estimate = calculate_recovery([40.] * 60, [40.] * 7, 40., [55.] * 60, rhr, 450., 450.)
    assert estimate.components['z_rhr'] is None
    assert estimate.confidence == 'medium'
    assert estimate.rejected_readings['rhr_today'] == 1
    assert RecoveryCalculator._rhr_component(rhr, 55.) == 50.
    assert SleepCalculator.compute_sleeping_hr_score(rhr, 55.) == 50.


def test_invalid_reference_rhr_is_counted_and_cannot_create_high_confidence():
    estimate = calculate_recovery([40.] * 60, [40.] * 7, 40., [1000.] * 60, 55., 450., 450.)
    assert estimate.rhr_baseline_days == 0
    assert estimate.rejected_readings['rhr_baseline'] == 60
    assert estimate.components['z_rhr'] is None
    assert estimate.confidence == 'medium'


def test_known_age_applies_hrmax_in_connected_reference():
    history = {key: [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': value,
                     'method': 'WITH_SLEEP'} for i in range(68)] for key, value in [('hrv', 40.), ('rhr', 180.)]}
    result = recovery_from_history(history, DAY, 450., 450., age=70)
    assert result.components['z_rhr'] is None
    assert result.rhr_baseline_days == 0


@settings(max_examples=250, derandomize=True)
@given(st.floats(allow_nan=True, allow_infinity=True))
def test_rhr_acceptance_agrees_without_age(value):
    accepted = math.isfinite(value) and 30 <= value <= 230
    assert valid_health_value('rhr', value) == accepted
    estimate = calculate_recovery([40.] * 60, [40.] * 7, 40., [55.] * 60, value)
    assert (estimate.components['z_rhr'] is not None) == accepted
    stamp = __import__('datetime').datetime(2026, 10, 7, tzinfo=__import__('datetime').timezone.utc)
    strain = calculate_strain([], [], {'start': stamp, 'end': stamp}, None, [value])
    assert (strain['params']['hr_rest_source'] == 'recovery') == accepted


@settings(max_examples=250, derandomize=True)
@given(st.one_of(st.none(), st.booleans(), st.text(max_size=12), st.floats(allow_nan=True, allow_infinity=True)))
def test_hrv_acceptance_agrees_across_layers(value):
    accepted = type(value) in (float, int) and math.isfinite(value) and value > 0
    assert valid_health_value('hrv', value) == accepted
    result = calculate_recovery([40.] * 60, [40.] * 7, value)
    assert result.rejected_readings['hrv_today'] == int(value is not None and not accepted)
    assert math.isfinite(RecoveryCalculator._hrv_component(value, 40., None))
    assert math.isfinite(SleepCalculator.compute_sleeping_hrv_score(value, 40.))
