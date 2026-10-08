from datetime import datetime, timedelta, timezone

import pytest

from sleep_stress import HrSample, HrvWindow, SleepNight, StageSegment, prepare_night


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), 0., -1.])
def test_nonfinite_or_nonpositive_hrv_cannot_enter_stress_reference(value):
    start = datetime(2026, 10, 7, 22, tzinfo=timezone.utc)
    end = start + timedelta(hours=6)
    night = SleepNight('synthetic', end.date(), start, end, 'STAGES',
                       (StageSegment(start, end, 'LIGHT'),))
    samples = [HrSample(start + timedelta(seconds=i * 30), 60.) for i in range(10)]
    result = prepare_night(night, [HrvWindow(start, start + timedelta(minutes=5), value)], samples)
    assert result.windows == ()
    assert result.coverage == 0.
