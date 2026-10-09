import asyncio
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mock_sleep_stress import _raw_night
from sleep_stress import score_night
from sleep_stress_pipeline import compute_connected_sleep_stress
from sleep_stress_store import SleepStressStore
from test_sleep_stress import DAY, make_night, baseline_history


@pytest.mark.parametrize('failure', ['insufficient_baseline', 'no_valid_windows', 'pending_processing', 'short_sleep'])
def test_each_null_stress_has_a_reason(failure):
    current = make_night(DAY, [(40, 60, 5)] * 4)
    history = baseline_history()
    if failure == 'insufficient_baseline':
        history = []
    elif failure == 'no_valid_windows':
        current = replace(current, windows=())
    elif failure == 'pending_processing':
        current = replace(current, night=replace(current.night, processed=False))
    else:
        current = replace(current, night=replace(current.night, end_utc=current.night.start_utc + timedelta(hours=1)))
    result = score_night(current, history)
    assert result['stress_pct'] is None
    assert result['withheld_reason'] == failure


def test_missing_anchor_is_named_even_without_baseline(tmp_path):
    sleep, hrv, hr = _raw_night(DAY)
    source = SimpleNamespace(get_sleep_stress_points=AsyncMock(return_value=([sleep], hrv, hr)))
    results = asyncio.run(compute_connected_sleep_stress(source, DAY, DAY, None,
                           SleepStressStore(tmp_path / 'stress.sqlite3')))
    assert results[0]['stress_pct'] is None
    assert results[0]['withheld_reason'] == 'hrv_anchor_unconfigured'
    assert results[0]['anchor_verification'] == 'unconfigured'


def test_configured_anchor_is_operator_assertion(tmp_path):
    sleep, hrv, hr = _raw_night(DAY)
    source = SimpleNamespace(get_sleep_stress_points=AsyncMock(return_value=([sleep], hrv, hr)))
    result = asyncio.run(compute_connected_sleep_stress(source, DAY, DAY, 'start',
                          SleepStressStore(tmp_path / 'stress.sqlite3')))[0]
    assert result['anchor_verification'] == 'operator_configured'
    assert result['withheld_reason'] == 'insufficient_baseline'


def raw_series(shift=0, offset=0):
    sleeps, variability, heart = [], [], []
    zone = timezone(timedelta(hours=offset))
    def stamp(value):
        return value.astimezone(zone).isoformat()
    for back in range(8, -1, -1):
        day = DAY - timedelta(days=back)
        start = datetime.combine(day - timedelta(days=1), time(22), timezone.utc)
        end = start + timedelta(hours=6)
        sleeps.append({'name': f'synthetic-{day}', 'sleep': {
            'interval': {'startTime': stamp(start), 'endTime': stamp(end)},
            'type': 'STAGES', 'metadata': {'mainSleep': True, 'processed': True, 'stagesStatus': 'SUCCEEDED'},
            'stages': [{'startTime': stamp(start), 'endTime': stamp(end), 'type': 'LIGHT'}]}})
        for minute in range(0, 360, 5):
            tick = start + timedelta(minutes=minute)
            variability.append({'heartRateVariability': {
                'sampleTime': {'physicalTime': stamp(tick + timedelta(minutes=shift))},
                'rootMeanSquareOfSuccessiveDifferencesMilliseconds': 40.}})
        for minute in range(360):
            heart.append({'heartRate': {'sampleTime': {'physicalTime': stamp(start + timedelta(minutes=minute))},
                                       'beatsPerMinute': 60}})
    return sleeps, variability, heart


def pipeline_result(tmp_path, name, shift=0, offset=0):
    source = SimpleNamespace(get_sleep_stress_points=AsyncMock(return_value=raw_series(shift, offset)))
    return asyncio.run(compute_connected_sleep_stress(source, DAY, DAY, 'start',
                       SleepStressStore(tmp_path / (name + '.sqlite3'))))[0]


def test_configured_anchor_outside_sleep_bounds_withholds(tmp_path):
    result = pipeline_result(tmp_path, 'outside', shift=720)
    assert result['stress_pct'] is None
    assert result['withheld_reason'] == 'insufficient_baseline'
    assert result['coverage'] == 0
    assert result['anchor_verification'] == 'operator_configured'


def test_one_window_shift_is_not_empirically_detectable(tmp_path):
    result = pipeline_result(tmp_path, 'shift', shift=5)
    assert result['status'] == 'ok'
    assert result['anchor_verification'] == 'operator_configured'
    assert result['withheld_reason'] is None
    assert result['coverage'] < 1


def test_different_offsets_preserve_physical_alignment(tmp_path):
    utc = pipeline_result(tmp_path, 'utc')
    shifted = pipeline_result(tmp_path, 'offset', offset=-8)
    for result in (utc, shifted):
        result.pop('computed_at')
    assert utc == shifted
