"""Contract and interval tests for the overnight BPM chart."""

import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from google_health_client import GoogleHealthClient, WEARABLES
from main import app
from mock_sleep_stage_ranges import mock_stage_points
from sleep_heart_rate import build_sleep_heart_rate, select_sleep, mock_sleep_heart_rate_points


DAY = date(2026, 9, 30)


def point():
    return {"name": "sleep-one", "dataSource": {"platform": "FITBIT"}, "sleep": {
        "interval": {"startTime": "2026-09-29T21:00:00Z", "endTime": "2026-09-30T05:00:00Z",
                     "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
        "metadata": {"mainSleep": True}}}


def reading(time="2026-09-30T00:00:00Z", bpm="57", offset="7200s"):
    return {"heartRate": {"sampleTime": {"physicalTime": time, "utcOffset": offset}, "beatsPerMinute": bpm}}


class SleepHeartRateTests(unittest.TestCase):
    def test_demo_has_today_completed_sleep_even_before_synthetic_wake_time(self):
        early = datetime.fromisoformat("2026-09-30T00:00:00+00:00")
        with patch("sleep_heart_rate.datetime") as clock:
            clock.now.return_value = early
            self.assertIsNone(select_sleep([point()], DAY))
            response = TestClient(app).get("/api/sleep/heart-rate", headers={"X-User-Date": DAY.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["night_date"], DAY.isoformat())
        self.assertGreater(len(response.json()["stage_intervals"]), 0)

    def test_stage_intervals_are_from_the_same_sleep_and_pending_stages_stay_absent(self):
        raw = mock_stage_points(DAY, 1)[0]
        data = build_sleep_heart_rate(raw, [], True)
        expected = raw["sleep"]["stages"]
        self.assertEqual(len(data["stage_intervals"]), len(expected))
        for actual, source in zip(data["stage_intervals"], expected):
            self.assertEqual(actual, {"stage": source["type"].lower(), "start": source["startTime"], "end": source["endTime"]})
        for state in ("pending", "classic", "invalid"):
            changed = deepcopy(raw)
            if state == "pending":
                changed["sleep"]["metadata"]["processed"] = False
            elif state == "classic":
                changed["sleep"]["type"] = "CLASSIC"
            else:
                changed["sleep"]["stages"][0]["endTime"] = changed["sleep"]["interval"]["endTime"]
            self.assertEqual(build_sleep_heart_rate(changed, [], True)["stage_intervals"], [])

    def test_interval_edges_numeric_strings_sorting_and_deduplication(self):
        raw = [reading(), reading(), reading("2026-09-29T21:00:00Z", "64"),
               reading("2026-09-29T20:59:59Z"), reading("2026-09-30T05:00:00Z"),
               reading(bpm="nan"), reading(bpm="0"), reading(bpm="301"), reading(bpm="57.5"),
               reading(time="2026-09-30T00:00:00"), {"heartRate": {}}]
        data = build_sleep_heart_rate(point(), raw, False)
        self.assertEqual([s["bpm"] for s in data["samples"]], [64, 57])
        self.assertEqual(data["samples"][1]["local_time"], "2026-09-30T02:00:00+02:00")
        self.assertEqual(data["start_local"], "2026-09-29T23:00:00+02:00")
        self.assertEqual(data["end_local"], "2026-09-30T07:00:00+02:00")
        self.assertFalse(data["is_mock"])

    def test_conflicting_duplicates_are_not_arbitrarily_selected(self):
        data = build_sleep_heart_rate(point(), [reading(), reading(bpm="90")], False)
        self.assertEqual(data["samples"], [])
        self.assertEqual(data["status"], "no_readings")

    def test_repeated_dst_clock_times_remain_distinct_physical_samples(self):
        sleep = point()
        sleep["sleep"]["interval"].update(startTime="2026-09-29T00:00:00Z", endTime="2026-09-29T03:00:00Z", endUtcOffset="3600s")
        data = build_sleep_heart_rate(sleep, [reading("2026-09-29T00:30:00Z", "55", "7200s"),
                                              reading("2026-09-29T01:30:00Z", "61", "3600s")], False)
        self.assertEqual(len(data["samples"]), 2)
        self.assertEqual(data["samples"][0]["local_time"][11:19], data["samples"][1]["local_time"][11:19])
        self.assertNotEqual(data["samples"][0]["timestamp"], data["samples"][1]["timestamp"])

    def test_main_selection_excludes_naps_future_and_other_platforms(self):
        main = point()
        extra = deepcopy(main)
        extra["name"] = "nap"
        extra["sleep"]["metadata"]["nap"] = True
        other = deepcopy(main)
        other["name"], other["dataSource"]["platform"] = "other", "APPLE"
        future = deepcopy(main)
        future["sleep"]["interval"]["endTime"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.assertEqual(select_sleep([extra, future, other, main], DAY), main)
        self.assertIsNone(select_sleep([main], DAY, "not-this-sleep"))
        unflagged = deepcopy(main)
        unflagged["sleep"]["metadata"] = {}
        unflagged["sleep"]["interval"]["startTime"] = "2026-09-29T20:00:00Z"
        self.assertEqual(select_sleep([unflagged, main], DAY), main)

    def test_google_query_uses_physical_boundaries_wearables_and_all_pages(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"dataPoints": [reading()], "nextPageToken": "next" if len(requests) == 1 else ""})
        transport = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("google_health_client.httpx.AsyncClient", return_value=transport):
            raw = asyncio.run(GoogleHealthClient("token").get_sleep_heart_rate_points(
                datetime.fromisoformat("2026-09-29T23:00:00+02:00"), datetime.fromisoformat("2026-09-30T07:00:00+02:00")))
        self.assertEqual(len(raw), 2)
        self.assertEqual(requests[0].url.path, "/v4/users/me/dataTypes/heart-rate/dataPoints:reconcile")
        self.assertEqual(requests[0].url.params["dataSourceFamily"], WEARABLES)
        self.assertEqual(requests[0].url.params["filter"], 'heart_rate.sample_time.physical_time >= "2026-09-29T21:00:00Z" AND heart_rate.sample_time.physical_time < "2026-09-30T05:00:00Z"')
        self.assertEqual(requests[1].url.params["pageToken"], "next")

    def test_demo_is_varied_repeatable_and_matches_stage_session_with_gap(self):
        raw = mock_stage_points(DAY, 1)[0]
        samples = mock_sleep_heart_rate_points(raw)
        self.assertEqual(samples, mock_sleep_heart_rate_points(raw))
        data = build_sleep_heart_rate(raw, samples, True)
        self.assertGreater(len({s["bpm"] for s in data["samples"]}), 20)
        times = [datetime.fromisoformat(s["timestamp"]) for s in data["samples"]]
        self.assertTrue(any(b - a > timedelta(minutes=10) for a, b in zip(times, times[1:])))
        client = TestClient(app)
        stages = client.get("/api/sleep/stages/typical-ranges", headers={"X-User-Date": DAY.isoformat()}).json()
        night = stages["nights"][-1]
        response = client.get("/api/sleep/heart-rate", params={"night_date": night["night_date"], "sleep_id": night["sleep_id"]}, headers={"X-User-Date": DAY.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["samples"], data["samples"])
        self.assertEqual(response.json()["sleep_id"], night["sleep_id"])

    def test_connected_and_missing_sleeps_never_fall_back_to_mock(self):
        source = type("Client", (), {"get_sleep_stage_points": AsyncMock(return_value=[point()]),
                                    "get_sleep_heart_rate_points": AsyncMock(return_value=[reading()])})()
        client = TestClient(app)
        with patch("main._get_token", new=AsyncMock(return_value="live")), patch("main.GoogleHealthClient", return_value=source):
            data = client.get("/api/sleep/heart-rate?night_date=2026-09-30&sleep_id=sleep-one", headers={"X-User-Date": DAY.isoformat()}).json()
            self.assertFalse(data["is_mock"])
            self.assertEqual(data["samples"][0]["bpm"], 57)
            self.assertEqual(source.get_sleep_stage_points.call_args.args, (DAY, DAY))
            missing = client.get("/api/sleep/heart-rate?night_date=2026-09-30&sleep_id=missing", headers={"X-User-Date": DAY.isoformat()}).json()
            self.assertEqual(missing["status"], "no_sleep")
            self.assertFalse(missing["is_mock"])
            self.assertEqual(source.get_sleep_heart_rate_points.await_count, 1)
        with patch("main.get_session", return_value={"expired": True}), patch("main._get_token", new=AsyncMock(return_value=None)):
            self.assertEqual(client.get("/api/sleep/heart-rate").status_code, 401)


if __name__ == "__main__":
    unittest.main()
