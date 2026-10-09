"""Reproducible offline hardening evidence; never contacts a provider."""
import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'final'
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT), str(ROOT / 'validation')]
spec = importlib.util.spec_from_file_location('original_evidence', ROOT / 'validation/followup/evidence.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
original.OUT = OUT

import httpx
from main import _compute_connected_recovery, _compute_real_sleep, _load_sleep_need_inputs
from mock_recovery import MockRecoveryClient
from recovery_score import recovery_from_history
from health_trends import build_health_response
from strain import calculate_strain
from strain_service import strain_response
from sleep_stress import score_night, prepare_night, adapt_google_hrv
from sleep_stress_pipeline import compute_connected_sleep_stress
from sleep_stress_store import SleepStressStore
from mock_sleep_stress import _raw_night
from sleepscore import SleepCalculator
from validity import finite_median, valid_metric
from run_simulations import stress_night

DAY = original.DAY


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def clock(point, kind):
    value = next(v for k, v in point.items() if k != 'name')
    if 'date' in value:
        from datetime import date
        return date(**value['date'])
    stamp = value['sampleTime']['physicalTime'] if kind == 'heart-rate' else value['interval']['endTime' if kind == 'sleep' else 'startTime']
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).date()


async def extra_profiles():
    rows = json.loads((OUT / 'adversarial-profiles.json').read_text())
    for name in ('stopped_sync_10_days', 'remote_timezone'):
        client = MockRecoveryClient(DAY)
        if name == 'stopped_sync_10_days':
            cutoff = DAY - timedelta(days=10)
            for kind in client.points:
                client.points[kind] = [p for p in client.points[kind] if clock(p, kind) <= cutoff]
        else:
            client.strain_timezone = timezone(timedelta(hours=-8))
            for kind in ('sleep', 'heart-rate', 'exercise'):
                for point in client.points[kind]:
                    value = next(v for k, v in point.items() if k != 'name')
                    if kind == 'heart-rate':
                        value['sampleTime']['utcOffset'] = '7200s'
                    else:
                        value['interval'].update(startUtcOffset='7200s', endUtcOffset='7200s')
        with patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', side_effect=AssertionError('Outbound HTTP blocked')):
            recovery = await _compute_connected_recovery(client, DAY, 30)
            inputs = await _load_sleep_need_inputs(client, DAY, 30)
            need = inputs.for_tonight(DAY - timedelta(days=1))
            sleep = await _compute_real_sleep(client, DAY, need, 30)
        timing = {}
        if name == 'remote_timezone':
            end = datetime.fromisoformat(client.points['sleep'][0]['sleep']['interval']['endTime'].replace('Z', '+00:00'))
            device = end.astimezone(timezone(timedelta(hours=2)))
            user = end.astimezone(client.strain_timezone)
            timing = dict(device_offset_hours=2, request_offset_hours=-8,
                          device_wake_date=device.date().isoformat(), user_wake_date=user.date().isoformat(),
                          physical_instant_preserved=device == user,
                          wake_dates_differ=device.date() != user.date(),
                          contract='Provider civil wake date selects summary sleep; activity-day boundaries use request timezone.')
            assert timing['physical_instant_preserved'] and timing['wake_dates_differ']
        else:
            assert recovery.percent is None and recovery.status_reason
            assert sleep.score is None and sleep.status_reason
            assert recovery.recent_nights == 0
        start = datetime(2026, 10, 7, 7, tzinfo=timezone.utc)
        load = calculate_strain([(start + timedelta(minutes=i), 160.) for i in range(46)], [],
            {'start': start, 'end': start + timedelta(minutes=45)}, 30, [55.], 'm')
        rows.append(dict(profile=name, synthetic=True,
            inputs=dict(age=30, usual_hrv_ms=44., usual_rhr_bpm=55., sleep_minutes=470.),
            recovery=recovery.model_dump(), sleep_score=sleep.score, sleep_response=sleep.model_dump(),
            sleep_need=asdict(need) if need else None, cardio_strain_at_160bpm_45min=load['strain'],
            consistency_minutes=sleep.consistency_minutes, timezone_checks=timing))
    for row in rows:
        age, hrv, rhr = (row['inputs'][key] for key in ('age', 'usual_hrv_ms', 'usual_rhr_bpm'))
        start = datetime(2026, 10, 7, 7, tzinfo=timezone.utc)
        current = stress_night(DAY, [(hrv * .5, rhr + 15, 5.)] * 72)
        prior = stress_night(DAY - timedelta(days=1), [(hrv, rhr, 5.)] * 72)
        stress = score_night(current, [prior] * 7, computed_at=start)
        flat = {'hrv': [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': hrv} for i in range(1, 68)]}
        flat['hrv'].append({'date': DAY.isoformat(), 'value': hrv * 1.2})
        bad = calculate_strain([(start, 160.), (start + timedelta(minutes=1), 160.)], [],
            {'start': start, 'end': start + timedelta(minutes=1)}, age, [1000.], 'm')
        invalid = {'hrv': [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': -1.} for i in range(1, 8)]}
        row['five_fix_probes'] = dict(duration_jump=SleepCalculator.compute_duration_score(7.500001, 7.5) - SleepCalculator.compute_duration_score(7.5, 7.5),
            stress_unique_nights=stress['baseline']['nights_used'],
            invalid_health_baseline=build_health_response(invalid, [], DAY, DAY, 'W', True).metrics['hrv'][0].baseline,
            bad_rhr_fallback=bad['params']['hr_rest'], bad_rhr_calibrating=bad['calibrating'],
            today_20pct_z=recovery_from_history(flat, DAY).components['z_hrv'])
        probes = row['five_fix_probes']
        assert probes['duration_jump'] == 0 and probes['stress_unique_nights'] == 1
        assert probes['invalid_health_baseline'] is None and probes['bad_rhr_fallback'] == 60 and probes['bad_rhr_calibrating']
        assert math.isclose(probes['today_20pct_z'], .3 * math.log(1.2) / .05, abs_tol=1e-12)
        bad['strain'] = 16.86
        bad.update(date=DAY, day_window={'start': start, 'end': start + timedelta(minutes=1)})
        model = strain_response(bad, {DAY: bad}, 'demo', age)
        partition = replace(current.night, stages=())
        invalid_night = prepare_night(partition, [], [])
        raw_sleep, raw_hrv, raw_hr = _raw_night(DAY)
        source = SimpleNamespace(get_sleep_stress_points=AsyncMock(return_value=([raw_sleep], raw_hrv, raw_hr)))
        with tempfile.TemporaryDirectory() as directory:
            withheld = (await compute_connected_sleep_stress(source, DAY, DAY, None,
                SleepStressStore(Path(directory) / 'stress.db')))[0]
        raw_hrv[0]['heartRateVariability']['rootMeanSquareOfSuccessiveDifferencesMilliseconds'] = True
        try:
            adapt_google_hrv(raw_hrv, 'start')
        except ValueError:
            boolean_sample_rejected = True
        else:
            boolean_sample_rejected = False
        assert boolean_sample_rejected
        row['hardening_probes'] = dict(boolean_hrv_rejected=not valid_metric('hrv', True),
            sample_hrv_201_rejected=not valid_metric('sample_hrv', 201.),
            vo2_101_rejected=not valid_metric('vo2_max', 101.), daily_hrv_1e9_remains_unbounded=valid_metric('hrv', 1e9),
            stable_even_median=finite_median([1.79e308] * 2),
            json_strain=model.model_dump(mode='json')['strain'], model_strain=model.strain,
            partition_withheld_reason=invalid_night.withheld_reason,
            missing_anchor_withheld_reason=withheld['withheld_reason'], boolean_sample_rejected=boolean_sample_rejected)
        assert row['hardening_probes']['json_strain'] == 16.8 and model.strain == 16.9
        assert invalid_night.withheld_reason and withheld['withheld_reason']
    save('adversarial-profiles.json', rows)
    save('profile-summary.json', [dict(profile=r['profile'], recovery=r['recovery']['percent'],
        recovery_status=r['recovery']['status'], recovery_reason=r['recovery']['status_reason'],
        sleep_score=r['sleep_score'], need_minutes=r['sleep_need']['total_need_min'] if r['sleep_need'] else None,
        strain=r['cardio_strain_at_160bpm_45min']) for r in rows])


def run():
    OUT.mkdir(exist_ok=True)
    original.curve()
    svg = OUT / 'sleep-duration-curve.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')
    original.replay()
    asyncio.run(original.profiles())
    asyncio.run(extra_profiles())
    original.constants()
    print('Offline evidence: 19 demo routes, W/M/6M replays, 9 profiles, 5 original and 9 hardening probes per profile.')


if __name__ == '__main__':
    run()
