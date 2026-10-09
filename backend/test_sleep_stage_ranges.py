import asyncio
import base64
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import httpx
import tink
from tink import signature

from main import app
from google_health_client import GoogleHealthClient
from mock_sleep_stage_ranges import mock_stage_points, mock_stage_ranges
from sleep_stage_ranges import (
    STAGES, StageRangeConfig, StageSegment, SleepNight, adapt_google_sleep, stage_stats,
    personal_ranges, score_stages,
)
from sleep_stage_store import SleepStageStore
from sleep_stage_pipeline import sync_stage_ranges, run_stage_jobs
from sleep_stage_webhooks import enqueue_sleep_notifications, verify_notification


DAY = date(2026, 9, 30)


def night(day, amounts=(30, 240, 90, 120), **overrides):
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=22)
    cursor, segments = start, []
    for stage, amount in zip(STAGES, amounts):
        if amount:
            end = cursor + timedelta(minutes=amount)
            segments.append(StageSegment(cursor, end, stage))
            cursor = end
    return replace(SleepNight(f"sleep-{day}", day, start, cursor, "STAGES", "SUCCEEDED", True,
                              tuple(segments), main_sleep=True), **overrides)


def stats(day, amounts=(30, 240, 90, 120), config=StageRangeConfig()):
    result, state = stage_stats(night(day, amounts), config)
    assert state == "ok"
    return result


def raw(n):
    return {"name": n.sleep_id, "dataSource": {"platform": "FITBIT"}, "sleep": {
        "interval": {"startTime": n.start_utc.isoformat(), "endTime": n.end_utc.isoformat(),
                     "startUtcOffset": "7200s", "endUtcOffset": "7200s"}, "type": n.type,
        "metadata": {"processed": n.processed, "stagesStatus": n.stages_status,
                     "mainSleep": n.main_sleep, "nap": n.nap},
        "stages": [{"startTime": s.start_utc.isoformat(), "endTime": s.end_utc.isoformat(), "type": s.stage.upper()}
                   for s in n.segments],
    }}


