import asyncio
from datetime import date
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from main import app, _compute_real_sleep, _compute_connected_recovery, _load_sleep_need_inputs
from mock_recovery import MockRecoveryClient

DAY = date(2026, 10, 7)


def test_connected_sleep_reports_defaulted_vital_components():
    async def run():
        client = MockRecoveryClient(DAY)
        inputs = await _load_sleep_need_inputs(client, DAY, 30)
        sleep = await _compute_real_sleep(client, DAY, inputs.for_tonight(DAY), 30)
        assert sleep.partial is True
        for name in ('sleeping_hrv', 'sleeping_hr', 'hr_dip'):
            assert sleep.components_available[name] is False
            assert sleep.defaulted_components[name] == 50.
    asyncio.run(run())


def test_missing_connected_summary_has_a_reason():
    async def run():
        client = MockRecoveryClient(DAY, 'missing_sleep')
        result = await _compute_real_sleep(client, DAY, None, 30)
        assert result.score is None
        assert result.status_reason == 'sleep_duration_unavailable'
        assert result.partial and not any(result.components_available.values())
    asyncio.run(run())
