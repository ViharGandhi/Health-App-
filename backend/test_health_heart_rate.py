import asyncio
import unittest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from health_trends import build_heart_rate_response
from google_health_client import GoogleHealthClient
from main import app


class HealthHeartRateTests(unittest.TestCase):
    def test_google_reading_keeps_physical_instant_and_device_offset_for_monitor(self):
        client = GoogleHealthClient("token")
        client._points = AsyncMock(return_value=[{"heartRate": {
            "sampleTime": {"physicalTime": "2026-10-06T18:29:59Z", "utcOffset": "19800s"},
            "beatsPerMinute": "116",
        }}])
        samples = asyncio.run(client.get_intraday_heart_rate(date(2026, 10, 6), preserve_offset=True))
        result = build_heart_rate_response(samples, date(2026, 10, 6), False)
        self.assertEqual(result.latest_heart_rate.sample_time, "2026-10-06T23:59:59+05:30")
        legacy = asyncio.run(client.get_intraday_heart_rate(date(2026, 10, 6)))
        self.assertIsNone(legacy[0][0].tzinfo)

    def test_latest_is_newest_individual_reading_not_median_or_response_order(self):
        samples = [
            (datetime.fromisoformat("2026-10-06T08:05:02+02:00"), 81.25),
            (datetime.fromisoformat("2026-10-06T08:00:00+02:00"), 60),
        ]
        result = build_heart_rate_response(samples, date(2026, 10, 6), False)
        self.assertEqual(result.latest_heart_rate.value, 81.25)
        self.assertEqual(result.latest_heart_rate.sample_time, "2026-10-06T08:05:02+02:00")
        self.assertEqual(result.heart_rate[0].value, 70.6)

    def test_missing_and_invalid_readings_do_not_become_current_bpm(self):
        samples = [
            (datetime.fromisoformat("2026-10-05T23:59:00+02:00"), 88),
            (datetime.fromisoformat("2026-10-07T00:01:00+02:00"), 99),
            (datetime.fromisoformat("2026-10-06T08:00:00+02:00"), 0),
            (datetime.fromisoformat("2026-10-06T08:01:00+02:00"), float("nan")),
            (datetime.fromisoformat("2026-10-06T08:02:00+02:00"), float("inf")),
        ]
        for history in ([], samples):
            result = build_heart_rate_response(history, date(2026, 10, 6), False)
            self.assertIsNone(result.latest_heart_rate)
            self.assertEqual(result.heart_rate, [])

    def test_refresh_reads_only_heart_rate_for_client_day_and_returns_new_sample(self):
        client = type("Client", (), {
            "get_intraday_heart_rate": AsyncMock(side_effect=[
                [(datetime.fromisoformat("2026-10-06T08:00:02+02:00"), 60)],
                [(datetime.fromisoformat("2026-10-06T08:01:02+02:00"), 72)],
                [],
            ]),
        })()
        with patch("main._get_token", AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client) as factory:
            api = TestClient(app)
            first = api.get("/api/health/heart-rate", headers={"X-User-Date": "2026-10-06"})
            second = api.get("/api/health/heart-rate", headers={"X-User-Date": "2026-10-06"})
            next_day = api.get("/api/health/heart-rate", headers={"X-User-Date": "2026-10-07"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["latest_heart_rate"]["value"], 60)
        self.assertEqual(second.json()["latest_heart_rate"]["value"], 72)
        self.assertFalse(second.json()["is_mock"])
        self.assertEqual(next_day.json()["date"], "2026-10-07")
        self.assertIsNone(next_day.json()["latest_heart_rate"])
        self.assertEqual(client.get_intraday_heart_rate.await_args_list[-1].args, (date(2026, 10, 7),))
        self.assertEqual(client.get_intraday_heart_rate.await_args_list[-1].kwargs, {"preserve_offset": True})
        factory.assert_called_with("token", cache=True)

    def test_disconnected_samples_are_explicitly_labeled_and_dated(self):
        with patch("main._get_token", AsyncMock(return_value=None)):
            result = TestClient(app).get("/api/health/heart-rate")
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertTrue(data["is_mock"])
        self.assertIsNotNone(data["latest_heart_rate"])
        self.assertEqual(data["latest_heart_rate"]["sample_time"][:10], data["date"])

    def test_upstream_failure_is_reported_without_substituting_demo(self):
        request = httpx.Request("GET", "https://health.googleapis.com/data")
        error = httpx.HTTPStatusError("upstream error", request=request, response=httpx.Response(429, request=request))
        client = type("Client", (), {"get_intraday_heart_rate": AsyncMock(side_effect=error)})()
        with patch("main._get_token", AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            response = TestClient(app).get("/api/health/heart-rate")
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
