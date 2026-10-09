"""Deterministic malformed-payload probes; pure validation ValueError is intentional."""
from dataclasses import asdict, is_dataclass
from datetime import date
import math

from hypothesis import given, settings, strategies as st
import pytest

from google_health_client import _local_datetime, _google_date, _valid_sleep_summary
from health_read_store import point_clock
from sleep_stage_ranges import adapt_google_sleep as stage_sleep, stats_from_dict
from sleep_stress import adapt_google_sleep as stress_sleep, adapt_google_hr, adapt_google_hrv
from sleep_heart_rate import select_sleep
from strain_service import sleep_windows


scalar = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), st.text(max_size=40))
payload = st.recursive(scalar, lambda child: st.one_of(st.lists(child, max_size=4),
    st.dictionaries(st.sampled_from(['sleep', 'interval', 'startTime', 'endTime', 'sampleTime',
        'physicalTime', 'heartRate', 'heartRateVariability', 'year', 'month', 'day', 'stages', 'metadata']),
        child, max_size=5)), max_leaves=15)


def finite_tree(value):
    if is_dataclass(value):
        finite_tree(asdict(value))
    elif hasattr(value, 'model_dump'):
        finite_tree(value.model_dump())
    elif isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            finite_tree(item)


RECIPES = {
    'local_datetime': lambda p: _local_datetime(p, '0s', preserve_offset=True),
    'google_date': _google_date,
    'summary_gate': _valid_sleep_summary,
    'stage_sleep': stage_sleep,
    'stress_sleep': stress_sleep,
    'stress_hr': adapt_google_hr,
    'stress_hrv': lambda p: adapt_google_hrv([p], 'start'),
    'stats_from_dict': stats_from_dict,
    'main_sleep_selector': lambda p: select_sleep([p], date(2026, 10, 7)),
    'strain_sleep_windows': lambda p: sleep_windows([p]),
    'store_point_clock': lambda p: point_clock(p, 'sleep.interval.civil_end_time'),
}


@pytest.mark.parametrize('adapter', RECIPES)
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_adapters_return_valid_data_or_explicit_validation_error(adapter, value):
    try:
        result = RECIPES[adapter](value)
    except ValueError:
        return
    finite_tree(result)
