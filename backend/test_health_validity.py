from datetime import date, timedelta

import pytest

from health_trends import METRICS, build_health_response

DAY = date(2026, 10, 8)


@pytest.mark.parametrize('metric', METRICS)
@pytest.mark.parametrize('invalid', [0, -1, float('nan'), float('inf')])
def test_invalid_daily_value_is_missing_everywhere(metric, invalid):
    points = [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': invalid} for i in range(8)]
    result = build_health_response({metric: points}, [], DAY, DAY, 'W', False)
    assert result.metrics[metric][0].value is None
    assert result.metrics[metric][0].baseline is None
    assert result.averages[metric] is None


@pytest.mark.parametrize('metric,invalid', [('rhr', 1000), ('nrem_hr', 1000), ('rhr', 29), ('spo2', 101)])
def test_existing_or_physical_bounds(metric, invalid):
    result = build_health_response({metric: [{'date': DAY.isoformat(), 'value': invalid}]}, [], DAY, DAY, 'W', False)
    assert result.metrics[metric][0].value is None


@pytest.mark.parametrize('metric', ['hrv', 'deep_sleep_hrv', 'respiratory_rate', 'skin_temperature'])
def test_new_upper_limits_are_not_invented(metric):
    result = build_health_response({metric: [{'date': DAY.isoformat(), 'value': 1e9}]}, [], DAY, DAY, 'W', False)
    # User approved finite/positive gates only for these metrics; flag in audit report.
    assert result.metrics[metric][0].value == 1e9
