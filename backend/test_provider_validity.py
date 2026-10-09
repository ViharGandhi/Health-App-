from datetime import date
from dataclasses import replace

import pytest

from health_trends import valid_health_value
from sleep_stress import prepare_night, HrvWindow, HrSample


def test_daily_vo2_obeys_approved_provider_ceiling():
    assert valid_health_value('vo2_max', 100.)
    assert not valid_health_value('vo2_max', 100.01)
    assert not valid_health_value('vo2_max', 1e9)


@pytest.mark.parametrize('metric', ['hrv', 'deep_sleep_hrv', 'respiratory_rate', 'skin_temperature'])
def test_daily_fields_without_approved_ceilings_remain_unbounded(metric):
    assert valid_health_value(metric, 1e9)


def test_sample_hrv_obeys_its_own_ceiling_without_capping_daily_hrv():
    from validation.run_simulations import stress_night
    current = stress_night(date(2026, 10, 7), [(45., 60., 5)] * 72)
    night = current.night
    first = night.start_utc
    from datetime import timedelta
    windows = [HrvWindow(first, first + timedelta(minutes=5), 1e9)]
    samples = [HrSample(first + timedelta(seconds=i * 5), 60.) for i in range(61)]
    assert not prepare_night(night, windows, samples).windows
    windows[0] = replace(windows[0], rmssd_ms=200.)
    assert len(prepare_night(night, windows, samples).windows) == 1
