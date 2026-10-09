from datetime import date, datetime, timedelta, timezone
from sleep_stage_ranges import SleepNight, StageSegment, stage_stats


def test_25_hour_sleep_partition_is_rejected():
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    end = start + timedelta(hours=25)
    night = SleepNight('synthetic', date(2026, 10, 7), start, end, 'STAGES', 'SUCCEEDED', True,
                       (StageSegment(start, end, 'light'),))
    stats, status = stage_stats(night)
    assert stats is None and status == 'invalid_stage_partition'
