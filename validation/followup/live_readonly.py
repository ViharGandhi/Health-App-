"""Read-only Google v4 audit. Raw observations and credentials stay in memory.

Requires GOOGLE_HEALTH_ACCESS_TOKEN and the three Google Health readonly scopes
listed in LIVE_README.md. No OAuth refresh, database writes or webhook calls.
"""
import argparse
import asyncio
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from google_health_client import GoogleHealthClient, _day_filter
from health_read_store import read_range, point_clock
from health_trends import valid_health_value, build_health_response
from main import _compute_real_sleep
from recovery_score import recovery_from_history
from strain_service import calculate_days, sleep_windows
from sleep_need_inputs import SleepNeedInputs
from sleep_stage_ranges import adapt_google_sleep, stage_stats, personal_ranges
from sleep_stress import adapt_google_sleep as stress_sleep, adapt_google_hr, adapt_google_hrv, prepare_night, score_night


class MemorySummaries(GoogleHealthClient):
    """Reuse production adapters against already fetched summaries, without storage."""
    def __init__(self, points):
        super().__init__('in-memory-not-a-token', cache=False)
        self.points = points

    async def _points(self, kind, expression, *, reconcile=True):
        query = read_range(expression)
        if query is None or kind not in self.points:
            raise ValueError('Unsupported in-memory summary query')
        return [p for p in self.points[kind] if (clock := point_clock(p, query.field)) is not None
                and query.start <= clock < query.end]


async def readonly_request(request):
    if request.method != 'GET' or request.url.host != 'health.googleapis.com' or not request.url.path.startswith('/v4/users/me/dataTypes/'):
        raise RuntimeError('Request outside readonly observation scope')


