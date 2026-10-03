import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app
from mock_data import _build_mock_sleep_data, _build_sample_sleep_records
from sleep_consistency import (
    SleepConsistencyCalculator, SleepNight, _drift_score, consistency_label, score_main_sleep,
)
from sleep_efficiency import SleepEfficiencyCalculator
from sleep_trends import build_consistency_scores, build_sleep_trend, range_start


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
    def test_sample_sleep_history_is_stable_and_varied(self):
        end = date(2026, 10, 3)
        start = end - timedelta(days=40)
        records = _build_sample_sleep_records(start, end)
        self.assertEqual(records, _build_sample_sleep_records(start, end))
        self.assertEqual([row for row in records if row["date"] >= end - timedelta(days=6)],
                         _build_sample_sleep_records(end - timedelta(days=6), end))
        self.assertTrue(all(row["bed_time"] < row["wake_time"]
                            and 390 <= row["time_in_bed_minutes"] <= 600
                            and row["time_asleep_minutes"] < row["time_in_bed_minutes"]
                            for row in records))
        week = build_consistency_scores(records, end, "W", True)
        scores = [point.score for point in week.points if point.score is not None]
        self.assertGreater(max(scores) - min(scores), 20)
        for label, count in week.band_counts.items():
            self.assertEqual(count, sum(point.label == label for point in week.points))

    def test_latest_sample_sleep_matches_history(self):
        today = date.today()
        night = _build_sample_sleep_records(today, today)[0]
        sleep = _build_mock_sleep_data()
        self.assertEqual(sleep.sleep_start_time, night["bed_time"])
        self.assertEqual(sleep.sleep_end_time, night["wake_time"])
        self.assertAlmostEqual(sleep.total_duration / 60, night["time_asleep_minutes"], places=1)
        self.assertEqual(sleep.in_bed_duration / 60, night["time_in_bed_minutes"])

    def test_new_consistency_curve_and_labels(self):
        reference = {0: 100.0, 15: 97.5, 30: 92.6, 45: 83.7, 60: 69.5,
                     75: 51.2, 90: 32.8, 120: 9.7, 180: 0.5, 240: 0.0}
        self.assertEqual({minutes: round(_drift_score(minutes), 1) for minutes in reference}, reference)
        self.assertEqual([consistency_label(score) for score in (90, 75, 50, 49.9)],
                         ["Optimal", "Good", "Fair", "Poor"])

    def test_new_consistency_score_matches_weighted_example(self):
        day = date(2026, 10, 1)
        records = [sleep_record(day - timedelta(days=k), -drift, -drift)
                   for k, drift in enumerate((0, 0, 30, 60, 120))]
        nights = {row["date"]: SleepNight(row["date"], row["bed_time"], row["wake_time"])
                  for row in records}
        result = score_main_sleep(nights[day], nights)
        self.assertEqual(round(result.score, 1), 82.7)
        self.assertEqual(result.prior_nights, 4)

    def test_new_consistency_score_wraps_midnight_and_skips_missing_dates(self):
        day = date(2026, 10, 1)
        current = SleepNight(day, datetime(2026, 9, 30, 23, 50), datetime(2026, 10, 1, 7))
        before = SleepNight(day - timedelta(days=1), datetime(2026, 9, 30, 0, 10), datetime(2026, 9, 30, 7))
        older = SleepNight(day - timedelta(days=3), datetime(2026, 9, 27, 23, 50), datetime(2026, 9, 28, 7))
        one = score_main_sleep(current, {day: current, before.night_date: before})
        self.assertIsNone(one.score)
        two = score_main_sleep(current, {day: current, before.night_date: before, older.night_date: older})
        self.assertEqual(two.prior_nights, 2)
        self.assertEqual(round(two.drift_minutes, 1), 6.7)
        self.assertAlmostEqual(two.score, (0.4 * _drift_score(10) + 0.2 * _drift_score(0)) / 0.6)
        self.assertGreater(two.score, 90)

    def test_new_consistency_history_has_gaps_and_rolling_buckets(self):
        end = date(2026, 10, 2)
        start = range_start(end, "Y")
        records = [sleep_record(end - timedelta(days=offset), bedtime_minutes=offset % 35)
                   for offset in range(375) if offset not in (0, 3, 40)]
        weekly = build_consistency_scores(records, end, "W", False)
        self.assertEqual(len(weekly.points), 7)
        self.assertIsNone(weekly.points[-1].score)
        self.assertIsNone(weekly.points[-1].drift_minutes)
        self.assertEqual(weekly.scored_days, 5)
        self.assertIsNotNone(weekly.points[-2].drift_minutes)
        self.assertIsNotNone(weekly.change_percentage_points)
        month = build_consistency_scores(records, end, "M", False)
        self.assertEqual(len(month.points), 30)
        self.assertEqual(month.points[0].start_date, month.range_start)
        self.assertEqual(month.points[-1].end_date, end.isoformat())
        self.assertTrue(all(point.start_date == point.end_date for point in month.points))
        self.assertEqual(sum(point.scored_days for point in month.points), month.scored_days)
        year = build_consistency_scores(records, end, "Y", False)
        self.assertEqual(len(year.points), 12)
        self.assertEqual(year.points[0].start_date, start.isoformat())
        self.assertEqual(year.points[-1].end_date, end.isoformat())
        self.assertEqual(sum(point.scored_days for point in year.points), year.scored_days)
        self.assertEqual(sum(year.band_counts.values()), year.scored_days)
        self.assertEqual(set(year.band_counts), {"Optimal", "Good", "Fair", "Poor"})
        self.assertEqual(year.y_axis_min, 0)
        self.assertEqual(year.y_axis_max, 100)
        self.assertEqual(year.guide_lines, [90, 75, 50])

    def test_empty_buckets_remain_gaps_and_missing_comparison_is_null(self):
        end = date(2026, 10, 2)
        records = [sleep_record(end - timedelta(days=offset)) for offset in range(5)]
        result = build_consistency_scores(records, end, "Y", False)
        self.assertTrue(all(point.score is None for point in result.points[:-1]))
        self.assertIsNone(result.previous_average_score)
        self.assertIsNone(result.change_percentage_points)

    def test_comparison_uses_previous_equivalent_week(self):
        end = date(2026, 10, 2)
        records = [sleep_record(end - timedelta(days=offset),
                                bedtime_minutes=100 if offset < 7 else 0,
                                wake_minutes=100 if offset < 7 else 0)
                   for offset in range(18)]
        result = build_consistency_scores(records, end, "W", False)
        self.assertEqual(result.previous_average_score, 100.0)
        self.assertLess(result.average_score, 100.0)
        self.assertEqual(result.change_percentage_points,
                         round(result.average_score - result.previous_average_score, 1))

    def test_rolling_month_buckets_cover_leap_and_month_end_dates(self):
        for end in (date(2024, 2, 29), date(2026, 3, 31)):
            result = build_consistency_scores([], end, "Y", False)
            self.assertEqual(len(result.points), 12)
            self.assertEqual(result.points[0].start_date, result.range_start)
            self.assertEqual(result.points[-1].end_date, result.range_end)
            for previous, following in zip(result.points, result.points[1:]):
                self.assertEqual(date.fromisoformat(previous.end_date) + timedelta(days=1),
                                 date.fromisoformat(following.start_date))

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
        self.assertEqual(range_start(date(2026, 10, 1), "M"), date(2026, 9, 2))
        self.assertEqual(range_start(date(2026, 10, 1), "Y"), date(2025, 10, 2))
        self.assertEqual(range_start(date(2026, 10, 1), "6M"), date(2026, 4, 2))
        self.assertEqual(range_start(date(2026, 10, 1), "1Y"), date(2025, 10, 2))

    def test_connected_account_without_records_never_receives_demo_data(self):
        client = type("Client", (), {
            "get_sleep_trend_history": AsyncMock(return_value=[]),
            "get_main_sleep_timing_history": AsyncMock(return_value=[]),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            for metric in ("efficiency", "consistency"):
                response = TestClient(app).get(f"/api/sleep/{metric}?timeframe=1Y")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertFalse(data["is_mock"])
                self.assertIsNone(data["average_value"])
                self.assertEqual(data["recorded_nights"], 0)
                self.assertTrue(all(day["value"] is None for day in data["days"]))
            response = TestClient(app).get("/api/sleep/consistency/score?timeframe=Y")
            data = response.json()
            self.assertFalse(data["is_mock"])
            self.assertIsNone(data["latest_score"])
            self.assertEqual(data["scored_days"], 0)
            self.assertTrue(all(point["score"] is None for point in data["points"]))

    def test_new_score_endpoint_keeps_legacy_minutes_response(self):
        today = date(2026, 10, 2)
        records = [sleep_record(today - timedelta(days=offset)) for offset in range(7)]
        client = type("Client", (), {
            "get_main_sleep_timing_history": AsyncMock(return_value=records),
        })()
        with patch("main._get_token", new=AsyncMock(return_value="token")), patch("main.GoogleHealthClient", return_value=client):
            response = TestClient(app).get("/api/sleep/consistency/score?timeframe=W",
                                           headers={"X-User-Date": today.isoformat()})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["is_mock"])
        self.assertEqual(data["latest_score"], 100.0)
        self.assertEqual(data["latest_label"], "Optimal")
        self.assertEqual(data["scored_days"], 5)
        self.assertEqual(data["total_days"], 7)
        self.assertEqual(len(data["points"]), 7)
        previous_start = range_start(range_start(today, "W") - timedelta(days=1), "W")
        client.get_main_sleep_timing_history.assert_awaited_once_with(previous_start - timedelta(days=4), today)
        legacy = TestClient(app).get("/api/sleep/consistency?timeframe=W")
        self.assertEqual(legacy.status_code, 200)
        self.assertIn("days", legacy.json())
        self.assertNotIn("points", legacy.json())

    def test_score_endpoint_uses_week_month_six_month_and_year_ranges(self):
        today = date(2026, 10, 2)
        client = TestClient(app)
        for timeframe, points, days in (("W", 7, 7), ("M", 30, 30), ("6M", 27, 183), ("Y", 12, 365)):
            response = client.get(f"/api/sleep/consistency/score?timeframe={timeframe}",
                                  headers={"X-User-Date": today.isoformat()})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["timeframe"], timeframe)
            self.assertEqual(len(data["points"]), points)
            self.assertEqual(data["total_days"], days)

    def test_six_month_score_uses_contiguous_weekly_buckets_and_daily_weighted_average(self):
        end = date(2026, 10, 2)
        start = range_start(end, "6M")
        records = [sleep_record(end - timedelta(days=offset),
                                bedtime_minutes=100 if offset % 5 == 0 else 0,
                                wake_minutes=100 if offset % 5 == 0 else 0)
                   for offset in range(380) if offset % 11 != 0]
        result = build_consistency_scores(records, end, "6M", False)
        self.assertEqual(result.points[0].start_date, start.isoformat())
        self.assertEqual(result.points[-1].end_date, end.isoformat())
        self.assertEqual(sum(point.scored_days for point in result.points), result.scored_days)
        self.assertEqual(sum(result.band_counts.values()), result.scored_days)
        for point in result.points:
            self.assertLessEqual((date.fromisoformat(point.end_date) - date.fromisoformat(point.start_date)).days, 6)
        for previous, following in zip(result.points, result.points[1:]):
            self.assertEqual(date.fromisoformat(previous.end_date) + timedelta(days=1), date.fromisoformat(following.start_date))
        by_date = {r['date']: SleepNight(r['date'], r['bed_time'], r['wake_time']) for r in records}
        daily = [score_main_sleep(night, by_date).score for day, night in by_date.items() if start <= day <= end]
        scored = [value for value in daily if value is not None]
        self.assertEqual(result.average_score, round(sum(scored) / len(scored), 1))
        empty = build_consistency_scores([], end, "6M", False)
        self.assertTrue(all(point.score is None for point in empty.points))
        self.assertIsNone(empty.average_score)


if __name__ == "__main__":
    unittest.main()
