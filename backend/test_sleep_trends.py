import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app
from sleep_consistency import SleepConsistencyCalculator, SleepNight
from sleep_efficiency import SleepEfficiencyCalculator
from sleep_trends import build_sleep_trend, range_start


def sleep_record(day, bedtime_minutes=0, wake_minutes=0, asleep=440, period=500):
    return {
        "date": day,
        "bed_time": datetime.combine(day - timedelta(days=1), datetime.min.time())
                    + timedelta(hours=23, minutes=50 + bedtime_minutes),
        "wake_time": datetime.combine(day, datetime.min.time())
                     + timedelta(hours=7, minutes=wake_minutes),
        "time_asleep_minutes": asleep,
        "time_in_bed_minutes": period,
    }


class SleepTrendTests(unittest.TestCase):
    def test_midnight_crossing_is_small_variation(self):
        end = date(2026, 10, 1)
        records = [sleep_record(end - timedelta(days=6 - index),
                                bedtime_minutes=20 if index % 2 else 0,
                                wake_minutes=10 if index % 2 else 0)
                   for index in range(7)]
        result = SleepConsistencyCalculator.calculate([
            SleepNight(row["date"], row["bed_time"], row["wake_time"]) for row in records
        ])
        self.assertIsNotNone(result.timing_variability_minutes)
        self.assertLess(result.bed_time_variability_minutes, 15)
        self.assertLess(result.timing_variability_minutes, 15)

    def test_missing_night_leaves_consistency_gap(self):
        end = date(2026, 10, 1)
        records = [sleep_record(end - timedelta(days=day)) for day in range(13) if day != 3]
        trend = build_sleep_trend(records, end - timedelta(days=6), end, "W", "consistency", False)
        self.assertEqual(len(trend.days), 7)
        self.assertEqual(trend.recorded_nights, 6)
        self.assertEqual(trend.scored_days, 3)
        self.assertTrue(all(day.value is None for day in trend.days[-4:]))

    def test_efficiency_uses_valid_periods_and_weighted_average(self):
        end = date(2026, 10, 1)
        records = [sleep_record(end - timedelta(days=2), asleep=420, period=500),
                   sleep_record(end - timedelta(days=1), asleep=480, period=500),
                   sleep_record(end, asleep=500, period=0)]
        trend = build_sleep_trend(records, end - timedelta(days=2), end, "W", "efficiency", False)
        self.assertEqual([day.value for day in trend.days], [84.0, 96.0, None])
        self.assertEqual(trend.average_value, 90.0)
        self.assertIsNone(SleepEfficiencyCalculator.calculate_single_night(500, 400))

    def test_range_uses_calendar_months(self):
        self.assertEqual(range_start(date(2026, 10, 1), "W"), date(2026, 9, 25))
        self.assertEqual(range_start(date(2026, 10, 1), "6M"), date(2026, 4, 2))
        self.assertEqual(range_start(date(2026, 10, 1), "1Y"), date(2025, 10, 2))

    def test_connected_account_without_records_never_receives_demo_data(self):
        client = type("Client", (), {"get_sleep_trend_history": AsyncMock(return_value=[])})()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            for metric in ("efficiency", "consistency"):
                response = TestClient(app).get(f"/api/sleep/{metric}?timeframe=1Y")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertFalse(data["is_mock"])
                self.assertIsNone(data["average_value"])
                self.assertEqual(data["recorded_nights"], 0)
                self.assertTrue(all(day["value"] is None for day in data["days"]))


if __name__ == "__main__":
    unittest.main()
