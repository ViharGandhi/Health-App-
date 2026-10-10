"""Restricted Takeout reads. No recursive discovery or unrestricted CSV columns."""
from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .config import fixed_timezone


PATTERNS = {
    'hr': ('Physical Activity_GoogleData/Heart Rate', 'heart_rate_*.csv'),
    'hrv': ('Heart Rate Variability', 'Heart Rate Variability Details - *.csv'),
    'sleep': ('Health Fitness Data_GoogleData', 'UserSleepStages_*.csv'),
    'exercises': ('Health Fitness Data_GoogleData', 'UserExercises_*.csv'),
    'level': ('Physical Activity_GoogleData/Activity Level', 'activity_level_*.csv'),
    'steps': ('Global Export Data', 'steps-*.json'),
    'motion': ('Health Fitness Data_GoogleData', 'UserActivityProbabilities_*.csv'),
}
COLUMNS = {
    'hr': ['timestamp', 'beats per minute', 'data source'],
    'hrv': ['timestamp', 'rmssd', 'coverage', 'low_frequency', 'high_frequency'],
    'sleep': ['sleep_id', 'sleep_stage_type', 'start_utc_offset', 'sleep_stage_start', 'sleep_stage_end'],
    'exercises': ['exercise_start', 'exercise_end', 'utc_offset', 'activity_name',
                  'tracker_avg_heart_rate', 'tracker_peak_heart_rate', 'tracker_total_steps'],
    'level': ['timestamp', 'level'],
    'motion': ['activity_probabilities_start', 'activity_probabilities_end', 'activity_probabilities'],
}


@dataclass
class Export:
    hr: pd.DataFrame
    hrv: pd.DataFrame
    stages: pd.DataFrame
    sleeps: pd.DataFrame
    exercises: pd.DataFrame
    levels: pd.DataFrame
    steps_naive: pd.DataFrame
    motion: pd.Series
    timezone: object
    source_offset: str
    files: dict


def allowed_files(root, kind, required=True):
    root = Path(root).resolve()
    folder, pattern = PATTERNS[kind]
    files = sorted((root / folder).glob(pattern))
    files = [p for p in files if p.is_file()]
    for path in files:
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'Refusing a file outside the Takeout root: {path.name}')
    if required and not files:
        raise ValueError(f'Missing required files: {folder}/{pattern}')
    return files


def csv_read(path, kind, chunksize=None):
    header = pd.read_csv(path, nrows=0)
    missing = sorted(set(COLUMNS[kind]) - set(header.columns))
    if missing:
        raise ValueError(f'{path.name}: missing required column(s): {", ".join(missing)}')
    # In particular, exercise location_metadata and all other columns are excluded.
    return pd.read_csv(path, usecols=COLUMNS[kind], chunksize=chunksize)


def utc(series, label):
    if not series.astype(str).str.endswith('Z').all():
        raise ValueError(f'{label}: expected ISO UTC timestamps ending with Z')
    return pd.to_datetime(series, utc=True, format='mixed', errors='raise')


def _numeric(frame, columns):
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors='coerce').astype(float)


def _motion(files, cfg):
    parts = []
    target = 'ACTIVITY_PROBABILITY_TYPE_STILL'
    for path in files:
        for chunk in csv_read(path, 'motion', cfg['motion']['chunk_rows']):
            chunk = chunk[chunk['activity_probabilities'].astype(str).str.contains(target, regex=False)]
            if chunk.empty:
                continue
            values = []
            for text in chunk['activity_probabilities']:
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict) and target in payload:
                        value = payload[target]
                    else:
                        entries = payload if isinstance(payload, list) else payload.get('activityProbabilities', [])
                        item = next(v for v in entries if v.get('type', v.get('activityProbabilityType')) == target)
                        value = item.get('probability', item.get('value'))
                    value = float(value)
                    if not 0 <= value <= 1:
                        raise ValueError()
                except (ValueError, TypeError, KeyError, StopIteration, AttributeError):
                    raise ValueError(f'{path.name}: cannot parse STILL probability; no raw row was logged') from None
                values.append(value)
            stamps = utc(chunk['activity_probabilities_start'], path.name)
            parts.append(pd.Series(values, index=pd.DatetimeIndex(stamps)))
    return pd.concat(parts).sort_index().resample('1min').median() if parts else pd.Series(dtype=float)


