import math

import pytest

from sleepscore import SleepCalculator, SleepData


def duration_component(ratio):
    seconds = ratio * 7.5 * 3600
    data = SleepData(seconds, 0, 0, 0, 0, seconds / .95, None, None, 0)
    # All other components are fixed: 10 efficiency + 14 missing-HR + 15 restfulness.
    return (SleepCalculator.calculate_score(data, 7.5) - 39) / .27


@pytest.mark.parametrize('ratio', [.6, .75, .9, 1.])
def test_approved_rescaling_reaches_full_score(ratio):
    raw = lambda r: 100 / (1 + math.exp(-8 * (r - .75)))
    assert duration_component(ratio) == pytest.approx(raw(ratio) / raw(1) * 100)


@pytest.mark.parametrize('boundary', [1., 1.1])
def test_duration_is_continuous_at_branch_boundaries(boundary):
    assert abs(duration_component(boundary + 1e-9) - duration_component(boundary - 1e-9)) < 1e-5


def test_oversleep_penalty_is_unchanged():
    assert duration_component(1.3) == pytest.approx(85)