async def audit(remote, end, days=60, age=30, tz=timezone.utc, sex='m', anchor=None):
    """Score 30–60 days with an extra 67 daily dates for Recovery reference."""
    first = end - timedelta(days=days - 1)
    baseline_start = first - timedelta(days=67)
    raw = {}
    kinds = ('daily-heart-rate-variability', 'daily-resting-heart-rate', 'daily-oxygen-saturation',
             'daily-respiratory-rate', 'daily-sleep-temperature-derivations', 'daily-vo2-max')
    for kind in kinds:
        raw[kind] = await remote._points(kind, _day_filter(kind.replace('-', '_') + '.date', baseline_start, end))
    raw['sleep'] = await remote.get_sleep_stage_points(first - timedelta(days=14), end)
    memory = MemorySummaries(raw)
    health = await memory.get_health_history(baseline_start, end)
    records = await memory._sleep_records(first - timedelta(days=9), end)
    naps = await memory.get_nap_minutes_history(first - timedelta(days=9), end)
    rhrs = {date.fromisoformat(p['date']): p['value'] for p in health.get('rhr', [])}
    sleeps = sleep_windows(raw['sleep'])
    strains, prepared = {}, []
    statuses = Counter()
    malformed = Counter()
    observations = {}
    selected_stages = {}
    by_date = Counter()
    ids = Counter()
    offsets = []
    deltas = {'asleep_minutes': [], 'period_minutes': [], 'deep_minutes': [], 'rem_minutes': [], 'light_minutes': [], 'efficiency_pct': []}
    for point in raw['sleep']:
        try:
            night = adapt_google_sleep(point)
            ids[night.sleep_id] += 1
            if night.main_sleep is not False and not night.nap: by_date[night.night_date] += 1
            stats, status = stage_stats(night)
            statuses['stage:' + status] += 1
            offsets.append({'wake_date_matches_provider_offset': night.night_date == stress_sleep(point).night_date,
                'device_date_matches_user_timezone': night.night_date == night.end_utc.astimezone(tz).date()})
            if stats:
                summary = point['sleep'].get('summary', {})
                reported = {s['type']: float(s['minutes']) for s in summary.get('stagesSummary', [])}
                asleep = sum(stats.minutes[s] for s in ('light', 'deep', 'rem'))
                for key, actual, reference in [('asleep_minutes', asleep, summary.get('minutesAsleep')),
                    ('period_minutes', stats.total_minutes, summary.get('minutesInSleepPeriod')),
                    ('deep_minutes', stats.minutes['deep'], reported.get('DEEP')), ('rem_minutes', stats.minutes['rem'], reported.get('REM')),
                    ('light_minutes', stats.minutes['light'], reported.get('LIGHT'))]:
                    if reference is not None and math.isfinite(float(reference)):
                        deltas[key].append(actual - float(reference))
                if summary.get('minutesAsleep') is not None and float(summary.get('minutesInSleepPeriod') or 0) > 0:
                    deltas['efficiency_pct'].append(100 * asleep / stats.total_minutes - 100 * float(summary['minutesAsleep']) / float(summary['minutesInSleepPeriod']))
            if night.main_sleep is not False and status not in ('nap_excluded', 'short_sleep_excluded'):
                key = (night.main_sleep is True, night.end_utc - night.start_utc, night.sleep_id)
                previous = selected_stages.get(night.night_date)
                if previous is None or key > previous[0]:
                    selected_stages[night.night_date] = (key, stats)
        except (KeyError, TypeError, ValueError, OverflowError):
            malformed['sleep_schema'] += 1
    observations = {day: item[1] for day, item in selected_stages.items() if item[1] is not None}
    # Bound intraday memory to roughly one week plus overlap. Keep only derived windows.
    chunk = first - timedelta(days=14)
    while chunk <= end:
        upper = min(chunk + timedelta(days=6), end)
        physical_start = chunk - timedelta(days=1)
        physical_end = upper + timedelta(days=2)
        expression = lambda field: f'{field} >= "{physical_start}T00:00:00Z" AND {field} < "{physical_end}T00:00:00Z"'
        hr = await remote._points('heart-rate', expression('heart_rate.sample_time.physical_time'))
        hrv = await remote._points('heart-rate-variability', expression('heart_rate_variability.sample_time.physical_time'))
        samples = []
        for point in hr:
            try: samples.append(adapt_google_hr(point))
            except (ValueError, TypeError, KeyError): malformed['hr_schema'] += 1
        workouts = await remote.get_workout_sessions(chunk - timedelta(days=1), upper + timedelta(days=1), preserve_offset=True)
        strains.update(calculate_days(chunk, upper, datetime.now(timezone.utc), tz, age, sex, False,
            ([(p.time_utc, p.bpm) for p in samples], workouts, sleeps, rhrs)))
        if anchor:
            windows = adapt_google_hrv(hrv, anchor)
            for point in raw['sleep']:
                night = stress_sleep(point)
                if chunk <= night.night_date <= upper:
                    prepared.append(prepare_night(night, windows, samples))
        chunk = upper + timedelta(days=1)
    sleep_map = {r['date']: r['total_duration'] / 60 if r['sleep_duration_available'] else None for r in records}
    strain_map = {d: v['strain'] / 21 * 100 if v['strain'] is not None and v['coverage'] > 0 else None for d, v in strains.items()}
    need_inputs = SleepNeedInputs(sleep_map, strain_map, naps)
    confidence = Counter()
    finite_results = Counter()
    current_sleep = None
    for i in range(days):
        day = first + timedelta(days=i)
        need = need_inputs.for_tonight(day - timedelta(days=1))
        estimate = recovery_from_history(health, day, sleep_map.get(day), need.total_need_min if need else None)
        confidence[estimate.confidence or estimate.status] += 1
        sleep = await _compute_real_sleep(memory, day, need, age)
        for name, value, lower, upper in [('recovery', estimate.percent, 0, 100), ('sleep_score', sleep.score, 0, 100),
            ('efficiency', sleep.efficiency_pct, 0, 100), ('sleep_need', need.total_need_min if need else None, 360, 660),
            ('strain', strains[day]['strain'], 0, 21)]:
            finite_results[name + (':missing' if value is None else ':valid' if math.isfinite(value) and lower <= value <= upper else ':invalid')] += 1
        if day in observations:
            bands, used = personal_ranges(observations[day], list(observations.values()))
            statuses['stage_ranges:' + ('ok' if bands else 'building_baseline')] += 1
        if day == end: current_sleep = sleep
    for item in prepared:
        if first <= item.night.night_date <= end:
            result = score_night(item, prepared)
            statuses['stress:' + result['status']] += 1
    rejected = {}
    for metric, points in health.items():
        causes = Counter()
        for p in points:
            if not valid_health_value(metric, p['value']):
                value = p['value']
                causes['nonfinite' if not math.isfinite(value) else 'nonpositive' if value <= 0 else 'outside_existing_unit_or_hr_limit'] += 1
        rejected[metric] = dict(causes)
    health_response = build_health_response(health, [], first, end, 'M', False)
    return {'live': True, 'requested_days': days, 'additional_reference_days': 67,
        'recovery_confidence_counts': dict(confidence), 'score_validity_counts': dict(finite_results),
        'stage_stress_statuses': dict(statuses), 'stress_timing': 'verified_by_operator' if anchor else 'unverified_not_scored',
        'duplicates': {'repeated_sleep_id_rows': sum(n - 1 for n in ids.values()),
            'dates_with_multiple_main_sessions': sum(n > 1 for n in by_date.values())},
        'strain_rhr_rejections': sum(v['params']['rhr_rejected_count'] for d, v in strains.items() if first <= d <= end),
        'health_rejections_by_metric_and_reason': rejected, 'schema_errors': dict(malformed),
        'sampled_timezone_checks': offsets[:5],
        'provider_deltas': {key: {'compared_nights': len(values), 'mean_difference': sum(values) / len(values) if values else None,
            'max_absolute_difference': max(map(abs, values), default=None)} for key, values in deltas.items()},
        'structure': {'connected_sleep_fields': sorted(current_sleep.model_dump()), 'health_fields': sorted(health_response.model_dump()),
            'connected': 'Provider summaries for composite sleep; stage segments for descriptive ranges; intraday HR/HRV for stress.',
            'demo': 'Synthetic fixtures and optional legacy Recovery; fixture identity/timestamps are not evidence of provider validity.'},
        'privacy': 'Aggregates and field names only; no IDs, dates, raw readings or tokens saved.',
        'limitations': ['Unbounded finite HRV/respiration/temperature/VO2 values require agreed ceilings.',
            'RHR rejection sum counts occurrences across rolling windows, not unique records.',
            'Provider summaries are a reference, not ground truth; stage/summary definitions can differ.']}


