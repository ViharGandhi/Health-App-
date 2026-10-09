from copy import deepcopy
from datetime import date

from mock_sleep_stage_ranges import mock_stage_points
from sleep_stage_ranges import adapt_google_sleep, stage_stats


def test_invalid_partition_logs_reason_without_raw_identifier(caplog):
    point = deepcopy(mock_stage_points(date(2026, 10, 3), 1)[0])
    point['name'] = 'private-device-session-identifier'
    point['sleep']['stages'][0]['type'] = 'INVALID'
    result, reason = stage_stats(adapt_google_sleep(point))
    assert result is None and reason == 'invalid_stage_partition'
    assert caplog.records
    assert point['name'] not in caplog.text
