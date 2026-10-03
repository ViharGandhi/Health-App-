import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from math import log
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app
from mock_sleep_stress import _raw_night, mock_sleep_stress_history
from sleep_stress import (
    HrSample, HrvWindow, NightWindows, SleepNight, StageSegment, StressConfig,
    ValidWindow, adapt_google_hrv, adapt_google_sleep, build_baseline,
    prepare_night, score_night, summarize_nights,
)
from sleep_stress_store import SleepStressStore


UTC = timezone.utc
DAY = date(2026, 10, 3)


def make_night(day: date, readings: list[tuple[float, float, float]],
               gap_before: int = -1, sleep_type: str = "STAGES") -> NightWindows:
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), UTC).replace(hour=23)
    night = SleepNight(f"sleep-{day}", day, start, start + timedelta(hours=6), sleep_type,
                       (StageSegment(start, start + timedelta(hours=6),
                                     "ASLEEP" if sleep_type == "CLASSIC" else "LIGHT"),))
    windows = []
    cursor = start
    for index, (rmssd, hr, minutes) in enumerate(readings):
        if index == gap_before:
            cursor += timedelta(minutes=5)
        end = cursor + timedelta(minutes=minutes)
        windows.append(ValidWindow(cursor, end, "ASLEEP" if sleep_type == "CLASSIC" else "LIGHT",
                                   log(rmssd), hr, minutes))
        cursor = end
    return NightWindows(night, tuple(windows), sum(item[2] for item in readings), 1.0)


def baseline_history() -> list[NightWindows]:
    return [make_night(DAY - timedelta(days=index),
                       [(38 + index % 4, 58 + index % 5, 5)] * 5)
            for index in range(1, 8)]