async def run(args):
    token = os.getenv('GOOGLE_HEALTH_ACCESS_TOKEN')
    if not token:
        return {'live': False, 'reason': 'GOOGLE_HEALTH_ACCESS_TOKEN unavailable; no live reads attempted.'}
    tz = ZoneInfo(args.timezone)
    end = date.fromisoformat(args.end) if args.end else datetime.now(tz).date()
    if end > datetime.now(tz).date(): raise ValueError('Future end date')
    real_client = httpx.AsyncClient
    def http_client(**kwargs):
        kwargs['event_hooks'] = {'request': [readonly_request]}
        return real_client(**kwargs)
    with patch('google_health_client.httpx.AsyncClient', http_client):
        return await audit(GoogleHealthClient(token, cache=False), end, args.days, args.age, tz, args.sex, args.anchor)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, choices=range(30, 61), default=60)
    parser.add_argument('--age', type=int, choices=range(18, 101), required=True)
    parser.add_argument('--sex', choices=('m', 'f'), required=True)
    parser.add_argument('--timezone', required=True)
    parser.add_argument('--end')
    parser.add_argument('--anchor', choices=('start', 'end'), help='Supply only after real-device timestamp calibration.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)  # Production partition warnings contain raw IDs.
    try:
        result = asyncio.run(run(args))
    except httpx.HTTPStatusError as error:
        result = {'live': False, 'reason': 'Provider read failed', 'http_status': error.response.status_code}
    except Exception as error:
        result = {'live': False, 'reason': 'Read-only audit failed; raw exception withheld', 'error_type': type(error).__name__}
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.output: args.output.write_text(text, encoding='utf-8')
    print(text)
    sys.exit(0 if result.get('live') else 2)
