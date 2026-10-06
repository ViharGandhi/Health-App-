import asyncio
import unittest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import httpx

from google_health_client import GoogleHealthClient


class GoogleHealthClientTests(unittest.TestCase):
    def test_sleep_stress_fetches_three_paginated_data_types(self):
        client = GoogleHealthClient("token")
        client._points = unittest.mock.AsyncMock(side_effect=[["sleep"], ["hrv"], ["hr"]])
        result = asyncio.run(client.get_sleep_stress_points(date(2026, 10, 1), date(2026, 10, 3)))
        self.assertEqual(result, (["sleep"], ["hrv"], ["hr"]))
        calls = client._points.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["sleep", "heart-rate-variability", "heart-rate"])
        self.assertIn("heart_rate_variability.sample_time.physical_time", calls[1].args[1])
        self.assertIn("2026-09-30T00:00:00Z", calls[1].args[1])
        self.assertIn("2026-10-05T00:00:00Z", calls[1].args[1])

    def test_main_sleep_timing_uses_fitbit_flag_and_onset_latency(self):
        client = GoogleHealthClient("token")
        client._points = lambda *args: asyncio.sleep(0, result=[
            {"sleep": {"interval": {"startTime": "2026-09-29T20:00:00Z", "endTime": "2026-09-30T05:00:00Z", "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
                       "metadata": {"mainSleep": False, "nap": False}, "summary": {"minutesAsleep": "500"}}},
            {"sleep": {"interval": {"startTime": "2026-09-29T21:30:00Z", "endTime": "2026-09-30T05:30:00Z", "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
                       "metadata": {"mainSleep": True, "nap": False}, "summary": {"minutesAsleep": "420", "minutesToFallAsleep": "20", "minutesAfterWakeUp": "10"}}},
            {"sleep": {"interval": {"startTime": "2026-09-30T08:00:00Z", "endTime": "2026-09-30T09:00:00Z", "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
                       "metadata": {"mainSleep": False, "nap": True}, "summary": {"minutesAsleep": "50"}}},
        ])
        result = asyncio.run(client.get_main_sleep_timing_history(date(2026, 9, 30), date(2026, 9, 30)))
        self.assertEqual(result, [{"date": date(2026, 9, 30),
                                   "bed_time": datetime(2026, 9, 29, 23, 50),
                                   "wake_time": datetime(2026, 9, 30, 7, 20)}])

    def test_non_main_sleep_does_not_become_a_daily_record(self):
        client = GoogleHealthClient("token")
        client._points = lambda *args: asyncio.sleep(0, result=[
            {"sleep": {"interval": {"startTime": "2026-09-29T22:00:00Z", "endTime": "2026-09-30T06:00:00Z", "startUtcOffset": "0s", "endUtcOffset": "0s"},
                       "metadata": {"mainSleep": False, "nap": False}, "summary": {"minutesAsleep": "440"}}},
        ])
        result = asyncio.run(client.get_main_sleep_timing_history(date(2026, 9, 30), date(2026, 9, 30)))
        self.assertEqual(result, [])

    def test_reconciled_points_paginate_and_preserve_filters(self):
        requests = []

        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(200, json={"dataPoints": [{"dailyHeartRateVariability": {
                    "date": {"year": 2026, "month": 9, "day": 30},
                    "averageHeartRateVariabilityMilliseconds": "53.2",
                }}], "nextPageToken": "next"})
            return httpx.Response(200, json={"dataPoints": []})

        transport = httpx.MockTransport(respond)
        mock_client = httpx.AsyncClient(transport=transport)
        with patch("google_health_client.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(GoogleHealthClient("token").get_daily_hrv(date(2026, 9, 30)))

        self.assertEqual(result, 53.2)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.path, "/v4/users/me/dataTypes/daily-heart-rate-variability/dataPoints:reconcile")
        self.assertEqual(requests[0].url.params["dataSourceFamily"], "users/me/dataSourceFamilies/google-wearables")
        self.assertEqual(requests[0].url.params["pageSize"], "10000")
        self.assertEqual(requests[0].url.params["filter"], 'daily_heart_rate_variability.date >= "2026-09-30" AND daily_heart_rate_variability.date < "2026-10-01"')
        self.assertEqual(requests[1].url.params["pageToken"], "next")
        self.assertEqual(requests[1].url.params["pageSize"], "10000")

    def test_sleep_and_exercise_keep_the_api_session_page_limit(self):
        for data_type, reconcile in (("sleep", True), ("sleep", False), ("exercise", True)):
            requests = []
            def respond(request):
                requests.append(request)
                return httpx.Response(200, json={"dataPoints": []})
            mock_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            with self.subTest(data_type=data_type, reconcile=reconcile), \
                 patch("google_health_client.httpx.AsyncClient", return_value=mock_client):
                asyncio.run(GoogleHealthClient("token")._points(data_type, "", reconcile=reconcile))
            self.assertEqual(requests[0].url.params["pageSize"], "25")

    def test_daily_metric_filters_use_proto_names_not_json_names(self):
        client = GoogleHealthClient("token")
        client._points = AsyncMock(return_value=[])
        day = date(2026, 9, 30)
        asyncio.run(client.get_deep_sleep_hrv(day))
        asyncio.run(client.get_hrv_history())
        asyncio.run(client.get_resting_heart_rate(day))
        self.assertTrue(client._points.call_args_list[0].args[1].startswith("daily_heart_rate_variability.date "))
        self.assertTrue(client._points.call_args_list[1].args[1].startswith("daily_heart_rate_variability.date "))
        self.assertTrue(client._points.call_args_list[2].args[1].startswith("daily_resting_heart_rate.date "))

    def test_health_history_filters_keep_json_response_fields_separate(self):
        client = GoogleHealthClient("token")
        client._points = AsyncMock(return_value=[{"dailyRestingHeartRate": {
            "date": {"year": 2026, "month": 9, "day": 30}, "beatsPerMinute": "56",
        }}])
        result = asyncio.run(client.get_health_history(date(2026, 9, 30), date(2026, 9, 30)))
        for call in client._points.call_args_list:
            data_type, filter_expr = call.args
            field = data_type.replace("-", "_")
            self.assertEqual(filter_expr, f'{field}.date >= "2026-09-30" AND {field}.date < "2026-10-01"')
        self.assertEqual(result["rhr"][0]["value"], 56)

    def test_intraday_heart_rate_filter_uses_proto_name(self):
        client = GoogleHealthClient("token")
        client._points = AsyncMock(return_value=[])
        asyncio.run(client.get_intraday_heart_rate(date(2026, 9, 30), date(2026, 10, 1)))
        client._points.assert_awaited_once_with("heart-rate", (
            'heart_rate.sample_time.civil_time >= "2026-09-30" AND '
            'heart_rate.sample_time.civil_time < "2026-10-02"'
        ))

    def test_api_errors_are_not_treated_as_missing_data(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(403, json={"error": "forbidden"}))
        mock_client = httpx.AsyncClient(transport=transport)
        with patch("google_health_client.httpx.AsyncClient", return_value=mock_client):
            with self.assertRaises(httpx.HTTPStatusError):
                asyncio.run(GoogleHealthClient("token").get_resting_heart_rate(date(2026, 9, 30)))

    def test_rate_limit_retries_then_returns_points(self):
        calls = 0

        def respond(request):
            nonlocal calls
            calls += 1
            return (httpx.Response(429, headers={"Retry-After": "0"}) if calls == 1
                    else httpx.Response(200, json={"dataPoints": [{"dailyRestingHeartRate": {
                        "beatsPerMinute": "56"}}]}))

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("google_health_client.httpx.AsyncClient", return_value=mock_client), \
             patch("google_health_client.asyncio.sleep", new=AsyncMock()) as wait:
            result = asyncio.run(GoogleHealthClient("token").get_resting_heart_rate(date(2026, 9, 30)))
        self.assertEqual(result, 56)
        self.assertEqual(calls, 2)
        wait.assert_awaited_once_with(0)

    def test_sleep_summary_uses_wake_date_and_ignores_naps(self):
        client = GoogleHealthClient("token")
        client._points = lambda *args: asyncio.sleep(0, result=[
            {"sleep": {"interval": {"startTime": "2026-09-29T21:00:00Z", "endTime": "2026-09-30T05:00:00Z", "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
                       "metadata": {"nap": False}, "summary": {"minutesAsleep": "420", "minutesAwake": "60", "minutesInSleepPeriod": "480", "minutesToFallAsleep": "10", "stagesSummary": [
                           {"type": "DEEP", "minutes": "100", "count": "2"}, {"type": "REM", "minutes": "90", "count": "3"},
                           {"type": "LIGHT", "minutes": "230", "count": "4"}, {"type": "AWAKE", "minutes": "60", "count": "5"}]}}},
            {"sleep": {"interval": {"startTime": "2026-09-30T11:00:00Z", "endTime": "2026-09-30T11:30:00Z"}, "metadata": {"nap": True}}},
        ])

        result = asyncio.run(client.get_sleep_session(date(2026, 9, 30)))
        self.assertEqual(result["date"], date(2026, 9, 30))
        self.assertEqual(result["sleep_end_time"], datetime(2026, 9, 30, 7))
        self.assertEqual(result["total_duration"], 420 * 60)
        self.assertEqual(result["deep_sleep_duration"], 100 * 60)
        self.assertEqual(result["interruption_count"], 5)


if __name__ == "__main__":
    unittest.main()
