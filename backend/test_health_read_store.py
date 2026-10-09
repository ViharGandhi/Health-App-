import asyncio
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import google_health_client as google
from health_read_store import HealthReadStore, ReadRange, read_range, point_clock, CacheInvalidated

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc).timestamp()
FIELD = 'daily_heart_rate_variability.date'
KIND = 'daily-heart-rate-variability'


def query(start='2026-10-01', end='2026-10-08'):
    return read_range(f'{FIELD} >= "{start}" AND {FIELD} < "{end}"')


def point(day, value=40):
    return {'dailyHeartRateVariability': {'date': {'year': 2026, 'month': 10, 'day': day},
            'averageHeartRateVariabilityMilliseconds': value}}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'health.sqlite3'
        self.store = HealthReadStore(self.path)

    def test_restart_subset_and_account_isolation(self):
        self.store.range_write('a', KIND, query(), True, [point(1), point(5)], now=NOW)
        reopened = HealthReadStore(self.path)
        points, missing = reopened.range_read('a', KIND, query('2026-10-05', '2026-10-06'), True, now=NOW)
        self.assertEqual(points, [point(5)])
        self.assertEqual(missing, [])
        self.assertEqual(reopened.range_read('b', KIND, query(), True, now=NOW)[0], [])
        self.assertTrue(reopened.range_read('b', KIND, query(), True, now=NOW)[1])
        self.assertTrue(reopened.range_read('a', KIND, query(), False, now=NOW)[1])

    def test_indexed_reads_do_not_reparse_all_observation_times(self):
        self.store.range_write('a', KIND, query(), True, [point(1), point(5)], now=NOW)
        with patch('health_read_store.point_clock', side_effect=AssertionError('full snapshot scan')):
            points, missing = self.store.range_read('a', KIND, query('2026-10-05', '2026-10-06'), True, now=NOW)
        self.assertEqual(points, [point(5)])
        self.assertFalse(missing)

    def test_existing_snapshot_is_migrated_to_index_on_restart(self):
        import json
        with self.store.connection() as conn, conn:
            conn.execute('INSERT INTO read_slices VALUES (?,?,?,?,?,?,?,?,?)',
                         ('a', KIND, FIELD, True, query().start, query().end, NOW, json.dumps([point(5)]), 0))
        reopened = HealthReadStore(self.path)
        self.assertEqual(reopened.range_read('a', KIND, query(), True, now=NOW)[0], [point(5)])

    def test_only_recent_slice_expires_after_fifteen_minutes(self):
        self.store.range_write('a', KIND, query(), True, [point(1), point(7)], now=NOW)
        points, missing = self.store.range_read('a', KIND, query(), True, now=NOW + 901)
        self.assertEqual(points, [point(1)])
        self.assertEqual(missing, [(query('2026-10-04', '2026-10-08').start, query().end)])

    def test_new_empty_slice_removes_old_readings_and_preserves_neighbors(self):
        self.store.range_write('a', KIND, query(), True, [point(5), point(6)], now=NOW)
        self.store.range_write('a', KIND, query('2026-10-05', '2026-10-06'), True, [], now=NOW + 1)
        points, missing = self.store.range_read('a', KIND, query(), True, now=NOW + 2)
        self.assertEqual(points, [point(6)])
        self.assertFalse(missing)

    def test_new_corrected_slice_replaces_value_without_duplicate(self):
        self.store.range_write('a', KIND, query(), True, [point(5)], now=NOW)
        self.store.range_write('a', KIND, query('2026-10-05', '2026-10-06'), True, [point(5, 70)], now=NOW + 1)
        self.assertEqual(self.store.range_read('a', KIND, query(), True, now=NOW + 2)[0], [point(5, 70)])

    def test_union_coverage_fetches_only_the_gap(self):
        self.store.range_write('a', KIND, query('2026-10-01', '2026-10-03'), True, [], now=NOW)
        self.store.range_write('a', KIND, query('2026-10-05', '2026-10-08'), True, [], now=NOW)
        missing = self.store.range_read('a', KIND, query(), True, now=NOW)[1]
        gap = query('2026-10-03', '2026-10-05')
        self.assertEqual(missing, [(gap.start, gap.end)])

    def test_unknown_schema_does_not_claim_empty_coverage(self):
        self.assertFalse(self.store.range_write('a', KIND, query(), True, [{'unknown': 5}], now=NOW))
        self.assertTrue(self.store.range_read('a', KIND, query(), True, now=NOW)[1])

    def test_refresh_blocks_inflight_old_writes(self):
        epoch = self.store.epoch('a')
        self.store.expire_recent('a')
        with self.assertRaises(CacheInvalidated):
            self.store.range_write('a', KIND, query(), True, [], epoch=epoch)
        with self.assertRaises(CacheInvalidated):
            self.store.exact_write('a', 'steps', {}, epoch=epoch)

    def test_civil_times_use_offsets_and_physical_bounds_keep_z(self):
        sleep = {'sleep': {'interval': {'endTime': '2026-10-06T23:00:00Z', 'endUtcOffset': '19800s'}}}
        self.assertEqual(point_clock(sleep, 'sleep.interval.civil_end_time'), '2026-10-07T04:30:00.000000')
        physical = read_range('heart_rate.sample_time.physical_time >= "2026-10-06T23:00:00Z" AND heart_rate.sample_time.physical_time < "2026-10-07T00:00:00Z"')
        self.assertIn('00.000000Z"', physical.expression(physical.start, physical.end))
        self.assertIn('"2026-10-01"', query().expression(query().start, query().end))


