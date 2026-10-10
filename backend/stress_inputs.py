"""Adapt app observations into the same stress calculator used by export tests."""
from datetime import datetime, time, timedelta, timezone
import math

import numpy as np
import pandas as pd

from stressmon.io import Export
from stressmon.pipeline import preprocess_hr, score_inputs

UTC = timezone.utc


def instant(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError('Stress observations require timezone-aware timestamps')
    return stamp.tz_convert('UTC')


def numeric(value):
    if isinstance(value, bool):
        return np.nan
    try:
        value = float(value)
        return value if math.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def adapt_inputs(samples, sleep_points, sessions, level_points, hrv_points, tz, cutoff, cfg):
    hr = pd.DataFrame([(instant(t), numeric(v)) for t, v in samples], columns=['timestamp', 'hr'])
    hr = hr[hr['timestamp'] < instant(cutoff)].dropna().groupby('timestamp', as_index=False)['hr'].median()
    sleeps, stages = [], []
    for point in sleep_points:
        sleep = point.get('sleep', {})
        interval = sleep.get('interval', {})
        if not interval.get('startTime') or not interval.get('endTime') or sleep.get('metadata', {}).get('processed') is False:
            continue
        start, end = instant(interval['startTime']), instant(interval['endTime'])
        if end <= start:
            continue
        sid = point.get('name') or f'{start}/{end}'
        sleeps.append((sid, start, end))
        for stage in sleep.get('stages', []) + sleep.get('shortAwakenings', []) + sleep.get('outOfBedSegments', []):
            stages.append((sid, instant(stage['startTime']), instant(stage['endTime']), stage.get('type', 'AWAKE')))
    sleeps = pd.DataFrame(sleeps, columns=['sleep_id', 'start', 'end']).drop_duplicates(['start', 'end'])
    stages = pd.DataFrame(stages, columns=['sleep_id', 'start', 'end', 'stage'])
    for frame in (sleeps, stages):
        for column in ('start', 'end'):
            frame[column] = pd.to_datetime(frame[column], utc=True)
    exercises = []
    for session in sessions:
        start, end = instant(session['start']), instant(session['end'])
        if end <= start:
            continue
        valid = hr['hr'].between(cfg['hr']['min_bpm'], cfg['hr']['max_bpm'])
        measured = hr.loc[valid & hr['timestamp'].between(start, end, inclusive='left'), 'hr'].mean()
        exercises.append((start, end, session['activity_name'], measured))
    exercises = pd.DataFrame(exercises, columns=['start', 'end', 'activity_name', 'tracker_avg_heart_rate'])
    levels = []
    allowed = {'SEDENTARY', 'LIGHTLY_ACTIVE', 'MODERATELY_ACTIVE', 'VERY_ACTIVE'}
    for point in level_points:
        item = point.get('activityLevel', {})
        interval = item.get('interval', {})
        if item.get('activityLevelType') not in allowed or not interval.get('startTime') or not interval.get('endTime'):
            continue
        start, end = instant(interval['startTime']), min(instant(interval['endTime']), instant(cutoff))
        for stamp in pd.date_range(start.ceil('1min'), end, freq='1min', inclusive='left'):
            levels.append((stamp, item['activityLevelType']))
    levels = pd.DataFrame(levels, columns=['timestamp', 'level']).drop_duplicates('timestamp')
    hrv_rows = []
    observed = []
    rejected_quality = 0
    for point in hrv_points:
        item = point.get('heartRateVariability', {})
        clock = item.get('sampleTime', {})
        if not clock.get('physicalTime'):
            continue
        stamp = instant(clock['physicalTime'])
        if stamp >= instant(cutoff):
            continue
        observed.append(stamp.to_pydatetime())
        # Google currently has no documented coverage field. Never assume 100%.
        coverage = numeric(item.get('coverage'))
        value = numeric(item.get('rootMeanSquareOfSuccessiveDifferencesMilliseconds'))
        if not math.isfinite(coverage) or coverage < cfg['hrv']['min_coverage']:
            rejected_quality += 1
            continue
        if cfg['hrv']['min_rmssd'] < value < cfg['hrv']['max_rmssd']:
            hrv_rows.append((stamp, value, coverage, math.log(value)))
    hrv = pd.DataFrame(hrv_rows, columns=['timestamp', 'rmssd', 'coverage', 'x']).drop_duplicates('timestamp')
    hrv['timestamp'] = pd.to_datetime(hrv['timestamp'], utc=True)
    empty = pd.DataFrame()
    data = Export(hr, hrv, stages, sleeps, exercises, levels, empty, pd.Series(dtype=float), tz, str(tz), {})
    return data, sorted(set(observed)), rejected_quality


def demo_inputs(first, last, tz, cutoff, cfg):
    from activity_details import showcase_inputs
    from mock_sleep_stage_ranges import mock_stage_points
    _, sessions, _, _ = showcase_inputs(first, last, tz)[0]
    sleep_points = [p for day in pd.date_range(first, last + timedelta(days=1)) for p in mock_stage_points(day.date(), 1)]
    start = datetime.combine(first, time.min, tzinfo=tz)
    stamps = pd.date_range(start, cutoff, freq='5s', inclusive='left').tz_convert('UTC')
    # The same date must have identical synthetic readings in W and M views.
    seconds = stamps.asi8 / 1e9
    hr = 70 + 5 * np.sin(seconds / 3700) + 2 * np.sin(seconds / 19)
    for point in sleep_points:
        item = point['sleep']['interval']
        mask = (stamps >= instant(item['startTime'])) & (stamps < instant(item['endTime']))
        hr[mask] = 56 + 3 * np.sin(seconds[mask] / 190)
    level = np.repeat('SEDENTARY', len(stamps)).astype(object)
    for session in sessions:
        mask = (stamps >= instant(session['start'])) & (stamps < instant(session['end']))
        target = 105 if 'walk' in session['activity_name'].lower() else 170 if 'run' in session['activity_name'].lower() else 125
        hr[mask] = target + 5 * np.sin(seconds[mask] / 35)
        level[mask] = 'LIGHTLY_ACTIVE'
    # A measured, synthetic off-wrist gap at 11:00–13:00 each display day.
    minutes = stamps.tz_convert(tz).hour * 60 + stamps.tz_convert(tz).minute
    missing = (minutes >= 660) & (minutes < 780)
    samples = list(zip(stamps[~missing], hr[~missing]))
    unique = np.arange(0, len(stamps), 12)
    minute_levels = level[unique]
    cuts = np.r_[0, np.flatnonzero(minute_levels[1:] != minute_levels[:-1]) + 1, len(unique)]
    level_points = [{'activityLevel': {'interval': {'startTime': str(stamps[unique[lo]]),
                      'endTime': str(stamps[unique[hi]] if hi < len(unique) else instant(cutoff))},
                      'activityLevelType': minute_levels[lo]}} for lo, hi in zip(cuts[:-1], cuts[1:])]
    hrv = []
    for point in sleep_points:
        interval = point['sleep']['interval']
        for stamp in pd.date_range(instant(interval['startTime']) + pd.Timedelta(minutes=5), instant(interval['endTime']), freq='5min'):
            hrv.append({'heartRateVariability': {'sampleTime': {'physicalTime': stamp.isoformat()},
                        'rootMeanSquareOfSuccessiveDifferencesMilliseconds': 50 + 3 * math.sin(stamp.timestamp() / 700),
                        'coverage': 1.0}})  # Known synthetic coverage, never added to live data.
    return adapt_inputs(samples, sleep_points, sessions, level_points, hrv, tz, cutoff, cfg)


def calculate(data, cfg):
    if data.hr.empty or not data.hr['hr'].between(cfg['hr']['min_bpm'], cfg['hr']['max_bpm']).any():
        return pd.DataFrame()
    minute = preprocess_hr(data, cfg)
    report = {'within_sleep_hrv_enabled': False, 'exercise_checks': []}
    return score_inputs(data, cfg, minute, data.hrv, pd.Series(dtype=float), report)[0]
