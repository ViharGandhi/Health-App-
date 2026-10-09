from datetime import date
import pytest
from hypothesis import given, settings
from sleep_analytics import sleep_observations
from sleep_heart_rate import build_sleep_heart_rate
from test_adapter_fuzz import payload, finite_tree


@pytest.mark.parametrize('adapter', ['sleep_observations', 'sleep_hr_chart'])
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_additional_sleep_adapters_validate_payload(adapter, value):
    try:
        result = sleep_observations([value], date(2026, 10, 7)) if adapter == 'sleep_observations' else build_sleep_heart_rate(value, [], False)
    except ValueError:
        return
    finite_tree(result)