class StoredClientTests(unittest.TestCase):
    def setUp(self):
        StoreTests.setUp(self)
        google._point_cache.clear()
        google._point_requests.clear()
        google._request_lanes.clear()
        google._range_locks.clear()

    def test_token_rotation_and_memory_restart_reuse_database(self):
        async def check():
            first = google.GoogleHealthClient('token-one', cache=True, account_id='same-account', store=self.store)
            first._fetch_points = AsyncMock(return_value=[point(5)])
            await first._points(KIND, query().expression(query().start, query().end))
            google._point_cache.clear()
            second = google.GoogleHealthClient('token-two', cache=True, account_id='same-account', store=self.store)
            second._fetch_points = AsyncMock(side_effect=AssertionError('unnecessary Google read'))
            self.assertEqual(await second._points(KIND, query('2026-10-05', '2026-10-06').expression(query('2026-10-05', '2026-10-06').start, query('2026-10-05', '2026-10-06').end)), [point(5)])
        asyncio.run(check())

    def test_overlapping_simultaneous_requests_share_one_download(self):
        async def check():
            client = google.GoogleHealthClient('token', cache=True, account_id='account', store=self.store)
            client._fetch_points = AsyncMock(return_value=[point(5)])
            broad, narrow = query(), query('2026-10-05', '2026-10-06')
            values = await asyncio.gather(client._points(KIND, broad.expression(broad.start, broad.end)),
                                          client._points(KIND, narrow.expression(narrow.start, narrow.end)))
            self.assertEqual(values, [[point(5)], [point(5)]])
            # Either request can acquire the stream lock first. A narrow-first
            # read may leave two gaps, but no downloaded intervals may overlap.
            ranges = sorted((read_range(call.args[1]).start, read_range(call.args[1]).end)
                            for call in client._fetch_points.await_args_list)
            self.assertEqual(ranges[0][0], broad.start)
            self.assertEqual(ranges[-1][1], broad.end)
            for previous, following in zip(ranges, ranges[1:]):
                self.assertEqual(previous[1], following[0])
        asyncio.run(check())

    def test_failed_download_does_not_cache_coverage(self):
        async def check():
            client = google.GoogleHealthClient('token', cache=True, account_id='account', store=self.store)
            client._fetch_points = AsyncMock(side_effect=RuntimeError('offline'))
            with self.assertRaises(RuntimeError):
                await client._points(KIND, query().expression(query().start, query().end))
            self.assertTrue(self.store.range_read(client.account_key, KIND, query(), True)[1])
            client._fetch_points.side_effect = None
            client._fetch_points.return_value = []
            await client._points(KIND, query().expression(query().start, query().end))
            self.assertEqual(client._fetch_points.await_count, 2)
        asyncio.run(check())

    def test_explicit_refresh_bypasses_memory_and_replaces_readings(self):
        async def check():
            client = google.GoogleHealthClient('token', cache=True, account_id='account', store=self.store)
            client._fetch_points = AsyncMock(return_value=[point(5)])
            expression = query('2026-10-05', '2026-10-06').expression(query('2026-10-05', '2026-10-06').start, query('2026-10-05', '2026-10-06').end)
            await client._points(KIND, expression)
            self.store.expire_recent(client.account_key)
            client._fetch_points.return_value = [point(5, 80)]
            self.assertEqual(await client._points(KIND, expression), [point(5, 80)])
        # Keep the fixed 5 October fixture inside the explicit recent-refresh window.
        with patch('health_read_store.time.time', return_value=NOW):
            asyncio.run(check())