class SleepStressTests(unittest.TestCase):
    def test_four_consecutive_joint_windows_count_twenty_minutes(self):
        current = make_night(DAY, [(20, 80, 5)] * 4)
        result = score_night(current, baseline_history())
        self.assertEqual(result["stressed_minutes"], 20)
        self.assertEqual(result["stress_pct"], 100)
        self.assertEqual(len(result["episodes"]), 1)
        self.assertEqual(result["baseline"]["nights_used"], 7)

    def test_hrv_alone_does_not_count_and_isolated_candidate_is_discarded(self):
        history = baseline_history()
        hrv_only = score_night(make_night(DAY, [(20, 60, 5)] * 4), history)
        self.assertEqual(hrv_only["stressed_minutes"], 0)
        self.assertEqual(hrv_only["hrv_only_minutes"], 20)
        isolated = score_night(make_night(DAY, [(20, 80, 5), (40, 60, 5), (40, 60, 5)]), history)
        self.assertEqual(isolated["stressed_minutes"], 0)

    def test_awake_gap_breaks_persistence_run(self):
        current = make_night(DAY, [(20, 80, 5)] * 4, gap_before=2)
        config = StressConfig(min_consecutive_windows=3)
        result = score_night(current, baseline_history(), config)
        self.assertEqual(result["stressed_minutes"], 0)
        self.assertEqual(result["episodes"], [])

    def test_unequal_window_lengths_are_time_weighted(self):
        current = make_night(DAY, [(20, 80, 4), (20, 80, 6), (40, 60, 5)])
        result = score_night(current, baseline_history())
        self.assertEqual(result["stressed_minutes"], 10)
        self.assertAlmostEqual(result["stress_pct"], 100 * 10 / 15, places=2)
        self.assertEqual(result["episodes"][0]["minutes"], 10)

    def test_stage_majority_awakenings_and_hr_spike_filter(self):
        start = datetime(2026, 10, 2, 23, tzinfo=UTC)
        stages = (StageSegment(start, start + timedelta(minutes=7), "LIGHT"),
                  StageSegment(start + timedelta(minutes=7), start + timedelta(minutes=10), "REM"))
        night = SleepNight("stage", DAY, start, start + timedelta(minutes=10), "STAGES", stages)
        hr = [HrSample(start + timedelta(seconds=30 * index), 200 if index == 4 else 60)
              for index in range(20)]
        window = HrvWindow(start, start + timedelta(minutes=10), 40)
        config = StressConfig(min_sleep_hours=0)
        valid = prepare_night(night, [window], hr, config)
        self.assertEqual(len(valid.windows), 1)
        self.assertEqual(valid.windows[0].stage, "LIGHT")
        self.assertEqual(valid.windows[0].hr, 60)
        split = SleepNight("split", DAY, start, start + timedelta(minutes=10), "STAGES",
                           (StageSegment(start, start + timedelta(minutes=6), "LIGHT"),
                            StageSegment(start + timedelta(minutes=6), start + timedelta(minutes=10), "REM")))
        self.assertEqual(prepare_night(split, [window], hr, config).windows, ())
        awakened = SleepNight("awake", DAY, start, start + timedelta(minutes=10), "STAGES", stages,
                              ((start + timedelta(minutes=2), start + timedelta(minutes=3)),))
        self.assertEqual(prepare_night(awakened, [window], hr, config).windows, ())

    def test_low_coverage_hr_samples_drop_window(self):
        start = datetime(2026, 10, 2, 23, tzinfo=UTC)
        night = SleepNight("sparse", DAY, start, start + timedelta(minutes=5), "STAGES",
                           (StageSegment(start, start + timedelta(minutes=5), "LIGHT"),))
        hr = [HrSample(start + timedelta(seconds=30 * index), 60) for index in range(10)]
        hr[4] = HrSample(hr[4].time_utc, 200)
        hr[5] = HrSample(hr[5].time_utc, 200)
        hr[6] = HrSample(hr[6].time_utc, 200)
        hr[7] = HrSample(hr[7].time_utc, 200)
        hr[8] = HrSample(hr[8].time_utc, 200)
        self.assertEqual(prepare_night(night, [HrvWindow(start, start + timedelta(minutes=5), 40)],
                                       hr, StressConfig(min_sleep_hours=0)).windows, ())

    def test_stage_fallback_spread_floor_and_excludes_current(self):
        current = make_night(DAY, [(20, 80, 5)] * 4)
        history = baseline_history()
        stages, count, fallback = build_baseline(current, history + [current])
        self.assertEqual(count, 7)
        self.assertTrue(fallback)
        self.assertTrue(stages["DEEP"].fallback)
        constant = [make_night(DAY - timedelta(days=index), [(40, 60, 5)] * 5)
                    for index in range(1, 8)]
        floors, _, _ = build_baseline(current, constant, StressConfig(baseline_min_windows_per_stage=1))
        self.assertEqual(floors["LIGHT"].ln_hrv_spread, 0.02)
        self.assertEqual(floors["LIGHT"].hr_spread, 0.5)

    def test_insufficient_baseline_and_classic_confidence_cap(self):
        current = make_night(DAY, [(20, 80, 5)] * 4)
        self.assertEqual(score_night(current, baseline_history()[:6])["status"], "insufficient_baseline")
        classic = make_night(DAY, [(20, 80, 5)] * 4, sleep_type="CLASSIC")
        result = score_night(classic, baseline_history())
        self.assertEqual(result["confidence"], "medium")
        self.assertTrue(result["type_fallback"])

    def test_two_sessions_report_main_and_total_without_baseline_contamination(self):
        main = make_night(DAY, [(20, 80, 5)] * 2)
        second = replace(main, night=replace(main.night, sleep_id="second", main_sleep=False))
        history = baseline_history()
        results = [score_night(item, history) for item in (main, second)]
        total = summarize_nights(results)[0]
        self.assertEqual(total["main_sleep_id"], main.night.sleep_id)
        self.assertEqual(total["sessions"], 2)
        self.assertEqual(total["stressed_minutes"], 20)
        earlier_second = replace(history[0], night=replace(history[0].night,
                                 sleep_id="earlier-second", main_sleep=False))
        _, nights_used, _ = build_baseline(main, history + [earlier_second])
        self.assertEqual(nights_used, 7)

    def test_adapter_uses_rmssd_and_infers_non_fixed_cadence(self):
        point = {"name": "sleep-1", "sleep": {
            "interval": {"startTime": "2026-10-02T23:00:00Z", "endTime": "2026-10-03T05:00:00Z",
                         "endUtcOffset": "7200s"}, "type": "STAGES",
            "metadata": {"processed": True, "stagesStatus": "SUCCEEDED", "mainSleep": True},
            "stages": [{"startTime": "2026-10-02T23:00:00Z", "endTime": "2026-10-03T05:00:00Z",
                        "type": "LIGHT"}], "shortAwakenings": []}}
        sleep = adapt_google_sleep(point)
        self.assertEqual(sleep.night_date, DAY)
        points = [{"heartRateVariability": {"sampleTime": {"physicalTime": f"2026-10-02T23:{minute:02}:00Z"},
                                           "rootMeanSquareOfSuccessiveDifferencesMilliseconds": 35,
                                           "standardDeviationMilliseconds": 90}}
                  for minute in (0, 4, 10)]
        windows = adapt_google_hrv(points, "start")
        self.assertEqual([window.rmssd_ms for window in windows], [35] * 3)
        self.assertEqual([(window.end_utc - window.start_utc).total_seconds() / 60
                          for window in windows], [4, 6, 5])
        gap_points = [{"heartRateVariability": {"sampleTime": {"physicalTime":
                      f"2026-10-02T23:{minute:02}:00Z"},
                      "rootMeanSquareOfSuccessiveDifferencesMilliseconds": 35}}
                      for minute in (0, 5, 10, 20)]
        self.assertEqual([window.start_utc.minute for window in adapt_google_hrv(gap_points, "start")],
                         [0, 5, 20])
        with self.assertRaises(ValueError):
            adapt_google_hrv(points, "guess")

    def test_store_upsert_is_idempotent(self):
        current = make_night(DAY, [(20, 80, 5)] * 4)
        result = score_night(current, baseline_history())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stress.sqlite3"
            store = SleepStressStore(path)
            store.upsert(result, current)
            store.upsert(result, current)
            self.assertEqual(store.get(result["sleep_id"]), result)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM sleep_stress").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM sleep_stress_windows").fetchone()[0], 4)

    def test_mock_history_is_stable_and_mixed(self):
        results = mock_sleep_stress_history(DAY, 14)
        self.assertEqual(results, mock_sleep_stress_history(DAY, 14))
        stressed = [result["stressed_minutes"] for result in results]
        self.assertGreaterEqual(len(set(stressed)), 5)
        self.assertEqual(min(stressed), 0)
        self.assertGreaterEqual(max(stressed), 30)
        self.assertTrue(all(result["status"] == "ok" for result in results))

    def test_api_mock_and_connected_alignment_gate(self):
        client = TestClient(app)
        response = client.get("/api/sleep/stress?days=14", headers={"X-User-Date": DAY.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_mock"])
        self.assertEqual(len(response.json()["nights"]), 14)
        self.assertEqual(len(response.json()["totals"]), 14)
        with patch("main._get_token", new=AsyncMock(return_value="connected")), \
             patch.dict("main.os.environ", {"SLEEP_STRESS_HRV_ANCHOR": ""}):
            connected = client.get("/api/sleep/stress")
        self.assertEqual(connected.status_code, 503)
        with patch("main.get_session", return_value={"access_token": "expired"}), \
             patch("main._get_token", new=AsyncMock(return_value=None)):
            expired = client.get("/api/sleep/stress")
        self.assertEqual(expired.status_code, 401)

    def test_six_month_range_returns_mixed_daily_history(self):
        response = TestClient(app).get("/api/sleep/stress?timeframe=6M",
                                       headers={"X-User-Date": DAY.isoformat()})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["range_start"], "2026-04-04")
        self.assertEqual(data["range_end"], DAY.isoformat())
        self.assertEqual(len(data["nights"]), 183)
        self.assertGreaterEqual(len(set(item["stressed_minutes"] for item in data["nights"])), 5)

    def test_connected_pipeline_with_google_shaped_mock_points(self):
        sleep_points, hrv_points, hr_points = [], [], []
        for offset in range(14, -1, -1):
            sleep, hrv, hr = _raw_night(DAY - timedelta(days=offset))
            sleep_points.append(sleep)
            hrv_points.extend(hrv)
            hr_points.extend(hr)
        source = type("Source", (), {
            "get_sleep_stress_points": AsyncMock(return_value=(sleep_points, hrv_points, hr_points)),
        })()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.sqlite3"
            with patch("main._get_token", new=AsyncMock(return_value="connected")), \
                 patch("main.GoogleHealthClient", return_value=source), \
                 patch.dict("main.os.environ", {
                     "SLEEP_STRESS_HRV_ANCHOR": "start", "SLEEP_STRESS_DB_PATH": str(path)}):
                response = TestClient(app).get("/api/sleep/stress?days=1",
                                               headers={"X-User-Date": DAY.isoformat()})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["is_mock"])
            self.assertEqual(len(data["nights"]), 1)
            self.assertEqual(data["nights"][0]["status"], "ok")
            self.assertEqual(SleepStressStore(path).get(data["nights"][0]["sleep_id"]), data["nights"][0])


if __name__ == "__main__":
    unittest.main()
