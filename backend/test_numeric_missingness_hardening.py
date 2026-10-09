from dataclasses import replace
import math

import pytest

from recovery import RecoveryCalculator, RecoveryInput
from sleepscore import SleepCalculator, SleepData
from sleep_stage_ranges import StageRangeConfig
from validity import positive


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_nonfinite_sleep_duration_is_rejected(value):
    with pytest.raises(ValueError):
        SleepCalculator.compute_duration_score(value, 7.5)


@pytest.mark.parametrize('field', ['total_duration', 'deep_sleep_duration', 'rem_sleep_duration',
    'core_sleep_duration', 'awake_duration', 'in_bed_duration', 'nap_duration_seconds'])
def test_nonfinite_sleep_data_cannot_turn_into_plausible_score(field):
    with pytest.raises(ValueError):
        SleepCalculator.calculate_score(replace(SleepData.empty(), **{field: math.nan}), 7.5)


@pytest.mark.parametrize('field', ['sleep_score', 'yesterday_strain', 'acr', 'recovery_adjustment'])
def test_legacy_required_numeric_inputs_reject_nonfinite(field):
    with pytest.raises(ValueError):
        RecoveryCalculator.calculate(RecoveryInput(**{field: math.nan}))


@pytest.mark.parametrize('field', ['spread_scale', 'spread_floor_pct', 'min_sleep_hours'])
def test_stage_configuration_rejects_nonfinite(field):
    with pytest.raises(ValueError):
        StageRangeConfig(**{field: math.nan})


def test_unrepresentable_integer_is_rejected_without_overflow():
    assert positive(10 ** 400) is False
