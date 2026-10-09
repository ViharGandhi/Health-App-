"""Verify the live runner offline with Google-shaped data and a transport write guard."""
import asyncio
from datetime import date
import importlib.util
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('live_audit', HERE / 'live_readonly.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
from mock_recovery import mock_recovery_points


def test_full_live_script_pipeline_uses_only_in_memory_fixture():
    points = mock_recovery_points(date(2026, 10, 7))
    for kind in ('daily-oxygen-saturation', 'daily-vo2-max', 'heart-rate-variability'):
        points[kind] = []
    client = live.MemorySummaries(points)
    with patch.object(httpx.AsyncClient, 'send', side_effect=AssertionError('Outbound HTTP')):
        result = asyncio.run(live.audit(client, date(2026, 10, 7), 30))
    assert sum(result['recovery_confidence_counts'].values()) == 30
    assert result['stress_timing'] == 'unverified_not_scored'
    assert not any(k.endswith(':invalid') for k in result['score_validity_counts'])
    assert 'privacy' in result
    import json
    text = json.dumps(result)
    assert 'demo-main-' not in text
    assert '2026-10-07' not in text
    assert client.store is None


def test_no_token_makes_no_network_call():
    from types import SimpleNamespace
    args = SimpleNamespace(timezone='UTC', end=None, days=30, age=30, sex='m', anchor=None)
    with patch.dict('os.environ', {}, clear=True), patch.object(httpx.AsyncClient, 'send', side_effect=AssertionError('Outbound HTTP')):
        result = asyncio.run(live.run(args))
    assert result['live'] is False


@pytest.mark.parametrize('method,url', [('POST', 'https://health.googleapis.com/v4/users/me/dataTypes/sleep'),
    ('DELETE', 'https://health.googleapis.com/v4/users/me/dataTypes/sleep'),
    ('GET', 'https://example.test/v4/users/me/dataTypes/sleep'),
    ('GET', 'https://health.googleapis.com/v4/users/me/webhooks')])
def test_request_guard_blocks_writes_and_unrelated_resources(method, url):
    with pytest.raises(RuntimeError):
        asyncio.run(live.readonly_request(httpx.Request(method, url)))


def test_request_guard_allows_observation_get():
    asyncio.run(live.readonly_request(httpx.Request('GET', 'https://health.googleapis.com/v4/users/me/dataTypes/sleep/dataPoints')))
