from datetime import date, timedelta

import pytest

from sleep_vitals import sleep_vitals

DAY = date(2026, 10, 14)


def point(offset, value, method='ASLEEP_TIME_WEIGHTED_V1'):
    return {'date': (DAY - timedelta(days=offset)).isoformat(), 'value': value, 'method': method}


def test_available_week_uses_mean_and_excludes_today():
    history = {'hrv': [point(i, value) for i, value in enumerate([200, 10, 20, 30, 40, 50, 100])],
               'rhr': [point(i, value) for i, value in enumerate([100, 50, 55, 60, 65, 70, 80])]}
    result = sleep_vitals(history, DAY)
    assert result['hrv_baseline'] == pytest.approx(250 / 6)
    assert result['rhr_baseline'] == pytest.approx(380 / 6)
    assert result['hrv_baseline_nights'] == result['rhr_baseline_nights'] == 6
    assert result['hrv'] == 200 and result['rhr'] == 100


def test_window_rolls_and_daily_duplicates_are_not_double_counted():
    history = {'hrv': [point(i, 40) for i in range(1, 62)] + [point(1, 100), point(0, 40)],
               'rhr': [point(0, 60), point(1, 60), point(61, 200)]}
    result = sleep_vitals(history, DAY)
    assert result['hrv_baseline_nights'] == 60
    assert result['hrv_baseline'] == 41
    assert result['rhr_baseline'] == 60
    next_day = sleep_vitals(history, DAY + timedelta(days=1))
    assert next_day['hrv_baseline_nights'] == 60


def test_no_history_has_no_default_baseline_and_single_prior_night_works():
    result = sleep_vitals({'hrv': [point(0, 40)], 'rhr': [point(0, 65)]}, DAY)
    assert result['hrv_baseline'] is None and result['rhr_baseline'] is None
    result = sleep_vitals({'hrv': [point(1, 40)], 'rhr': [point(1, 65)]}, DAY)
    assert result['hrv_baseline'] == 40 and result['rhr_baseline'] == 65


def test_invalid_values_and_different_rhr_methods_are_excluded():
    result = sleep_vitals({'hrv': [point(1, True), point(2, float('nan')), point(3, 40)],
                          'rhr': [point(0, 65), point(1, 50, 'WITH_SLEEP'), point(2, 60)]}, DAY)
    assert result['hrv_baseline_nights'] == result['rhr_baseline_nights'] == 1
    assert result['hrv_baseline'] == 40 and result['rhr_baseline'] == 60
