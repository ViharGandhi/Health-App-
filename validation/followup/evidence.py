"""Offline diagnostic tables, adversarial profiles and full demo payloads."""
import asyncio
import ast
from collections import Counter
import csv
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
import math
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT), str(ROOT / 'validation')]
from fastapi.testclient import TestClient
from main import app, _compute_connected_recovery, _compute_real_sleep, _load_sleep_need_inputs
from mock_recovery import MockRecoveryClient, SCENARIOS
from recovery_score import recovery_from_history
from recovery import RecoveryCalculator, RecoveryInput
from sleep_need import calculate_sleep_need
from sleepscore import SleepCalculator
from health_trends import build_health_response
from strain import calculate_strain
from sleep_stress import score_night
from run_simulations import sleep_data, stress_night, cardio

DAY = date(2026, 10, 7)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def curve():
    points = []
    for i in range(8001):
        ratio = .5 + i * .0001
        raw = (100 / (1 + math.exp(-8 * (ratio - .75))) if ratio <= 1 else 100
               if ratio <= 1.1 else max(30, 100 - (ratio - 1.1) * 75))
        points.append({'ratio': ratio, 'old_duration': raw,
            'new_duration': SleepCalculator.compute_duration_score(ratio * 7.5, 7.5)})
    with (OUT / 'sleep-duration-curve.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=points[0].keys())
        writer.writeheader(); writer.writerows(points)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots(figsize=(10, 4.5), layout='constrained')
    for key, label, color in [('old_duration', 'Previous', '#a93226'), ('new_duration', 'Corrected', '#196f3d')]:
        axis.plot([p['ratio'] for p in points], [p[key] for p in points], label=label, color=color)
    axis.set(xlabel='Duration / required sleep', ylabel='Duration component (0–100)',
             title='Approved sleep-duration normalization', xlim=(.5, 1.3), ylim=(0, 105))
    axis.set_xticks([.5, .6, .75, .9, 1., 1.1, 1.3])
    axis.grid(alpha=.2)
    axis.legend()
    for suffix in ('svg', 'png'):
        figure.savefig(OUT / ('sleep-duration-curve.' + suffix), dpi=160)
    plt.close(figure)
    boundaries = []
    for boundary in (1., 1.1):
        for delta in (-1e-8, 0, 1e-8):
            ratio = boundary + delta
            boundaries.append({'ratio': ratio, 'component': SleepCalculator.compute_duration_score(ratio * 7.5, 7.5),
                'total_score': SleepCalculator.calculate_score(sleep_data(ratio * 7.5), 7.5, 45, 56, 72, 45, 56, 30)})
    save('sleep-boundaries.json', boundaries)
    weighting = []
    for name, prior, today in [('neutral', [40.] * 7, 40.), ('today +20%', [40.] * 7, 48.),
        ('today -20%', [40.] * 7, 32.), ('today doubled', [40.] * 7, 80.),
        ('one prior outlier', [80.] + [40.] * 6, 40.)]:
        old_signal = .7 * sum(math.log(v) for v in [today] + prior[:6]) / 7 + .3 * math.log(today)
        new_signal = .7 * sum(math.log(v) for v in prior) / 7 + .3 * math.log(today)
        weighting.append({'scenario': name, 'prior_hrv_ms': prior, 'today_hrv_ms': today,
            'reference_ms': 40., 'log_spread': .05, 'old_z_hrv': (old_signal - math.log(40)) / .05,
            'new_z_hrv': (new_signal - math.log(40)) / .05})
    save('recovery-weighting.json', weighting)


def replay():
    paths = ['/api/dashboard', '/api/strain', '/api/strain?demo=true', '/api/strain/analytics?demo=true',
        '/api/recovery', '/api/recovery?demo=estimate', '/api/recovery/analytics', '/api/recovery/analytics?demo=legacy',
        '/api/sleep', '/api/sleep/need', '/api/sleep/analytics', '/api/sleep/efficiency', '/api/sleep/consistency',
        '/api/sleep/consistency/score', '/api/sleep/stages/typical-ranges', '/api/sleep/stress', '/api/sleep/heart-rate',
        '/api/health', '/api/health/heart-rate']
    headers = {'X-User-Date': DAY.isoformat(), 'X-User-Age': '30', 'X-User-Sex': 'm', 'X-User-Timezone': 'Europe/Berlin'}
    responses = {}
    def block(*args, **kw):
        raise AssertionError('Outbound HTTP blocked')
    def nulls(value, path=''):
        if value is None: return [path]
        if isinstance(value, dict): return [p for k, v in value.items() for p in nulls(v, path + '/' + k)]
        if isinstance(value, list): return [p for i, v in enumerate(value) for p in nulls(v, f'{path}/{i}')]
        if isinstance(value, float): assert math.isfinite(value), path
        return []
    with patch('main._get_token', AsyncMock(return_value=None)), patch('main.get_session', return_value=None), \
         patch.object(httpx.AsyncClient, 'send', block), patch.object(httpx.HTTPTransport, 'handle_request', block):
        client = TestClient(app)
        for path in paths:
            result = client.get(path, headers=headers)
            body = result.json()
            assert result.status_code == 200, path
            responses[path] = {'status': result.status_code,
                'schema': {k: type(v).__name__ for k, v in body.items()}, 'null_fields': nulls(body), 'body': body}
        dashboard = responses['/api/dashboard']['body']
        for key in ('strain', 'sleep', 'recovery'):
            assert dashboard[key] == responses['/api/' + key]['body']
        assert dashboard['date'] == DAY.isoformat()
        assert responses['/api/recovery?demo=estimate']['body'] == responses['/api/recovery/analytics']['body']['current']
        for path in ('/api/health', '/api/health/heart-rate', '/api/sleep/need'):
            assert responses[path]['body']['date'] == DAY.isoformat()
        for path in ('/api/sleep/analytics', '/api/sleep/efficiency', '/api/sleep/consistency', '/api/sleep/stress', '/api/health'):
            assert responses[path]['body']['range_end'] == DAY.isoformat()
        for timeframe in ('W', 'M', '6M'):
            for path in ('/api/strain/analytics', '/api/recovery/analytics', '/api/sleep/analytics'):
                result = client.get(path, headers=headers, params={'timeframe': timeframe})
                assert result.status_code == 200
                nulls(result.json())
        for headers_change in ({'X-User-Date': 'bad'}, {'X-User-Age': '101'}, {'X-User-Timezone': 'bad'}):
            merged = {**headers, **headers_change}
            assert client.get('/api/dashboard', headers=merged).status_code == 400
    save('demo-replay.json', {'headers': headers, 'outbound_http': 'blocked', 'routes': responses,
        'checks': ['dashboard/detail exact agreement', 'estimate/current exact agreement',
                   'selected dates', 'W/M/6M serialization', 'invalid header rejection', 'all numbers finite']})


async def profiles():
    rows = []
    specs = [('fit', 30, 90., 45., 470., False), ('older', 70, 44., 55., 470., False),
        ('sedentary', 30, 35., 72., 470., False), ('sleep_deprived', 30, 44., 55., 270., False),
        ('illness', 30, 44., 55., 470., False), ('new_user', 30, 44., 55., 470., True),
        ('irregular_schedule', 30, 44., 55., 470., False)]
    for name, age, hrv, rhr, minutes, new_user in specs:
        client = MockRecoveryClient(DAY)
        for kind, points in client.points.items():
            for point in points:
                if kind.startswith('daily'):
                    value = next(iter(point.values()))
                    when = date(**value['date'])
                    offset = (DAY - when).days
                    if kind == 'daily-heart-rate-variability':
                        value['averageHeartRateVariabilityMilliseconds'] = hrv * (1 + .03 * math.sin(offset))
                        if name == 'illness' and offset <= 6: value['averageHeartRateVariabilityMilliseconds'] *= .8
                    elif kind == 'daily-resting-heart-rate':
                        value['beatsPerMinute'] = str(rhr + round(math.sin(offset)))
                        if name == 'illness' and offset <= 6: value['beatsPerMinute'] = str(rhr + 5)
                    elif kind == 'daily-sleep-temperature-derivations' and name == 'illness' and offset == 0:
                        value['nightlyTemperatureCelsius'] = 35.
                elif kind == 'sleep' and not point['sleep']['metadata'].get('nap'):
                    sleep = point['sleep']
                    sleep['summary']['minutesAsleep'] = str(minutes)
                    sleep['summary']['minutesAwake'] = str(540 - minutes)
                    sleep['summary']['stagesSummary'] = [{'type': s, 'minutes': minutes * share, 'count': 1}
                        for s, share in [('DEEP', .2), ('REM', .2), ('LIGHT', .6)]]
                    if name == 'irregular_schedule':
                        offset = (DAY - datetime.fromisoformat(sleep['interval']['endTime'].replace('Z', '+00:00')).date()).days
                        for edge in ('startTime', 'endTime'):
                            stamp = datetime.fromisoformat(sleep['interval'][edge].replace('Z', '+00:00'))
                            sleep['interval'][edge] = (stamp + timedelta(minutes=120 * (-1) ** offset)).isoformat()
        if new_user:
            for kind in client.points:
                if kind.startswith('daily'):
                    client.points[kind] = [p for p in client.points[kind] if (DAY - date(**next(iter(p.values()))['date'])).days <= 4]
        with patch.object(httpx.AsyncClient, 'send', side_effect=AssertionError('Outbound HTTP')):
            connected = await _compute_connected_recovery(client, DAY, age)
            inputs = await _load_sleep_need_inputs(client, DAY, age)
            need = inputs.for_tonight(DAY - timedelta(days=1))
            sleep = await _compute_real_sleep(client, DAY, need, age)
        start = datetime(2026, 10, 7, 7, tzinfo=timezone.utc)
        load = calculate_strain([(start + timedelta(minutes=i), 160.) for i in range(46)], [],
            {'start': start, 'end': start + timedelta(minutes=45)}, age, [rhr], 'm')
        bad_rhr = calculate_strain([(start, 160.), (start + timedelta(minutes=1), 160.)], [],
            {'start': start, 'end': start + timedelta(minutes=1)}, age, [1000.], 'm')
        invalid_history = {'hrv': [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': -1.} for i in range(1, 8)]}
        health = build_health_response(invalid_history, [], DAY, DAY, 'W', True)
        current = stress_night(DAY, [(hrv * .5, rhr + 15, 5)] * 72)
        prior = stress_night(DAY - timedelta(days=1), [(hrv, rhr, 5)] * 72)
        stress = score_night(current, [prior] * 7, computed_at=start)
        flat = {'hrv': [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': hrv} for i in range(1, 68)]}
        flat['hrv'].append({'date': DAY.isoformat(), 'value': hrv * 1.2})
        weight_z = recovery_from_history(flat, DAY).components['z_hrv']
        gates = {'duration_jump': SleepCalculator.compute_duration_score(7.500001, 7.5) - SleepCalculator.compute_duration_score(7.5, 7.5),
            'stress_unique_nights': stress['baseline']['nights_used'], 'invalid_health_baseline': health.metrics['hrv'][0].baseline,
            'bad_rhr_fallback': bad_rhr['params']['hr_rest'], 'bad_rhr_calibrating': bad_rhr['calibrating'],
            'today_20pct_z': weight_z}
        assert gates['duration_jump'] == 0 and gates['stress_unique_nights'] == 1
        assert gates['invalid_health_baseline'] is None and gates['bad_rhr_fallback'] == 60 and gates['bad_rhr_calibrating']
        assert math.isclose(weight_z, .3 * math.log(1.2) / .05, abs_tol=1e-12)
        rows.append({'profile': name, 'synthetic': True, 'inputs': {'age': age, 'usual_hrv_ms': hrv, 'usual_rhr_bpm': rhr, 'sleep_minutes': minutes},
            'recovery': connected.model_dump(), 'sleep_score': sleep.score, 'sleep_need': asdict(need) if need else None,
            'cardio_strain_at_160bpm_45min': load['strain'], 'five_fix_probes': gates,
            'consistency_minutes': sleep.consistency_minutes})
    deprived = next(r for r in rows if r['profile'] == 'sleep_deprived')
    assert deprived['recovery']['components']['sleep_adj'] < 0
    assert next(r for r in rows if r['profile'] == 'illness')['recovery']['illness_flag']
    assert next(r for r in rows if r['profile'] == 'new_user')['recovery']['status'] == 'building_reference'
    save('adversarial-profiles.json', rows)
    examples = []
    for scenario in SCENARIOS:
        client = MockRecoveryClient(DAY, scenario)
        result = await _compute_connected_recovery(client, DAY, 30)
        examples.append({'scenario': scenario, 'result': result.model_dump(), 'range_fetches': len(client.calls)})
    save('connected-demo-scenarios.json', examples)
    compared = []
    for row in rows:
        current = row['recovery']
        inp = row['inputs']
        legacy = RecoveryCalculator.calculate(RecoveryInput(today_hrv=current['today_hrv'], hrv_baseline=inp['usual_hrv_ms'],
            today_rhr=current['today_rhr'], rhr_baseline=inp['usual_rhr_bpm'], sleep_score=row['sleep_score'] or 0.,
            yesterday_strain=row['cardio_strain_at_160bpm_45min'], hrv_history=[inp['usual_hrv_ms']] * 14))
        compared.append({'profile': row['profile'], 'legacy': legacy, 'connected': {'percent': current['percent'],
            'z': current['z'], 'status': current['status'], 'components': current['components']},
            'interpretation': 'Same current vitals; legacy uses scalar fallback on this flat prior series and composite sleep/strain; connected uses robust long reference and duration modifier.'})
    save('legacy-vs-connected.json', compared)


def constants():
    modules = ['strain.py', 'sleepscore.py', 'recovery.py', 'sleep_consistency.py', 'sleep_efficiency.py',
        'backend/recovery_score.py', 'backend/sleep_need.py', 'backend/sleep_need_inputs.py', 'backend/sleep_stress.py',
        'backend/sleep_stage_ranges.py', 'backend/health_trends.py', 'backend/sleep_trends.py', 'backend/strain_analytics.py',
        'backend/recovery_analytics.py', 'backend/sleep_analytics.py', 'backend/main.py', 'backend/strain_service.py',
        'backend/google_health_client.py', 'backend/sleep_heart_rate.py']
    values = []
    for name in modules:
        path = ROOT / name
        source = path.read_text(encoding='utf-8-sig')
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                line = lines[node.lineno - 1].strip()
                values.append({'source': name, 'line': node.lineno, 'literal': node.value, 'context': line,
                    'comment': line.split('#', 1)[1].strip() if '#' in line else None,
                    'status': 'needs validation / provenance review',
                    'note': 'Conservative inventory includes mathematical scales, units and control limits; those need dimensional review, not clinical calibration.'})
    save('numeric-constants.json', values)
    grouped = Counter(v['source'] for v in values)
    (OUT / 'constants-inventory.md').write_text('# Numeric constants and provenance\n\n'
        'Every numeric literal in the listed computation/adaptation layers is inventoried, including inline values and defaults. '
        'Comments explain intent; they do not establish empirical validity. Zero/one, seconds-per-minute, normalization scales, '
        'calendar counts and cache limits are included conservatively and need dimensional/engineering review rather than physiological calibration. '
        'Scoring coefficients and cutoffs need held-out outcome validation. No coefficients were retuned.\n\n'
        '| Source | Literals |\n|---|---:|\n' + '\n'.join(f'| {s} | {n} |' for s, n in grouped.items())
        + '\n\nFull line-level context and nearby inline comments: numeric-constants.json.\n')


if __name__ == '__main__':
    curve()
    replay()
    asyncio.run(profiles())
    constants()
    print('Exported curve, weighting, demo replay, adversarial profiles, legacy comparisons and numeric constant inventory.')
