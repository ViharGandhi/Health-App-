import asyncio
from datetime import date

import pytest

from mock_recovery import MockRecoveryClient
from sleep_analytics import timing_records


@pytest.mark.parametrize('day,left,right,offset_start,offset_end', [
    (date(2026, 10, 25), '2026-10-25T00:45:00Z', '2026-10-25T01:15:00Z', '7200s', '3600s'),
    (date(2027, 10, 31), '2027-10-31T00:45:00Z', '2027-10-31T01:15:00Z', '7200s', '3600s'),
    (date(2026, 3, 29), '2026-03-29T00:45:00Z', '2026-03-29T01:15:00Z', '3600s', '7200s'),
    (date(2027, 3, 28), '2027-03-28T00:45:00Z', '2027-03-28T01:15:00Z', '3600s', '7200s'),
])
def test_clock_transition_does_not_discard_positive_physical_sleep(day, left, right, offset_start, offset_end):
    client = MockRecoveryClient(day)
    point = next(p for p in client.points['sleep'] if p['name'] == f'demo-main-{day}')
    point['sleep']['interval'].update(startTime=left, endTime=right,
                                    startUtcOffset=offset_start, endUtcOffset=offset_end)
    point['sleep']['summary'].update(minutesAsleep='25', minutesToFallAsleep='0', minutesAfterWakeUp='0')
    result = asyncio.run(client.get_sleep_session(day))
    assert result is not None
    assert result['total_duration'] == 1500


def test_analytics_compares_instants_instead_of_timestamp_text():
    records = timing_records([{'date': '2026-10-25',
        'onset_time': '2026-10-25T02:45:00+02:00', 'sleep_wake_time': '2026-10-25T02:15:00+01:00',
        'asleep_minutes': 25., 'period_minutes': 30.}])
    assert len(records) == 1
    assert (records[0]['wake_time'] - records[0]['bed_time']).total_seconds() == 1800