class StageRangeTests(unittest.TestCase):
    def test_worked_example_and_centers(self):
        history = [stats(DAY - timedelta(days=4-i), (total-light-180, light, 90, 90))
                   for i, (light, total) in enumerate(zip((270, 258, 300, 282), (540, 600, 660, 600)))]
        bands, _ = personal_ranges(stats(DAY), history)
        self.assertAlmostEqual(bands["light"]["center"], 46.25)
        self.assertAlmostEqual(bands["light"]["spread"], 2.9652)
        self.assertAlmostEqual(bands["light"]["low"], 43.2848)
        self.assertAlmostEqual(bands["light"]["high"], 49.2152)
        self.assertAlmostEqual(sum(bands[s]["center"] for s in STAGES), 100)

    def test_floor_and_one_extreme_night(self):
        history = [stats(DAY - timedelta(days=i)) for i in range(1, 8)]
        current = stats(DAY)
        baseline, _ = personal_ranges(current, history)
        history[0] = stats(DAY - timedelta(days=1), (10, 400, 10, 60))
        outlier, _ = personal_ranges(current, history)
        self.assertEqual(outlier["light"]["spread"], baseline["light"]["spread"])
        self.assertEqual(baseline["light"]["spread"], 1)
        self.assertEqual(baseline["light"]["high"] - baseline["light"]["low"], 2)
        self.assertNotEqual(outlier["light"]["center"], baseline["light"]["center"])

    def test_excludes_current_and_uses_qualifying_nights_across_gaps(self):
        history = [stats(DAY - timedelta(days=i * 4)) for i in range(1, 11)] + [stats(DAY), stats(DAY + timedelta(days=1))]
        bands, used = personal_ranges(stats(DAY), history)
        self.assertEqual(len(used), 7)
        self.assertEqual(used[0].night_date, DAY - timedelta(days=28))
        self.assertTrue(all(n.night_date < DAY for n in used))

    def test_configurable_window_and_building_baseline(self):
        current = stats(DAY)
        history = [stats(DAY - timedelta(days=i)) for i in range(1, 4)]
        result = score_stages(current, history)
        self.assertEqual(result["status"], "building_baseline")
        self.assertEqual(result["nights_available"], 3)
        self.assertIsNone(result["stages"]["light"]["range"])
        self.assertIsNone(result["stages"]["light"]["source"])
        result = score_stages(current, history, StageRangeConfig(window_nights=3, min_nights=2))
        self.assertEqual(result["nights_used"], 3)

    def test_naps_classic_pending_short_and_bad_segments(self):
        for item, expected in (
            (night(DAY, nap=True), "nap_excluded"),
            (night(DAY, type="CLASSIC"), "stage_breakdown_unavailable"),
            (night(DAY, processed=False), "stages_pending"),
            (night(DAY, stages_status="REJECTED_COVERAGE"), "stages_unavailable"),
            (night(DAY, (5, 100, 10, 20)), "short_sleep_excluded"),
        ):
            self.assertEqual(stage_stats(item), (None, expected))
        n = night(DAY)
        overlapping = replace(n.segments[1], start_utc=n.start_utc)
        self.assertEqual(stage_stats(replace(n, segments=(n.segments[0], overlapping, *n.segments[2:])))[1], "invalid_stage_partition")
        self.assertEqual(stage_stats(replace(n, segments=n.segments[:-1]))[1], "invalid_stage_partition")
        self.assertEqual(stage_stats(replace(n, segments=()))[1], "invalid_stage_partition")

    def test_short_awakenings_ignored_and_zeros_valid(self):
        p = raw(night(DAY, (30, 300, 0, 150)))
        original = stage_stats(adapt_google_sleep(p))[0]
        p["sleep"]["shortAwakenings"] = [{"startTime": p["sleep"]["interval"]["startTime"],
                                             "endTime": p["sleep"]["interval"]["endTime"], "type": "AWAKE"}]
        self.assertEqual(stage_stats(adapt_google_sleep(p))[0], original)
        self.assertEqual(original.pct["deep"], 0)

    def test_denominator_and_restorative_own_spread(self):
        cfg = StageRangeConfig(denominator="time_asleep")
        history = [stats(DAY - timedelta(days=i), (30, 240, 40+10*i, 170-10*i), cfg) for i in range(1, 8)]
        current = stats(DAY, config=cfg)
        result = score_stages(current, history, cfg)
        self.assertIsNone(result["stages"]["awake"]["pct"])
        self.assertIsNone(result["stages"]["awake"]["range"])
        self.assertEqual(result["stages"]["awake"]["minutes"], 30)
        bands, _ = personal_ranges(current, history, cfg)
        self.assertEqual(bands["restorative"]["spread"], 1)
        self.assertGreater(bands["deep"]["spread"] + bands["rem"]["spread"], 1)
        self.assertNotEqual(current.pct["light"], stats(DAY).pct["light"])
        with self.assertRaises(ValueError):
            score_stages(current, [stats(DAY-timedelta(days=1))], cfg)

    def test_neutral_status_delta_and_range_minutes(self):
        history = [stats(DAY - timedelta(days=i)) for i in range(1, 8)]
        result = score_stages(stats(DAY, (30, 270, 70, 110)), history)
        light = result["stages"]["light"]
        self.assertEqual(light["status"], "above")
        self.assertAlmostEqual(light["delta_vs_center_pct"], 6.25)
        self.assertAlmostEqual(light["range_minutes"]["low"], 235.2)
        self.assertEqual(result["reliability"], "ok")
        self.assertTrue(result["range_is_provisional"])
        self.assertEqual(score_stages(stats(DAY), history[:5])["reliability"], "low")

    def test_historical_offset_and_dst_actual_duration(self):
        p = raw(night(DAY))
        p["sleep"]["interval"]["endUtcOffset"] = "-28800s"
        adapted = adapt_google_sleep(p)
        self.assertEqual(adapted.night_date, DAY - timedelta(days=1))
        self.assertEqual(stage_stats(adapted)[0].total_minutes, 480)
        p["sleep"]["interval"]["startTime"] = "2026-10-25T01:00:00+02:00"
        p["sleep"]["interval"]["endTime"] = "2026-10-25T04:00:00+01:00"
        p["sleep"]["interval"]["endUtcOffset"] = "3600s"
        p["sleep"]["stages"] = [{"startTime": p["sleep"]["interval"]["startTime"],
                                    "endTime": p["sleep"]["interval"]["endTime"], "type": "LIGHT"}]
        self.assertEqual(stage_stats(adapt_google_sleep(p))[0].total_minutes, 240)


class StageStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SleepStageStore(Path(self.directory.name) / "ranges.sqlite3")

    def observations(self):
        return [(n, *stage_stats(n)) for n in [night(DAY-timedelta(days=i)) for i in range(8)]]

    def test_idempotence_user_isolation_and_correction_cascades(self):
        obs = self.observations()
        self.store.sync("alice", obs, None, DAY)
        before = self.store.results("alice", DAY, DAY)
        self.store.sync("alice", obs, None, DAY)
        self.assertEqual(before, self.store.results("alice", DAY, DAY))
        self.assertEqual(self.store.results("bob", DAY, DAY), [])
        changed = night(DAY-timedelta(days=1), (30, 300, 30, 120))
        self.store.sync("alice", [(changed, *stage_stats(changed))], changed.night_date, changed.night_date)
        after = self.store.results("alice", DAY, DAY)
        self.assertNotEqual(before[0]["stages"]["light"]["range"]["center"], after[0]["stages"]["light"]["range"]["center"])
        # A deletion also replaces a baseline night rather than counting it as zero.
        self.store.sync("alice", [], changed.night_date, changed.night_date)
        self.assertEqual(self.store.results("alice", DAY, DAY)[0]["nights_used"], 6)

    def test_longest_main_per_date_and_classic_excluded(self):
        obs = self.observations()
        extra = night(DAY, (30, 300, 90, 120), sleep_id="longest", main_sleep=None)
        obs[0] = (replace(obs[0][0], main_sleep=None), obs[0][1], obs[0][2])
        obs.append((extra, *stage_stats(extra)))
        classic = night(DAY-timedelta(days=1), type="CLASSIC")
        obs[1] = (classic, *stage_stats(classic))
        nap = night(DAY, (0, 30, 0, 0), sleep_id="nap", nap=True)
        obs.append((nap, *stage_stats(nap)))
        self.store.sync("alice", obs, None, DAY)
        result = self.store.results("alice", DAY, DAY)[0]
        self.assertEqual(result["sleep_id"], "longest")
        self.assertEqual(result["nights_used"], 6)
        self.assertEqual(self.store.results("alice", classic.night_date, classic.night_date)[0]["status"], "stage_breakdown_unavailable")

    def test_denominator_change_from_stored_minutes(self):
        self.store.sync("alice", self.observations(), None, DAY)
        self.store.sync("alice", [], DAY+timedelta(days=1), DAY+timedelta(days=1), StageRangeConfig(denominator="time_asleep"))
        result = self.store.results("alice", DAY, DAY)[0]
        self.assertIsNone(result["stages"]["awake"]["pct"])
        self.assertAlmostEqual(result["stages"]["light"]["range"]["center"], 100*240/450)

    def test_notification_queue_deduplicates_and_keeps_update_during_worker(self):
        payload = {"data": {"healthUserId": "alice", "dataType": "sleep", "operation": "UPSERT", "recordId": "sleep-1",
                            "intervals": [{"civilIso8601TimeInterval": {"startTime": "2026-09-29T22:00:00", "endTime": "2026-09-30T06:00:00"}}]}}
        enqueue_sleep_notifications([payload, payload], self.store)
        jobs = self.store.jobs("alice")
        self.assertEqual(len(jobs), 1)
        key, _, _, revision = jobs[0]
        enqueue_sleep_notifications(payload, self.store)
        self.store.finish_job("alice", key, revision)
        self.assertEqual(len(self.store.jobs("alice")), 1)
        self.store.finish_job("alice", key, self.store.jobs("alice")[0][3])
        self.assertEqual(self.store.jobs("alice"), [])

    def test_pipeline_fetches_all_history_then_ten_day_backfill_and_retries_pending(self):
        points = [raw(n) for n, _, _ in self.observations()]
        client = type("Client", (), {"get_sleep_stage_points": AsyncMock(return_value=points)})()
        result = asyncio.run(sync_stage_ranges(client, "alice", self.store, DAY, DAY))
        self.assertEqual(result[0]["nights_used"], 7)
        self.assertIsNone(client.get_sleep_stage_points.call_args.args[0])
        points[0]["sleep"]["metadata"]["processed"] = False
        self.store.enqueue("alice", "pending", DAY, DAY)
        asyncio.run(run_stage_jobs(client, "alice", self.store))
        self.assertEqual(client.get_sleep_stage_points.call_args.args[0], DAY-timedelta(days=9))
        self.assertEqual(self.store.results("alice", DAY, DAY)[0]["status"], "stages_pending")
        with closing(sqlite3.connect(self.store.path)) as conn:
            self.assertEqual(conn.execute("SELECT attempts FROM sleep_stage_jobs").fetchone()[0], 1)


