import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

import google_health_client as google
from main import app


class GoogleHealthLoadingTests(unittest.TestCase):
    def setUp(self):
        google._point_cache.clear()
        google._point_requests.clear()
        google._request_lanes.clear()

    def test_simultaneous_cards_share_one_read_and_account_results_stay_separate(self):
        async def check():
            reads = []
            async def respond(request):
                reads.append(request.headers['Authorization'])
                await asyncio.sleep(0)
                return httpx.Response(200, json={'dataPoints': [{'value': len(reads)}]})
            with patch('google_health_client.httpx.AsyncClient', return_value=httpx.AsyncClient(transport=httpx.MockTransport(respond))):
                a, b = google.GoogleHealthClient('account-a', cache=True), google.GoogleHealthClient('account-a', cache=True)
                first, second = await asyncio.gather(a._points('heart-rate', 'same'), b._points('heart-rate', 'same'))
            self.assertEqual(first, second)
            self.assertEqual(len(reads), 1)
            self.assertEqual(await b._points('heart-rate', 'same'), first)
            with patch('google_health_client.httpx.AsyncClient', return_value=httpx.AsyncClient(transport=httpx.MockTransport(respond))):
                other = await google.GoogleHealthClient('account-b', cache=True)._points('heart-rate', 'same')
            self.assertNotEqual(first, other)
            self.assertEqual(len(reads), 2)
        asyncio.run(check())

    def test_expired_reads_refresh_and_failed_reads_are_not_cached(self):
        async def check():
            client = google.GoogleHealthClient('account', cache=True)
            client._fetch_points = AsyncMock(return_value=[{'value': 1}])
            await client._points('sleep', 'same')
            key = next(iter(google._point_cache))
            google._point_cache[key] = (0, [{'value': 1}])
            client._fetch_points.return_value = [{'value': 2}]
            self.assertEqual(await client._points('sleep', 'same'), [{'value': 2}])
            self.assertEqual(client._fetch_points.await_count, 2)
            client._fetch_points.side_effect = httpx.ConnectError('offline')
            with self.assertRaises(httpx.ConnectError):
                await client._points('sleep', 'different')
            self.assertNotIn((client.account_key, 'sleep', 'different', True), google._point_cache)
            self.assertFalse(google._point_requests)
        asyncio.run(check())

    def test_requests_for_an_account_are_paced_across_cards(self):
        async def check():
            a, b = google.GoogleHealthClient('account', cache=True), google.GoogleHealthClient('account', cache=True)
            with patch('google_health_client.time.monotonic', return_value=100), patch('google_health_client.asyncio.sleep', new=AsyncMock()) as wait:
                await a._pace_request()
                await b._pace_request()
                wait.assert_awaited_once_with(0.5)
        asyncio.run(check())

    def test_google_failures_return_actionable_api_errors(self):
        request = httpx.Request('GET', 'https://health.googleapis.com/data')
        for status in (429, 403, 400):
            error = httpx.HTTPStatusError('upstream error', request=request, response=httpx.Response(status, request=request))
            with self.subTest(status=status), patch('main._get_token', AsyncMock(return_value='token')), patch('main._compute_real_strain', AsyncMock(side_effect=error)):
                response = TestClient(app).get('/api/strain')
                self.assertEqual(response.status_code, status if status in (429, 403) else 502)
                self.assertTrue(response.json()['detail'])