def load_export(root, cfg):
    files = {kind: allowed_files(root, kind) for kind in ('hr', 'hrv', 'sleep', 'exercises', 'level')}
    frames = {kind: pd.concat([csv_read(p, kind) for p in paths], ignore_index=True) for kind, paths in files.items()}
    hr = frames['hr'].rename(columns={'beats per minute': 'hr'})
    hr = hr[hr['data source'] == cfg['hr']['source']].copy()
    if hr.empty:
        raise ValueError('No HR rows from the configured Fitbit data source')
    hr['timestamp'] = utc(hr['timestamp'], 'Heart Rate')
    _numeric(hr, ['hr'])
    hr = hr.sort_values('timestamp').groupby('timestamp', as_index=False)['hr'].median()
    hrv = frames['hrv'].copy()
    if hrv['timestamp'].astype(str).str.contains(r'(?:Z|[+-]\d{2}:\d{2})$', regex=True).any():
        raise ValueError('HRV detail timestamps must be naive; do not silently strip their offsets')
    hrv['timestamp'] = pd.to_datetime(hrv['timestamp'], format='mixed', errors='raise')
    _numeric(hrv, ['rmssd', 'coverage', 'low_frequency', 'high_frequency'])
    hrv = hrv.drop_duplicates('timestamp').sort_values('timestamp')
    stages = frames['sleep'].rename(columns={'sleep_stage_start': 'start', 'sleep_stage_end': 'end', 'sleep_stage_type': 'stage'})
    stages['start'], stages['end'] = utc(stages['start'], 'Sleep start'), utc(stages['end'], 'Sleep end')
    if stages.empty or (stages['end'] <= stages['start']).any():
        raise ValueError('Sleep export must contain ordered, positive-duration stages')
    stages = stages.drop_duplicates(['sleep_id', 'start', 'end', 'stage']).sort_values(['sleep_id', 'start'])
    sleeps = stages.groupby('sleep_id').agg(start=('start', 'min'), end=('end', 'max')).reset_index()
    exercises = frames['exercises'].rename(columns={'exercise_start': 'start', 'exercise_end': 'end'})
    exercises['start'], exercises['end'] = utc(exercises['start'], 'Exercise start'), utc(exercises['end'], 'Exercise end')
    if (exercises['end'] <= exercises['start']).any():
        raise ValueError('Exercise export contains a nonpositive session duration')
    _numeric(exercises, ['tracker_avg_heart_rate', 'tracker_peak_heart_rate', 'tracker_total_steps'])
    exercises = exercises.drop_duplicates(['start', 'end', 'activity_name']).sort_values('start')
    offsets = set(stages['start_utc_offset'].dropna().astype(str)) | set(exercises['utc_offset'].dropna().astype(str))
    if len(offsets) != 1:
        raise ValueError('Expected one source UTC offset for naive HRV alignment; mixed offsets need an explicit per-night policy')
    source_offset = offsets.pop()
    fixed_timezone(source_offset)
    tz = fixed_timezone(cfg['time']['display_offset'] or source_offset)
    levels = frames['level'].copy()
    levels['timestamp'] = utc(levels['timestamp'], 'Activity Level')
    levels = levels.drop_duplicates('timestamp').sort_values('timestamp')
    files['steps'] = allowed_files(root, 'steps', required=False) if cfg['steps']['enabled'] else []
    step_parts = []
    for path in files['steps']:
        with path.open(encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, list) or any(not isinstance(r, dict) or not {'dateTime', 'value'} <= r.keys() for r in data):
            raise ValueError(f'{path.name}: expected steps dateTime/value objects')
        frame = pd.DataFrame(data, columns=['dateTime', 'value'])
        frame['timestamp'] = pd.to_datetime(frame['dateTime'], format='%m/%d/%y %H:%M:%S', errors='raise')
        frame['steps'] = pd.to_numeric(frame['value'], errors='raise')
        if (frame['steps'] < 0).any():
            raise ValueError(f'{path.name}: negative step count')
        step_parts.append(frame[['timestamp', 'steps']])
    steps = pd.concat(step_parts, ignore_index=True).drop_duplicates('timestamp') if step_parts else pd.DataFrame(columns=['timestamp', 'steps'])
    files['motion'] = allowed_files(root, 'motion') if cfg['motion']['enabled'] else []
    motion = _motion(files['motion'], cfg) if files['motion'] else pd.Series(dtype=float)
    return Export(hr, hrv, stages, sleeps, exercises, levels, steps, motion, tz, source_offset,
                  {k: [str(p) for p in v] for k, v in files.items()})


