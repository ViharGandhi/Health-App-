"""One daily RHR: nearest-sample time weighting over LIGHT/DEEP/REM stages."""
from datetime import datetime

from sleep_heart_rate import build_sleep_heart_rate
from sleep_stage_ranges import adapt_google_sleep, stage_stats, StageRangeConfig

METHOD = 'ASLEEP_TIME_WEIGHTED_V1'
MAX_SUPPORT_SECONDS = 30


def calculate_sleep_rhr(point, readings):
    """Clip sample support at stage boundaries; never bridge long device gaps.

    Neighboring samples split time at their midpoint. Each sample supports at
    most 30 seconds on either side, including at the sleep window boundaries.
    Short-awakening overlays are not separate AWAKE stages in this provider.
    """
    result = {'method': METHOD, 'value': None, 'sample_count': 0,
              'covered_seconds': 0.0, 'asleep_seconds': 0.0, 'status': 'no_stages'}
    if point is None:
        return result
    night = adapt_google_sleep(point)
    # RHR does not inherit the three-hour minimum used for stage baselines.
    stats, status = stage_stats(night, StageRangeConfig(min_sleep_hours=1 / 3600))
    if stats is None:
        result['status'] = status
        return result
    stages = [(s.start_utc.timestamp(), s.end_utc.timestamp()) for s in night.segments
              if s.stage in ('light', 'deep', 'rem')]
    result['asleep_seconds'] = sum(end - start for start, end in stages)
    observed = build_sleep_heart_rate(point, readings, False)
    samples = [(datetime.fromisoformat(s['timestamp']).timestamp(), s['bpm'])
               for s in observed['samples']]
    total = covered = 0.0
    count = 0
    for i, (stamp, bpm) in enumerate(samples):
        # Awake readings must not contribute even where their support would
        # cross into a neighboring asleep stage.
        stage = next(((start, end) for start, end in stages if start <= stamp < end), None)
        if stage is None:
            continue
        left = max(stage[0], stamp - MAX_SUPPORT_SECONDS,
                   (samples[i - 1][0] + stamp) / 2 if i else stage[0])
        right = min(stage[1], stamp + MAX_SUPPORT_SECONDS,
                    (stamp + samples[i + 1][0]) / 2 if i + 1 < len(samples) else stage[1])
        weight = max(0, right - left)
        total += bpm * weight
        covered += weight
        count += weight > 0
    result.update(sample_count=count, covered_seconds=covered,
                  value=total / covered if covered else None,
                  status='ok' if covered else 'no_readings')
    return result


def saved_rhr_points(rows):
    """Adapter for existing Health/Recovery consumers; these are local results."""
    points = []
    for day, payload in rows:
        if payload.get('value') is None:
            continue
        year, month, day_number = map(int, day.split('-'))
        points.append({'dailyRestingHeartRate': {
            'date': {'year': year, 'month': month, 'day': day_number},
            'beatsPerMinute': payload['value'],
            'dailyRestingHeartRateMetadata': {'calculationMethod': METHOD}}})
    return points
