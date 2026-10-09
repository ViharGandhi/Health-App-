from datetime import date

import pytest

from sleep_trends import build_sleep_trend
from test_sleep_trends import sleep_record


@pytest.mark.parametrize('field', ['time_asleep_minutes', 'time_in_bed_minutes'])
@pytest.mark.parametrize('metric', ['efficiency', 'consistency'])
def test_missing_duration_is_unusable_instead_of_raising(field, metric):
    day = date(2026, 10, 7)
    record = sleep_record(day)
    record[field] = None
    result = build_sleep_trend([record], day, day, 'W', metric, False)
    assert result.average_value is None
    assert result.scored_days == result.recorded_nights == 0
