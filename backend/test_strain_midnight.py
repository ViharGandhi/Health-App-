from datetime import date, datetime, timedelta, timezone
import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from strain import StrainConfig, day_window, seconds
from strain_service import calculate_days, load_strain_days


def test_midnight_excludes_yesterdays_load_before_next_main_sleep():
    tz = ZoneInfo('Europe/Berlin')
    yesterday = date(2026, 10, 9)
    midnight = datetime(2026, 10, 10, tzinfo=tz)
    wake = midnight - timedelta(hours=17)
    samples = [(midnight - timedelta(hours=4) + timedelta(minutes=i), 165.) for i in range(31)]
    samples += [(midnight + timedelta(minutes=i), 60.) for i in range(6)]
    sleeps = [{'start': wake - timedelta(hours=8), 'end': wake, 'main_sleep': True}]
    values = calculate_days(yesterday, midnight.date(), midnight + timedelta(minutes=5), tz,
                            30, 'm', False, (samples, [], sleeps, {}))
    assert values[yesterday]['strain'] > 0
    assert values[midnight.date()]['day_window']['start'] == midnight
    assert values[midnight.date()]['load'] == 0
    assert values[midnight.date()]['strain'] == 0


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_calendar_day_boundaries_follow_local_dst(day, hours):
    tz = ZoneInfo('Europe/Berlin')
    window = day_window(day, datetime(2026, 11, 1, tzinfo=timezone.utc), [], tz)
    assert window['start'].date() == day and window['start'].hour == 0
    assert window['end'].date() == day + timedelta(days=1) and window['end'].hour == 0
    assert seconds(window['start'], window['end']) == hours * 3600


def test_persisted_wake_based_strain_is_not_reused():
    async def run():
        day = date(2026, 10, 10)
        old_profile = hashlib.sha256(repr(('strain-v2', 'UTC', 30, 'm', False, StrainConfig())).encode()).hexdigest()
        store = SimpleNamespace(days_read=lambda *args, **kw: {f'{old_profile}:{day}': json.dumps({'strain': 19.})},
            calculation_version=lambda account: 0, days_write=lambda *args: None)
        client = SimpleNamespace(store=store, account_key='midnight-regression', strain_timezone=timezone.utc,
                                 strain_sex='m', strain_sex_defaulted=False)
        with patch('strain_service.fetch_strain_inputs', AsyncMock(return_value=([], [], [], {}))) as fetch:
            values, _ = await load_strain_days(client, day, day, datetime(2026, 10, 10, 0, 5, tzinfo=timezone.utc), 30)
        assert values[day]['strain'] == 0
        assert values[day]['day_window']['source'] == 'local_midnight'
        fetch.assert_awaited_once()
    asyncio.run(run())
