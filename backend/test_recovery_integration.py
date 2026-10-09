import asyncio
import unittest
from datetime import date, timedelta
from statistics import median
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app, _compute_connected_recovery, _compute_real_strain, _recovery_sleep_need
from mock_data import get_mock_dashboard
from mock_recovery import MockRecoveryClient, SCENARIOS
from sleep_need_inputs import SleepNeedInputs


DAY = date(2026, 9, 30)


class RecoveryIntegrationTests(unittest.TestCase):
    def request(self, scenario="normal"):
        client = MockRecoveryClient(DAY, scenario)
        with patch("main._get_token", new=AsyncMock(return_value="token")), \
             patch("main.GoogleHealthClient", return_value=client):
            response = TestClient(app).get("/api/recovery", headers={"X-User-Date": DAY.isoformat(), "X-User-Age": "30"})
        self.assertEqual(response.status_code, 200)
        return response.json(), client

    def test_connected_endpoint_returns_estimated_score_zone_confidence_and_components(self):
        data, client = self.request()
        self.assertFalse(data["is_mock"])
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["zone"], "normal")
        self.assertEqual(data["confidence"], "high")
        self.assertEqual(data["score"], data["percent"])
        self.assertTrue(data["estimated"])
        self.assertEqual(set(data["components"]), {"z_hrv", "z_rhr", "sleep_adj"})
        self.assertEqual(data["sleep_context"]["sleep_min"], 470)
        self.assertEqual(data["baseline_days"], 60)
        self.assertEqual(data["recent_nights"], 6)  # Fixture has today and six prior nights.
        self.assertIsNone(data["strain_component"])
        self.assertIsNone(data["sleep_component"])
        self.assertIn("Estimated", data["status_reason"])
        self.assertEqual(len(client.calls), 11)
        hr_calls = [expr for kind, expr in client.calls if kind == "heart-rate"]
        self.assertEqual(len(hr_calls), 1)
        self.assertIn('>= "2026-09-20"', hr_calls[0])  # Padding for physiological windows across midnight.
        self.assertIn('< "2026-10-01"', hr_calls[0])  # Fetch next sleep's day; the calculator still excludes sleep time.
        hrv_calls = [expr for kind, expr in client.calls if kind == "daily-heart-rate-variability"]
        self.assertEqual(len(hrv_calls), 1)
        self.assertIn('>= "2026-07-25"', hrv_calls[0])

    def test_existing_comparisons_still_use_previous_14_days(self):
        data, client = self.request()
        history = asyncio.run(client.get_health_history(DAY - timedelta(days=14), DAY, ("hrv", "rhr")))
        hrv = [point["value"] for point in history["hrv"] if point["date"] < DAY.isoformat()]
        rhr = [point["value"] for point in history["rhr"] if point["date"] < DAY.isoformat() and point["method"] == data["rhr_method"]]
        self.assertEqual(data["hrv_baseline"], round(median(hrv), 1))
        self.assertEqual(data["rhr_baseline"], round(median(rhr), 1))
        self.assertEqual(data["hrv_reference_count"], len(hrv))
        self.assertEqual(data["rhr_reference_count"], len(rhr))
        self.assertNotEqual(data["hrv_reference_count"], data["baseline_days"])

    def test_each_demo_scenario_runs_the_real_connected_path(self):
        results = {}
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                data, client = self.request(scenario)
                results[scenario] = data
                self.assertEqual(len(client.calls), 11)
        self.assertEqual(results["above_normal"]["zone"], "above_normal")
        self.assertEqual(results["below_normal"]["zone"], "below_normal")
        for scenario in ("building_reference", "sparse_recent"):
            self.assertEqual(results[scenario]["status"], "building_reference")
            self.assertIsNone(results[scenario]["percent"])
            self.assertIsNone(results[scenario]["zone"])
            self.assertTrue(results[scenario]["is_calibrating"])
        self.assertEqual(results["low_confidence"]["confidence"], "low")
        self.assertIsNone(results["low_confidence"]["score"])
        self.assertIsNotNone(results["low_confidence"]["zone"])
        for scenario in ("missing_rhr", "method_change"):
            self.assertIsNone(results[scenario]["components"]["z_rhr"])
            self.assertEqual(results[scenario]["confidence"], "medium")
        self.assertIsNone(results["missing_today_hrv"]["today_hrv"])
        self.assertEqual(results["missing_today_hrv"]["recent_nights"], 6)
        self.assertEqual(results["illness_flag"]["z"], -.5)
        self.assertTrue(results["illness_flag"]["illness_flag"])
        for scenario in ("missing_sleep", "short_sleep"):
            self.assertIsNone(results[scenario]["sleep_context"]["sleep_min"])
            self.assertEqual(results[scenario]["components"]["sleep_adj"], 0)
            self.assertNotEqual(results[scenario]["confidence"], "high")

    def test_batched_sleep_need_matches_existing_daily_calculations(self):
        async def check():
            client = MockRecoveryClient(DAY)
            batch = await _recovery_sleep_need(client, DAY, 30)
            self.assertEqual(len(client.calls), 6)
            sleep = await client.get_sleep_need_history(DAY - timedelta(days=7), DAY - timedelta(days=1))
            naps = await client.get_nap_minutes_history(DAY - timedelta(days=1), DAY - timedelta(days=1))
            strain = {}
            for offset in range(1, 9):
                day = DAY - timedelta(days=offset)
                result = await _compute_real_strain(client, day, 30)
                strain[day] = result.strain / 21 * 100 if result.strain is not None and result.coverage > 0 else None
            daily = SleepNeedInputs(sleep, strain, naps).for_tonight(DAY - timedelta(days=1))
            self.assertAlmostEqual(batch.total_need_min, daily.total_need_min, delta=.1)  # API scores round to 0.1; internal inputs do not.
        asyncio.run(check())

    def test_current_sleep_does_not_change_its_own_need(self):
        client = MockRecoveryClient(DAY)
        first = asyncio.run(_compute_connected_recovery(client, DAY, 30))
        current = next(point for point in client.points["sleep"] if point["name"] == f"demo-main-{DAY}")
        current["sleep"]["summary"]["minutesAsleep"] = "270"
        second = asyncio.run(_compute_connected_recovery(client, DAY, 30))
        self.assertEqual(first.sleep_context["need_min"], second.sleep_context["need_min"])
        self.assertLess(second.components["sleep_adj"], first.components["sleep_adj"])

    def test_missing_previous_day_strain_leaves_need_missing(self):
        client = MockRecoveryClient(DAY)
        yesterday = (DAY - timedelta(days=1)).isoformat()
        client.points["heart-rate"] = [point for point in client.points["heart-rate"]
                                      if not point["heartRate"]["sampleTime"]["physicalTime"].startswith(yesterday)]
        result = asyncio.run(_compute_connected_recovery(client, DAY, 30))
        self.assertIsNone(result.sleep_context["need_min"])
        self.assertIsNone(result.sleep_context["performance"])
        self.assertEqual(result.components["sleep_adj"], 0)
        self.assertEqual(result.confidence, "medium")

    def test_pending_current_sleep_is_not_used_as_completed_sleep(self):
        client = MockRecoveryClient(DAY)
        current = next(point for point in client.points["sleep"] if point["name"] == f"demo-main-{DAY}")
        current["sleep"]["metadata"]["processed"] = False
        result = asyncio.run(_compute_connected_recovery(client, DAY, 30))
        self.assertIsNone(result.sleep_context["sleep_min"])
        self.assertNotEqual(result.confidence, "high")

    def test_absent_optional_vitals_do_not_flag_illness(self):
        client = MockRecoveryClient(DAY)
        client.points["daily-respiratory-rate"] = []
        client.points["daily-sleep-temperature-derivations"] = []
        result = asyncio.run(_compute_connected_recovery(client, DAY, 30))
        self.assertFalse(result.illness_flag)
        self.assertEqual(result.status, "ok")

    def test_demo_endpoint_keeps_existing_algorithm(self):
        expected = get_mock_dashboard().recovery.model_dump()
        with patch("main._get_token", new=AsyncMock(return_value=None)):
            response = TestClient(app).get("/api/recovery")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_expired_connected_session_requires_reconnect_instead_of_demo(self):
        with patch("main._get_token", new=AsyncMock(return_value=None)), patch("main.get_session", return_value={"access_token": "expired"}):
            for path in ("/api/recovery", "/api/recovery/analytics", "/api/dashboard"):
                with self.subTest(path=path):
                    response = TestClient(app).get(path)
                    self.assertEqual(response.status_code, 401)

    def test_next_day_all_connected_endpoints_use_our_calculator_even_with_legacy_demo_selected(self):
        tomorrow = date(2026, 10, 7)
        for scenario in ("normal", "building_reference"):
            client = MockRecoveryClient(tomorrow, scenario)
            client.points["daily-oxygen-saturation"] = []
            expected = asyncio.run(_compute_connected_recovery(client, tomorrow, 22)).model_dump()
            headers = {"X-User-Date": tomorrow.isoformat(), "X-User-Age": "22"}
            with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
                for path, key in (("/api/recovery?demo=legacy", None),
                                  ("/api/recovery/analytics?demo=legacy", "current"),
                                  ("/api/dashboard", "recovery")):
                    with self.subTest(scenario=scenario, path=path):
                        response = TestClient(app).get(path, headers=headers)
                        self.assertEqual(response.status_code, 200)
                        result = response.json()[key] if key else response.json()
                        self.assertEqual(result, expected)
                        self.assertFalse(result["is_mock"])


if __name__ == "__main__":
    unittest.main()
