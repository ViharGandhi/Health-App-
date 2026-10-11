"""App Stress Monitor: shared HR model, genuine gaps, and explicit provenance."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, time, timedelta, timezone

from stressmon.config import load_config
from stress_inputs import adapt_inputs, calculate, demo_inputs


def category(score):
    return 'low' if score < 1 else 'medium' if score < 2 else 'high'


def recording_timezone(sleeps, day, now, fallback):
    candidates = []
    for point in sleeps:
        sleep = point.get('sleep', {})
        metadata, interval = sleep.get('metadata', {}), sleep.get('interval', {})
        if metadata.get('nap') or metadata.get('mainSleep') is False or metadata.get('processed') is False:
            continue
        offset = interval.get('endUtcOffset', interval.get('startUtcOffset'))
        if offset is None or not interval.get('endTime'):
            continue
        try:
            tz = timezone(timedelta(seconds=float(offset.removesuffix('s'))))
            end = datetime.fromisoformat(interval['endTime'].replace('Z', '+00:00'))
            if end.tzinfo is not None and end <= now and end.astimezone(tz).date() <= day:
                candidates.append((end, bool(metadata.get('mainSleep')), tz))
        except (ValueError, TypeError, AttributeError, OverflowError):
            continue
    return max(candidates, key=lambda item: item[:2])[2] if candidates else fallback


def summarize(start, end, points):
    seconds = dict.fromkeys(('low', 'medium', 'high'), 0.0)
    weighted = 0.0
    previous_end = start.timestamp()
    for point in points:
        left, right = point['start'].timestamp(), point['end'].timestamp()
        if left < previous_end or right <= left or left < start.timestamp() or right > end.timestamp():
            raise ValueError('Stress intervals must be ordered, non-overlapping and inside the day')
        previous_end = right
        score = point['score']
        if score is None:
            continue
        if not math.isfinite(score) or not 0 <= score <= 3:
            raise ValueError('Stress score outside 0–3')
        seconds[category(score)] += right - left
        weighted += score * (right - left)
    scored = sum(seconds.values())
    elapsed = max(0, end.timestamp() - start.timestamp())
    return {'average': round(weighted / scored, 2) if scored else None,
            'minutes': {k: v / 60 for k, v in seconds.items()},
            'unscored_minutes': (elapsed - scored) / 60,
            'scored_minutes': scored / 60, 'elapsed_minutes': elapsed / 60,
            'coverage': scored / elapsed if elapsed else 0}


def _day(day, tz, now, points, overlays, hrv, *, demo=False, stale_minutes=15):
    start = datetime.combine(day, time.min, tzinfo=tz)
    calendar_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    end = max(start, min(calendar_end, now))
    total = summarize(start, end, points)
    latest = next((p for p in reversed(points) if p['score'] is not None), None)
    stale = bool(latest and end.timestamp() - latest['end'].timestamp() > stale_minutes * 60)
    masked = bool(points and points[-1].get('state') == 'EXERCISE')
    clipped = []
    for item in overlays:
        left, right = max(start.timestamp(), item['start'].timestamp()), min(end.timestamp(), item['end'].timestamp())
        if right > left:
            clipped.append({**item, 'start': datetime.fromtimestamp(left, tz), 'end': datetime.fromtimestamp(right, tz)})
    observations = [t for t in hrv if start.timestamp() <= t.timestamp() < end.timestamp()]
    awake = sum(not any(o['kind'] == 'sleep' and o['start'] <= t < o['end'] for o in overlays) for t in observations)
    return {'date': day.isoformat(), 'start': start, 'end': end, 'calendar_end': calendar_end, **total,
            'points': points, 'overlays': clipped,
            'latest_score': round(latest['score'], 1) if latest and not stale and not masked else None,
            'latest_level': category(latest['score']) if latest and not stale and not masked else None,
            'latest_at': latest['end'] if latest else None, 'stale': stale,
            'hrv_samples': len(observations), 'awake_hrv_samples': awake,
            'status': 'synthetic' if demo else 'estimated' if total['scored_minutes'] else 'no_hr'}


def _present(data, frame, observations, dates, tz, now, cfg, demo, rejected):
    overlays = [{'kind': 'sleep', 'name': 'Sleep', 'start': p.start.to_pydatetime(), 'end': p.end.to_pydatetime()} for p in data.sleeps.itertuples()]
    overlays += [{'kind': 'activity', 'name': p.activity_name, 'start': p.start.to_pydatetime(), 'end': p.end.to_pydatetime()} for p in data.exercises.itertuples()]
    history = []
    for day in dates:
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = max(start, min(datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz), now))
        selected = frame[frame['date'].eq(str(day))] if len(frame) else frame
        points = []
        for row in selected.itertuples():
            left, right = max(start, row.Index.to_pydatetime()), min(end, row.end.to_pydatetime())
            if right.timestamp() <= left.timestamp():
                continue
            score = float(row.score) if math.isfinite(row.score) else None
            reason = None if score is not None else 'exercise_recovery' if row.state == 'EXERCISE' else 'missing_hr' if not math.isfinite(row.hr) else 'baseline_building'
            source = 'hr_plus_sleep_hrv' if math.isfinite(row.z_hrv) else 'hr_plus_night_context' if math.isfinite(row.z_night) else 'hr_only'
            points.append({'start': left, 'end': right, 'score': score, 'state': row.state,
                           'reason': reason, 'source': source, 'hr': float(row.hr) if math.isfinite(row.hr) else None})
        if points and points[-1]['end'].timestamp() < end.timestamp():
            points.append({'start': points[-1]['end'], 'end': end, 'score': None, 'state': 'GAP',
                           'reason': 'missing_hr', 'source': 'unavailable', 'hr': None})
        value = _day(day, tz, now, points, overlays, observations, demo=demo, stale_minutes=cfg['app']['stale_minutes'])
        baseline = selected.iloc[0] if len(selected) else None
        value.update(baseline_days=int(baseline['baseline_days']) if baseline is not None else 0,
                     baseline_mode=str(baseline['baseline_mode']) if baseline is not None else 'auto',
                     baseline_leaks=bool(baseline['baseline_leaks']) if baseline is not None else False,
                     low_confidence=bool(baseline['low_confidence']) if baseline is not None else True,
                     hrv_quality_verified=demo, hrv_quality_rejected=rejected,
                     sleep_hrv_enabled=cfg['time']['hrv_window_anchor'] != 'unverified' and not data.hrv.empty,
                     night_context_enabled=bool(len(selected) and selected['z_night'].notna().any()),
                     sleep_stress=summarize(start, end, [p for p in points if p.get('state') == 'SLEEP'])['average'],
                     non_activity_stress=summarize(start, end, [p for p in points if p.get('state') in ('STILL', 'AMBIG')])['average'])
        if not value['scored_minutes'] and len(selected) and selected['hr'].notna().any():
            value['status'] = 'baseline_building'
        history.append(value)
    return {'is_mock': demo, 'model': 'hr-baseline-logistic-v2', 'validated': False,
            'timezone': str(tz), 'current': history[-1], 'days': history,
            'data_source': 'synthetic' if demo else 'stored_google_health',
            'limitations': 'Independent, unvalidated wellness estimate. Awake scores use HR; nighttime HRV contributes only with known coverage. Exercise/recovery and missing HR stay unscored. Not WHOOP or Bevel.'}


async def stress_monitor(client, end_day, tz, *, days=7, now=None, demo=False, age=None):
    cfg = load_config()
    cfg['physiology']['age'] = age
    cfg['smoothing']['mode'] = 'live'
    now = now or datetime.now(timezone.utc)
    first = end_day - timedelta(days=days - 1)
    reference_start = first - timedelta(days=cfg['baselines']['window_days'])
    dates = [first + timedelta(days=i) for i in range(days)]
    if demo:
        hour, minute = map(int, cfg['app']['demo_cutoff'].split(':'))
        now = datetime.combine(end_day, time(hour, minute), tzinfo=tz)
        cfg['time']['hrv_window_anchor'] = 'end'
        data, observations, rejected = await asyncio.to_thread(demo_inputs, reference_start, end_day, tz, now, cfg)
    else:
        sleeps = await client.get_sleep_stage_points(reference_start, end_day + timedelta(days=1))
        tz = recording_timezone(sleeps, end_day, now, tz)
        end = min(datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz), now)
        start = datetime.combine(reference_start, time.min, tzinfo=tz).astimezone(timezone.utc)
        field = 'heart_rate_variability.sample_time.physical_time'
        expression = f'{field} >= "{start.isoformat()}" AND {field} < "{end.astimezone(timezone.utc).isoformat()}"'
        samples, sessions, levels, hrv = await asyncio.gather(
            client.get_intraday_heart_rate(reference_start - timedelta(days=1), end_day + timedelta(days=1), preserve_offset=True),
            client.get_workout_sessions(reference_start - timedelta(days=1), end_day, preserve_offset=True),
            client.get_activity_level_points(reference_start, end_day),
            client._points('heart-rate-variability', expression))
        data, observations, rejected = await asyncio.to_thread(adapt_inputs, samples, sleeps, sessions, levels, hrv, tz, end, cfg)
    frame = await asyncio.to_thread(calculate, data, cfg)
    return await asyncio.to_thread(_present, data, frame, observations, dates, tz, now, cfg, demo, rejected)
