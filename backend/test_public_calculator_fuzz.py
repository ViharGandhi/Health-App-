"""Malformed scalar fuzzing supplements the existing valid-domain invariants."""
import pytest
from hypothesis import given, settings, strategies as st

from sleepscore import SleepCalculator, SleepData
from recovery import RecoveryCalculator, RecoveryInput
from sleep_efficiency import SleepEfficiencyCalculator
from recovery_score import calculate_recovery
from sleep_need import calculate_sleep_need
from strain import strain_score
from test_adapter_fuzz import finite_tree


SLEEP = SleepData(27000., 5400., 5400., 16200., 1200., 28200., None, None, 1)
scalar = st.one_of(st.none(), st.booleans(), st.floats(), st.integers(), st.text(max_size=20))
RECIPES = {
    'strain_mapping': strain_score,
    'sleep_duration': lambda x: SleepCalculator.compute_duration_score(x, 7.5),
    'sleep_score': lambda x: SleepCalculator.calculate_score(SLEEP, x, 40, 60, 75, 40, 60, 30),
    'sleep_hrv': lambda x: SleepCalculator.compute_sleeping_hrv_score(x, 40),
    'sleep_hr': lambda x: SleepCalculator.compute_sleeping_hr_score(x, 60),
    'sleep_hr_dip': lambda x: SleepCalculator.compute_hr_dip_score(x, 75),
    'sleep_need_legacy': lambda x: SleepCalculator.calculate_sleep_need(yesterday_strain=x),
    'sleep_debt_legacy': lambda x: SleepCalculator.compute_sleep_debt([(7.5, x)]),
    'efficiency': lambda x: SleepEfficiencyCalculator.calculate_single_night(x, 28200),
    'recovery_legacy': lambda x: RecoveryCalculator.calculate(RecoveryInput(sleep_score=x)),
    'recovery_connected': lambda x: calculate_recovery([40.] * 60, [40.] * 7, x),
    'sleep_need_connected': lambda x: calculate_sleep_need(x, []),
}


@pytest.mark.parametrize('calculator', RECIPES)
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(scalar)
def test_public_scalar_calculators_validate_or_return_finite(calculator, value):
    try:
        result = RECIPES[calculator](value)
    except ValueError:
        return
    finite_tree(result)
    if calculator in ('sleep_duration', 'sleep_score', 'sleep_hrv', 'sleep_hr', 'sleep_hr_dip', 'efficiency') and result is not None:
        assert 0 <= result <= 100


@pytest.mark.parametrize('value', [None, True, '300', float('nan'), float('inf'), 10**1000])
def test_efficiency_wrong_types_are_withheld(value):
    assert SleepEfficiencyCalculator.calculate_single_night(value, 28200) is None


def test_custom_duration_sigmoid_is_stable():
    assert 0 <= SleepCalculator.compute_duration_score(1., 7.5, 1000., .75) <= 100

