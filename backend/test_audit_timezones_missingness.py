from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from strain import calculate_strain, day_window
from sleep_stage_ranges import adapt_google_sleep, stage_stats
from sleep_stress import adapt_google_sleep as adapt_stress
from sleep_heart_rate import select_sleep
from recovery_score import recovery_from_history
from test_recovery_score import DAY, reference_history


@pytest.mark.parametrize('day,start_clock,end_clock,elapsed', [
    ('2026-10-25', '2026-10-25T02:58:00+02:00', '2026-10-25T02:02:00+01:00', 4),
    ('2026-03-29', '2026-03-29T01:58:00+01:00', '2026-03-29T03:02:00+02:00', 4)])
def test_hr_load_uses_physical_minutes_across_dst(day, start_clock, end_clock, elapsed):
    start, end = datetime.fromisoformat(start_clock), datetime.fromisoformat(end_clock)
    result = calculate_strain([(start, 160.), (end, 160.)], [], {'start': start, 'end': end}, 30, [56], 'm')
    assert result['counted_minutes'] == elapsed
    assert result['coverage'] == 1


@pytest.mark.parametrize('start,end,offset,day,hours', [
    ('2026-10-24T21:00:00Z', '2026-10-25T06:00:00Z', '3600s', '2026-10-25', 9),
    ('2026-03-28T22:00:00Z', '2026-03-29T05:00:00Z', '7200s', '2026-03-29', 7),
    ('2026-10-07T16:00:00Z', '2026-10-07T23:30:00Z', '19800s', '2026-10-08', 7.5)])
def test_sleep_wake_date_uses_device_offset_and_duration_uses_utc(start, end, offset, day, hours):
    point = {'name': 'synthetic', 'sleep': {'interval': {'startTime': start, 'endTime': end,
        'startUtcOffset': offset, 'endUtcOffset': offset}, 'type': 'STAGES',
        'metadata': {'processed': True, 'stagesStatus': 'SUCCEEDED', 'mainSleep': True},
        'stages': [{'startTime': start, 'endTime': end, 'type': 'LIGHT'}]}}
    night = adapt_google_sleep(point)
    stress = adapt_stress(point)
    stats, status = stage_stats(night)
    assert night.night_date == stress.night_date == date.fromisoformat(day)
    assert status == 'ok' and stats.total_minutes == hours * 60
    assert select_sleep([point], night.night_date, now=datetime(2026, 12, 1, tzinfo=timezone.utc)) == point
    # Activity-day timezone is independently user-selected; daily sleep stays device-local.
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    user_tz = ZoneInfo('America/Los_Angeles')
    activity_day = night.end_utc.astimezone(user_tz).date()
    window = day_window(activity_day, now, [{'start': night.start_utc, 'end': night.end_utc}], user_tz)
    assert window['start'].astimezone(timezone.utc) == night.end_utc


@pytest.mark.parametrize('count,recent', [(20, 7), (60, 4), (5, 5)])
def test_missing_reference_is_not_imputed(count, recent):
    result = recovery_from_history(reference_history(count, recent), DAY, 450, 450)
    assert result.status == 'building_reference' and result.percent is None


def test_gaps_and_device_stop_syncing_are_not_forward_filled():
    history = reference_history()
    history['hrv'] = [p for p in history['hrv'] if p['date'] != DAY.isoformat()]
    assert recovery_from_history(history, DAY).components['z_hrv'] == pytest.approx(0)
    stale = recovery_from_history(history, DAY + timedelta(days=8))
    assert stale.recent_nights == 0 and stale.percent is None


def test_only_a_nap_does_not_define_activity_day_window():
    start = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    window = day_window(start.date(), start + timedelta(hours=10), [{'start': start, 'end': start + timedelta(minutes=45), 'nap': True}], timezone.utc)
    assert window['source'] == 'midnight_fallback'
