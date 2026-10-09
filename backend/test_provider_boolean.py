import asyncio
from datetime import date
from unittest.mock import AsyncMock
from google_health_client import GoogleHealthClient
from recovery_score import recovery_from_history


def test_boolean_provider_vitals_are_counted_as_rejected_not_converted_to_one():
    async def run():
        day = date(2026, 10, 7)
        client = GoogleHealthClient('synthetic')
        client._points = AsyncMock(return_value=[{'dailyHeartRateVariability': {
            'date': {'year': 2026, 'month': 10, 'day': 7},
            'averageHeartRateVariabilityMilliseconds': True}}])
        history = await client.get_health_history(day, day, ('hrv',))
        result = recovery_from_history(history, day)
        assert result.rejected_readings['hrv_today'] == 1
        assert result.data_quality_flag
    asyncio.run(run())
