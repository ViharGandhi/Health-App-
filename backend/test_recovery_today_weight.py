from datetime import timedelta
import math

import pytest

from recovery_score import recovery_from_history
from test_recovery_score import DAY, reference_history


@pytest.mark.parametrize('ratio', [1.2, .8, 2.])
def test_today_has_exactly_thirty_percent_weight(ratio):
    history = reference_history()
    history['hrv'][-7]['value'] = 40 * ratio  # Most recent/current date is first in the recent block.
    result = recovery_from_history(history, DAY, 450, 450)
    assert result.components['z_hrv'] == pytest.approx(.3 * math.log(ratio) / .05)


def test_six_prior_nights_still_qualify_for_high_confidence():
    result = recovery_from_history(reference_history(), DAY, 450, 450)
    assert result.recent_nights == 6
    assert result.confidence == 'high'


def test_today_cannot_fill_the_four_prior_night_minimum():
    result = recovery_from_history(reference_history(recent=4), DAY, 450, 450)
    assert result.status == 'building_reference'


def test_seventh_prior_date_is_included_without_entering_baseline():
    history = reference_history()
    history['hrv'].append({'date': (DAY - timedelta(days=7)).isoformat(), 'value': 48.})
    result = recovery_from_history(history, DAY, 450, 450)
    assert result.baseline_days == 60
    assert result.recent_nights == 7
    assert result.components['z_hrv'] == pytest.approx(.7 * math.log(1.2) / (7 * .05))
