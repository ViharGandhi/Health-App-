from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from sleep_stress import SleepNight, StageSegment, HrvWindow, HrSample, prepare_night, score_night


@pytest.mark.parametrize('problem', ['duplicate', 'overlap', 'outside', 'negative', 'unknown', 'too_long'])
def test_invalid_stage_partition_never_enters_stress_baseline(problem):
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    end = start + timedelta(hours=6)
    segment = StageSegment(start, end, 'LIGHT')
    segments = [segment]
    if problem == 'duplicate':
        segments.append(segment)
    elif problem == 'overlap':
        segments.append(replace(segment, start_utc=start + timedelta(hours=1)))
    elif problem == 'outside':
        segments[0] = replace(segment, end_utc=end + timedelta(hours=1))
    elif problem == 'negative':
        segments[0] = replace(segment, end_utc=start - timedelta(minutes=1))
    elif problem == 'unknown':
        segments[0] = replace(segment, stage='UNKNOWN')
    else:
        end = start + timedelta(hours=25)
        segments[0] = replace(segment, end_utc=end)
    night = SleepNight('synthetic', start.date(), start, end, 'STAGES', tuple(segments))
    windows = [HrvWindow(start, start + timedelta(minutes=5), 40.)]
    samples = [HrSample(start + timedelta(seconds=i), 60.) for i in range(300)]
    prepared = prepare_night(night, windows, samples)
    assert prepared.windows == ()
    assert 0 <= prepared.asleep_minutes <= (end - start).total_seconds() / 60
    result = score_night(prepared, [])
    assert result['stress_pct'] is None
    assert result['withheld_reason'] == 'invalid_stage_partition'
