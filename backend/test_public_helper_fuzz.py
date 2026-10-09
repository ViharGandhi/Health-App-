from datetime import datetime
from math import isfinite
import pytest
from hypothesis import given, settings
from sleepscore import SleepCalculator, compute_baseline
from test_public_calculator_fuzz import scalar
from test_adapter_fuzz import finite_tree


RECIPES = {
    'latency': SleepCalculator.compute_sleep_latency_score,
    'interruption': SleepCalculator.compute_interruption_score,
    'age_target': SleepCalculator.optimal_deep_ratio,
    'baseline': lambda x: compute_baseline([(datetime(2026, 10, 7), x)] * 7),
}


@pytest.mark.parametrize('helper', RECIPES)
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(scalar)
def test_public_helpers_validate_malformed_scalars(helper, value):
    try:
        result = RECIPES[helper](value)
    except ValueError:
        return
    finite_tree(result)
    if result is not None:
        # This generic mean supports signed values; only component scores are nonnegative.
        if helper != 'baseline':
            assert result >= 0
        if helper in ('latency', 'interruption'):
            assert result <= 100
