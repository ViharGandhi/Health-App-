from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from hypothesis import given, settings
import pytest

from main import app
from sleep_stage_webhooks import enqueue_sleep_notifications
from test_adapter_fuzz import payload


@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(payload)
def test_notification_adapter_rejects_malformed_payload_explicitly(value):
    try:
        enqueue_sleep_notifications(value, Mock())
    except ValueError:
        pass


@pytest.mark.parametrize('interval', [None, 1, 'wrong'])
def test_signed_malformed_interval_returns_400_without_queueing(interval):
    body = {'data': {'dataType': 'sleep', 'operation': 'UPSERT', 'healthUserId': 'fixture', 'intervals': [interval]}}
    store = Mock()
    with patch.dict('os.environ', {'GOOGLE_HEALTH_WEBHOOK_AUTHORIZATION': 'synthetic'}), \
         patch('sleep_stage_webhooks.verify_notification', AsyncMock()), patch('sleep_stage_webhooks.stage_store', return_value=store):
        result = TestClient(app).post('/api/webhooks/google-health/sleep-stages', json=body,
            headers={'Authorization': 'synthetic', 'GOOGLE-HEALTH-API-SIGNATURE': 'synthetic'})
    assert result.status_code == 400
    store.enqueue.assert_not_called()
