from copy import deepcopy
from datetime import date

from mock_sleep_stage_ranges import mock_stage_points
from sleep_analytics import build_sleep_analytics, sleep_observations


def test_build_does_not_mutate_callers_observations():
    day = date(2026, 10, 3)
    inputs = sleep_observations(mock_stage_points(day, 4), day)
    before = deepcopy(inputs)
    first = build_sleep_analytics(inputs, day, 'W', False)
    assert inputs == before
    assert first == build_sleep_analytics(inputs, day, 'W', False)