def sleep_membership(stamps, sleeps):
    stamps = pd.DatetimeIndex(stamps)
    result = np.zeros(len(stamps), dtype=bool)
    for item in sleeps.itertuples():
        result |= (stamps >= item.start) & (stamps < item.end)
    return result


def alignment_probe(data, minute, cfg):
    offsets = list(dict.fromkeys(['+00:00', data.source_offset]))
    candidates, anchors = {}, {}
    naive = pd.DatetimeIndex(data.hrv['timestamp'])
    if not len(naive):
        raise ValueError('No HRV detail observations for alignment')
    window = pd.Timedelta(minutes=cfg['hr']['window_minutes'])
    for offset in offsets:
        aligned = naive.tz_localize(fixed_timezone(offset)).tz_convert('UTC')
        candidates[offset] = float(sleep_membership(aligned, data.sleeps).mean())
        anchors[offset] = {anchor: float((sleep_membership(aligned + shift, data.sleeps) &
                                          sleep_membership(aligned + shift + window - pd.Timedelta(nanoseconds=1), data.sleeps)).mean())
                           for anchor, shift in [('start', pd.Timedelta(0)), ('end', -window)]}
    ranked = sorted(candidates, key=candidates.get, reverse=True)
    best = ranked[0]
    if candidates[best] < cfg['time']['alignment_min_sleep_share']:
        raise ValueError(f'HRV timezone alignment failed: sleep shares {candidates}; need >= {cfg["time"]["alignment_min_sleep_share"]:.0%}')
    if len(ranked) > 1 and candidates[best] - candidates[ranked[1]] < cfg['time']['alignment_min_margin']:
        raise ValueError(f'HRV timezone alignment is ambiguous: sleep shares {candidates}; confirm the source timezone')
    hrv = data.hrv.copy()
    hrv['timestamp'] = naive.tz_localize(fixed_timezone(best)).tz_convert('UTC')
    valid = (hrv['coverage'] >= cfg['hrv']['min_coverage']) & hrv['rmssd'].between(cfg['hrv']['min_rmssd'], cfg['hrv']['max_rmssd'], inclusive='neither')
    hrv = hrv[valid].copy()
    hrv['x'] = np.log(hrv['rmssd'])
    if cfg['hrv']['spectral_features']:
        hrv['ln_hf'] = np.log(hrv['high_frequency'].where(hrv['high_frequency'] > 0))
        hrv['lf_hf'] = hrv['low_frequency'].where(hrv['low_frequency'] >= 0) / hrv['high_frequency'].where(hrv['high_frequency'] > 0)
    exercise_checks = []
    for item in data.exercises.itertuples():
        values = data.hr.loc[data.hr['timestamp'].between(item.start, item.end), 'hr']
        values = values[values.between(cfg['hr']['min_bpm'], cfg['hr']['max_bpm'])]
        measured, tracker = values.median(), item.tracker_avg_heart_rate
        error = abs(measured - tracker) / tracker if np.isfinite(measured) and tracker > 0 else np.nan
        exercise_checks.append({'activity': item.activity_name, 'median_hr': float(measured), 'tracker_average': float(tracker),
                                'relative_error': float(error), 'aligned': bool(error <= cfg['time']['exercise_hr_tolerance']) if np.isfinite(error) else None})
    level = data.levels.assign(active=data.levels['level'] != cfg['states']['sedentary_level']).set_index('timestamp')['active'].resample('1min').max()
    steps = pd.Series(dtype=float)
    step_offset = None
    step_candidates = {}
    if len(data.steps_naive):
        for offset in offsets:
            series = pd.Series(data.steps_naive['steps'].to_numpy(), index=pd.DatetimeIndex(data.steps_naive['timestamp']).tz_localize(fixed_timezone(offset)).tz_convert('UTC')).resample('1min').sum(min_count=1)
            pairs = pd.concat([series.rename('steps'), level.astype(float).rename('active')], axis=1).dropna()
            corr = pairs['steps'].corr(pairs['active']) if len(pairs) >= cfg['steps']['alignment_min_overlap'] and pairs['steps'].std() and pairs['active'].std() else np.nan
            step_candidates[offset] = {'overlap': len(pairs), 'correlation': float(corr)}
        ranked_steps = sorted(offsets, key=lambda o: np.nan_to_num(step_candidates[o]['correlation'], nan=-np.inf), reverse=True)
        winner = ranked_steps[0]
        runner_up = np.nan_to_num(step_candidates[ranked_steps[1]]['correlation'], nan=-np.inf) if len(ranked_steps) > 1 else -np.inf
        advantage = step_candidates[winner]['correlation'] - runner_up
        if step_candidates[winner]['correlation'] >= cfg['steps']['alignment_min_correlation'] and advantage >= cfg['steps']['alignment_min_margin']:
            step_offset = winner
            steps = pd.Series(data.steps_naive['steps'].to_numpy(), index=pd.DatetimeIndex(data.steps_naive['timestamp']).tz_localize(fixed_timezone(winner)).tz_convert('UTC')).resample('1min').sum(min_count=1)
    per_night = []
    sessions = data.sleeps.assign(wake_date=data.sleeps['end'].dt.tz_convert(data.timezone).dt.date.astype(str))
    for date, group in sessions.groupby('wake_date'):
        count = int(sleep_membership(hrv['timestamp'], group).sum())
        per_night.append({'wake_date': date, 'sleep_records': len(group), 'valid_hrv_windows': count})
    local = minute.index.tz_convert(data.timezone)
    coverage = minute['hr'].notna().groupby(local.floor('5min')).sum().ge(cfg['hr']['min_valid_minutes'])
    per_day = coverage.groupby(coverage.index.date).sum() / (24 * 60 / cfg['hr']['window_minutes'])
    report = {'files': {k: len(v) for k, v in data.files.items()}, 'display_offset': str(data.timezone),
              'source_offset': data.source_offset, 'hrv_timezone_offset': best, 'hrv_sleep_shares': candidates,
              'hrv_anchor_sleep_shares': anchors[best], 'hrv_anchor': cfg['time']['hrv_window_anchor'],
              'hrv_rows_rejected': int(len(data.hrv) - len(hrv)), 'hrv_windows_per_night': per_night,
              'activity_levels': sorted(data.levels['level'].dropna().unique().tolist()),
              'exercise_checks': exercise_checks, 'steps_alignment_candidates': step_candidates,
              'steps_enabled_after_probe': bool(len(steps)),
              'steps_timezone_offset': step_offset,
              'days_available': [d.isoformat() for d in sorted(set(local.date))],
              'hr_coverage_percent': {d.isoformat(): round(float(v * 100), 2) for d, v in per_day.items()}}
    return report, hrv, steps
