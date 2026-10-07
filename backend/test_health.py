import asyncio
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from google_health_client import GoogleHealthClient
from health_trends import build_health_response, METRICS
from main import app, _compute_real_recovery, _compute_real_strain
from mock_data import get_mock_health


class HealthTests(unittest.TestCase):
    def test_month_and_previous_periods_skip_missing_readings(self):
        result = build_health_response({"hrv": [
            {"date": "2026-08-15", "value": 900},
            {"date": "2026-08-31", "value": 0},
            {"date": "2026-09-06", "value": 40},
            {"date": "2026-09-07", "value": 50},
            {"date": "2026-10-06", "value": 60},
        ]}, [], date(2026, 9, 7), date(2026, 10, 6), "M", False)
        self.assertEqual(len(result.metrics["hrv"]), 30)
        self.assertEqual(result.previous_range_start, "2026-08-08")
        self.assertEqual(result.previous_range_end, "2026-09-06")
        self.assertEqual(result.averages["hrv"], 55)
        self.assertAlmostEqual(result.previous_averages["hrv"], 940 / 3)
        self.assertIsNone(result.averages["spo2"])
        self.assertIsNone(result.previous_averages["spo2"])

    def test_demo_has_distinct_prior_period_averages(self):
        for timeframe in ("W", "M", "6M"):
            result = get_mock_health(timeframe)
            self.assertLess(result.previous_range_end, result.range_start)
            self.assertIsNotNone(result.previous_averages["hrv"])
            self.assertIsNotNone(result.averages["hrv"])
        self.assertEqual(len(get_mock_health("M").metrics["hrv"]), 30)

    def test_month_endpoint_fetches_prior_comparison_and_reference_history(self):
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value={}),
            "get_intraday_heart_rate": AsyncMock(return_value=[]),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            response = TestClient(app).get("/api/health?timeframe=M", headers={"X-User-Date": "2026-10-06"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["metrics"]["hrv"]), 30)
        self.assertIsNone(response.json()["averages"]["hrv"])
        client.get_health_history.assert_awaited_once_with(date(2026, 7, 25), date(2026, 10, 6))

    def test_demo_series_are_aligned_and_labeled(self):
        result = get_mock_health()
        self.assertTrue(result.is_mock)
        self.assertEqual(set(result.metrics), set(METRICS))
        self.assertTrue(all(len(points) == 7 for points in result.metrics.values()))
        self.assertEqual(result.metrics["hrv"][-1].value, 44.8)
        self.assertTrue(result.metrics["vo2_max"][-1].estimated)
        self.assertGreater(len(result.heart_rate), 0)
        year = get_mock_health("1Y")
        self.assertGreaterEqual(len(year.metrics["hrv"]), 365)
        self.assertTrue(any(point.value is None for point in year.metrics["hrv"]))

    def test_google_daily_vital_fields_and_missing_values(self):
        client = GoogleHealthClient("token")
        calls = []

        async def points(data_type, filter_expr):
            calls.append((data_type, filter_expr))
            if data_type == "daily-oxygen-saturation":
                return [{"dailyOxygenSaturation": {
                    "date": {"year": 2026, "month": 10, "day": 1},
                    "averagePercentage": 97.2,
                }}]
            if data_type == "daily-sleep-temperature-derivations":
                return [{"dailySleepTemperatureDerivations": {
                    "date": {"year": 2026, "month": 10, "day": 1},
                    "nightlyTemperatureCelsius": 32.6,
                }}]
            if data_type == "daily-resting-heart-rate":
                return [{"dailyRestingHeartRate": {
                    "date": {"year": 2026, "month": 10, "day": 1},
                    "beatsPerMinute": "55",
                    "dailyRestingHeartRateMetadata": {"calculationMethod": "WITH_SLEEP"},
                }}]
            return []

        client._points = points
        result = asyncio.run(client.get_health_history(date(2026, 9, 30), date(2026, 10, 1)))
        self.assertEqual(result["spo2"], [{"date": "2026-10-01", "value": 97.2, "estimated": None, "method": None}])
        self.assertEqual(result["skin_temperature"][0]["value"], 32.6)
        self.assertEqual(result["rhr"][0]["method"], "WITH_SLEEP")
        self.assertEqual(result["hrv"], [])
        self.assertEqual(len(calls), 6)
        self.assertIn('daily_oxygen_saturation.date >= "2026-09-30"', calls[2][1])

    def test_recovery_history_fetches_only_hrv_and_rhr(self):
        client = GoogleHealthClient("token")
        calls = []

        async def points(data_type, _filter_expr):
            calls.append(data_type)
            return []

        client._points = points
        result = asyncio.run(client.get_health_history(date(2026, 9, 17), date(2026, 10, 1), ("hrv", "rhr")))
        self.assertEqual(set(result), {"hrv", "rhr"})
        self.assertEqual(calls, ["daily-heart-rate-variability", "daily-resting-heart-rate"])

    def test_health_endpoint_aligns_missing_days_without_fetching_intraday_heart_rate(self):
        today = date.today().isoformat()
        history = {key: [] for key in METRICS}
        history["hrv"] = [{"date": today, "value": 45.0, "estimated": None}]
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value=history),
            "get_intraday_heart_rate": AsyncMock(return_value=[
                (datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=8), 60.0),
                (datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=8, minutes=5), 80.0),
            ]),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            response = TestClient(app).get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["is_mock"])
        self.assertEqual(data["metrics"]["hrv"][-1]["value"], 45.0)
        self.assertIsNone(data["metrics"]["rhr"][-1]["value"])
        self.assertEqual(data["heart_rate"], [])
        self.assertIsNone(data["latest_heart_rate"])
        client.get_intraday_heart_rate.assert_not_awaited()
        self.assertEqual(len(data["metrics"]["hrv"]), 7)

    def test_baseline_uses_only_previous_days_and_leaves_gaps(self):
        start = date(2026, 9, 15)
        end = date(2026, 9, 16)
        history = {"hrv": [
            {"date": (start - timedelta(days=offset)).isoformat(), "value": 40.0}
            for offset in range(1, 8)
        ] + [{"date": start.isoformat(), "value": 80.0}]}
        result = build_health_response(history, [], start, end, "W", False)
        self.assertEqual(result.metrics["hrv"][0].baseline, 40.0)
        self.assertEqual(result.metrics["hrv"][0].value, 80.0)
        self.assertIsNone(result.metrics["hrv"][1].value)

    def test_optional_deep_sleep_hrv_is_distinct_from_daily_average(self):
        client = GoogleHealthClient("token")
        client._points = lambda *args: asyncio.sleep(0, result=[{
            "dailyHeartRateVariability": {
                "date": {"year": 2026, "month": 10, "day": 1},
                "averageHeartRateVariabilityMilliseconds": 44.0,
                "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds": 51.0,
            },
        }])
        self.assertEqual(asyncio.run(client.get_deep_sleep_hrv(date(2026, 10, 1))), 51.0)
        self.assertEqual(asyncio.run(client.get_daily_hrv(date(2026, 10, 1))), 44.0)

    def test_connected_recovery_hides_score_without_personal_history(self):
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value={
                "hrv": [{"date": "2026-10-01", "value": 44.0}],
                "rhr": [{"date": "2026-10-01", "value": 55.0, "method": "WITH_SLEEP"}],
            }),
        })()
        result = asyncio.run(_compute_real_recovery(client, date(2026, 10, 1)))
        self.assertTrue(result.is_calibrating)
        self.assertIsNone(result.score)
        self.assertIsNone(result.hrv_component)
        self.assertEqual(result.status, "calibrating")
        self.assertEqual(result.hrv_reference_count, 0)
        self.assertEqual(result.rhr_reference_count, 0)

    def test_connected_recovery_uses_prior_device_medians(self):
        history = {
            "hrv": [{"date": f"2026-09-{day}", "value": value} for day, value in zip(range(24, 31), [38, 39, 40, 41, 42, 43, 44])]
            + [{"date": "2026-10-01", "value": 46.0}],
            "rhr": [{"date": f"2026-09-{day}", "value": value, "method": "WITH_SLEEP"} for day, value in zip(range(24, 31), [52, 53, 54, 55, 56, 57, 58])]
            + [{"date": "2026-10-01", "value": 52.0, "method": "WITH_SLEEP"}],
        }
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value=history),
        })()
        result = asyncio.run(_compute_real_recovery(client, date(2026, 10, 1), 7.5, 92.0))
        self.assertFalse(result.is_calibrating)
        self.assertIsNone(result.score)
        self.assertEqual(result.status, "signals")
        self.assertIsNone(result.hrv_component)
        self.assertEqual(result.hrv_baseline, 41.0)
        self.assertEqual(result.rhr_baseline, 55.0)
        self.assertEqual(result.hrv_reference_count, 7)
        self.assertEqual(result.rhr_reference_count, 7)
        self.assertEqual(result.rhr_method, "WITH_SLEEP")
        self.assertEqual(result.sleep_hours, 7.5)
        self.assertEqual(result.sleep_efficiency_pct, 92.0)
        client.get_health_history.assert_awaited_once_with(date(2026, 9, 17), date(2026, 10, 1), ("hrv", "rhr"))

    def test_connected_recovery_excludes_different_rhr_methods(self):
        history = {
            "hrv": [{"date": "2026-10-01", "value": 46.0}],
            "rhr": [{"date": "2026-09-30", "value": 52.0, "method": "ONLY_WITH_AWAKE_DATA"},
                    {"date": "2026-10-01", "value": 55.0, "method": "WITH_SLEEP"}],
        }
        client = type("Client", (), {"get_health_history": AsyncMock(return_value=history)})()
        result = asyncio.run(_compute_real_recovery(client, date(2026, 10, 1)))
        self.assertEqual(result.rhr_reference_count, 0)
        self.assertIsNone(result.rhr_baseline)
        self.assertEqual(result.rhr_method, "WITH_SLEEP")

    def test_connected_recovery_endpoint_returns_sleep_context_without_score(self):
        today = date.today().isoformat()
        history = {
            "hrv": [{"date": today, "value": 44.0}],
            "rhr": [{"date": today, "value": 55.0, "method": "WITH_SLEEP"}],
        }
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value=history),
            "get_sleep_session": AsyncMock(return_value={"total_duration": 27000, "in_bed_duration": 28800, "sleep_duration_available": True}),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client), \
             patch("main._recovery_sleep_need", new=AsyncMock(return_value=None)):
            response = TestClient(app).get("/api/recovery")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["score"])
        self.assertEqual(data["status"], "building_reference")
        self.assertEqual(data["sleep_hours"], 7.5)
        self.assertEqual(data["sleep_efficiency_pct"], 93.8)
        self.assertEqual(data["rhr_method"], "WITH_SLEEP")

    def test_connected_recovery_uses_client_calendar_day(self):
        client = type("Client", (), {
            "get_health_history": AsyncMock(return_value={"hrv": [], "rhr": []}),
            "get_sleep_session": AsyncMock(return_value=None),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client), \
             patch("main._recovery_sleep_need", new=AsyncMock(return_value=None)):
            response = TestClient(app).get("/api/recovery", headers={"X-User-Date": "2026-09-30"})
            invalid = TestClient(app).get("/api/recovery", headers={"X-User-Date": "not-a-date"})
        self.assertEqual(response.status_code, 200)
        client.get_sleep_session.assert_awaited_once_with(date(2026, 9, 30))
        client.get_health_history.assert_awaited_once_with(date(2026, 7, 25), date(2026, 9, 30), ("hrv", "rhr", "respiratory_rate", "skin_temperature"))
        self.assertEqual(invalid.status_code, 400)

    def test_connected_strain_uses_supplied_age_for_zone_reference(self):
        client = type("Client", (), {
            "get_intraday_heart_rate": AsyncMock(return_value=[]),
            "get_workout_sessions": AsyncMock(return_value=[]),
            "get_sleep_stage_points": AsyncMock(return_value=[]),
            "get_health_history": AsyncMock(return_value={}),
        })()
        result = asyncio.run(_compute_real_strain(client, date(2026, 10, 1), age=35))
        self.assertEqual(result.params["hr_max"], 183.5)
        self.assertIsNone(result.max_hr)
        self.assertEqual(result.age_used, 35)
        self.assertFalse(result.age_is_default)
        with patch.dict('os.environ', {}, clear=True):
            default = asyncio.run(_compute_real_strain(client, date(2026, 10, 1)))
        self.assertTrue(default.age_is_default)
        with patch.dict('os.environ', {'USER_AGE': '22'}):
            configured = asyncio.run(_compute_real_strain(client, date(2026, 10, 1)))
        self.assertTrue(configured.age_missing)  # USER_AGE is not a silent Strain default.
        self.assertTrue(configured.is_calibrating)


if __name__ == "__main__":
    unittest.main()