class StageApiTests(unittest.TestCase):
    def test_pagination_list_without_unsupported_sleep_source_family(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"dataPoints": [{"name": "first" if len(requests)==1 else "second"}],
                                             "nextPageToken": "next" if len(requests)==1 else ""})
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("google_health_client.httpx.AsyncClient", return_value=client):
            data = asyncio.run(GoogleHealthClient("secret").get_sleep_stage_points(None, DAY))
        self.assertEqual(len(data), 2)
        self.assertEqual(requests[0].url.path, "/v4/users/me/dataTypes/sleep/dataPoints")
        self.assertNotIn("dataSourceFamily", requests[0].url.params)
        self.assertEqual(requests[1].url.params["pageToken"], "next")

    def test_mixed_mock_endpoint_and_expired_token(self):
        data = TestClient(app).get("/api/sleep/stages/typical-ranges?days=30", headers={"X-User-Date": DAY.isoformat()}).json()
        self.assertTrue(data["is_mock"])
        self.assertLess(len(data["nights"]), 30)
        scored = [n for n in data["nights"] if n["status"] == "ok"]
        self.assertGreater(len({n["stages"]["light"]["pct"] for n in scored}), 10)
        self.assertIn("stage_breakdown_unavailable", {n["status"] for n in data["nights"]})
        self.assertEqual(mock_stage_ranges(DAY, 30), mock_stage_ranges(DAY, 30))
        with patch("main.get_session", return_value={"expired": True}), patch("main._get_token", new=AsyncMock(return_value=None)):
            self.assertEqual(TestClient(app).get("/api/sleep/stages/typical-ranges").status_code, 401)

    def test_connected_endpoint_uses_scoped_store_and_real_adapter(self):
        points = [raw(night(DAY-timedelta(days=i))) for i in range(8)]
        source = type("Client", (), {"get_sleep_stage_points": AsyncMock(return_value=points),
                                     "account_key": "alice",
                                     "get_health_user_id": AsyncMock(return_value="alice")})()
        with tempfile.TemporaryDirectory() as directory:
            store = SleepStageStore(Path(directory)/"connected.sqlite3")
            with patch("main._get_token", new=AsyncMock(return_value="connected")), \
                 patch("main.GoogleHealthClient", return_value=source), patch("main.stage_store", return_value=store):
                response = TestClient(app).get("/api/sleep/stages/typical-ranges?days=1", headers={"X-User-Date": DAY.isoformat()})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["is_mock"])
            self.assertEqual(data["nights"][0]["nights_used"], 7)
            self.assertEqual(store.results("bob", DAY, DAY), [])

    def test_signature_verification_and_tampering(self):
        signature.register()
        private = tink.new_keyset_handle(signature.signature_key_templates.ECDSA_P256)
        body = b'{"data":{"dataType":"sleep"}}'
        sig = private.primitive(signature.PublicKeySign).sign(body)
        verifier = private.public_keyset_handle().primitive(signature.PublicKeyVerify)
        with patch("sleep_stage_webhooks._verifier", verifier), patch("sleep_stage_webhooks._keyset_loaded_at", time.monotonic()):
            asyncio.run(verify_notification(body, base64.b64encode(sig).decode()))
        keys = tink.json_proto_keyset_format.serialize_without_secret(private.public_keyset_handle())
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=keys)))
        with patch("sleep_stage_webhooks._verifier", None), patch("sleep_stage_webhooks.httpx.AsyncClient", return_value=client):
            asyncio.run(verify_notification(body, base64.b64encode(sig).decode()))
        # Both attempts see the same trusted verifier; altered bytes fail.
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=keys)))
        with patch("sleep_stage_webhooks._verifier", verifier), patch("sleep_stage_webhooks._keyset_loaded_at", time.monotonic()), \
             patch("sleep_stage_webhooks.httpx.AsyncClient", return_value=client):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as error:
                asyncio.run(verify_notification(body+b" ", base64.b64encode(sig).decode()))
            self.assertEqual(error.exception.status_code, 401)

    def test_webhook_handshake_authentication_and_queue(self):
        client = TestClient(app)
        with patch.dict("os.environ", {"GOOGLE_HEALTH_WEBHOOK_AUTHORIZATION": "Bearer test-secret"}):
            path = "/api/webhooks/google-health/sleep-stages"
            self.assertEqual(client.post(path, json={"type": "verification"}).status_code, 401)
            auth = {"Authorization": "Bearer test-secret"}
            self.assertEqual(client.post(path, json={"type": "verification"}, headers=auth).status_code, 200)
            self.assertEqual(client.post(path, json={"data": {}}, headers=auth).status_code, 401)
            payload = {"data": {"healthUserId": "alice", "dataType": "sleep", "operation": "UPSERT", "recordId": "sleep-1",
                                "intervals": [{"civilIso8601TimeInterval": {"startTime": "2026-09-29T22:00:00", "endTime": "2026-09-30T06:00:00"}}]}}
            with tempfile.TemporaryDirectory() as directory, patch("sleep_stage_webhooks.verify_notification", new=AsyncMock()):
                store = SleepStageStore(Path(directory)/"queue.sqlite3")
                with patch("sleep_stage_webhooks.stage_store", return_value=store):
                    response = client.post(path, json=payload, headers={**auth, "GOOGLE-HEALTH-API-SIGNATURE": "test"})
                self.assertEqual(response.status_code, 204)
                self.assertEqual(len(store.jobs("alice")), 1)


if __name__ == "__main__":
    unittest.main()
