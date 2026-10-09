from datetime import datetime, timedelta, timezone

import pytest

from strain import calculate_strain

START = datetime(2026, 10, 8, 7, tzinfo=timezone.utc)


def calculate(rest):
    return calculate_strain([(START, 160), (START + timedelta(minutes=4), 160)], [],
                            {'start': START, 'end': START + timedelta(minutes=4)}, 30, rest, 'm')


@pytest.mark.parametrize('bad', [187, 230, 1000, 29, 0, -1, float('inf'), 'bad', None])
def test_bad_rhr_falls_back_and_marks_calibration(bad):
    result = calculate([bad])
    assert result['params']['hr_rest'] == 60
    assert result['params']['hr_rest_source'] == 'default'
    assert result['params']['rhr_rejected_count'] == 1
    assert result['calibrating']
    assert result['load'] == calculate([])['load']


def test_numeric_provider_string_is_accepted():
    assert calculate(['56'])['load'] == calculate([56])['load']


def test_mixed_valid_and_invalid_reference_is_flagged():
    result = calculate([56, 1000])
    assert result['params']['hr_rest'] == 56
    assert result['calibrating']
