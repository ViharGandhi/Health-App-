import json

import numpy as np
import pandas as pd
import pytest
import yaml

from stressmon.__main__ import main
from stressmon.io import load_export, csv_read, alignment_probe
from stressmon.pipeline import preprocess_hr, score_export, smooth_scores, _references
from stressmon.calibration import fit_anchors, fit_reference


def test_synthetic_order_mask_and_wake_boundary(takeout, cfg):
    data = load_export(takeout, cfg)
    scores, report = score_export(data, cfg)
    averages = scores.groupby('state')['score'].mean()
    assert averages['SLEEP'] < averages['STILL'] < averages['ACTIVE']
    assert scores.loc[scores['state'].eq('EXERCISE'), 'score'].isna().all()
    assert scores.loc[scores['state'].eq('SLEEP'), 'z_hrv'].notna().any()
    assert report['hrv_timezone_offset'] == '+05:30'
    # Perturb awake HR only: sleep smoothing must be identical at wake-up.
    raw = scores['score_raw'].to_numpy().copy()
    before = smooth_scores(scores, raw, cfg)
    raw[scores['state'].ne('SLEEP') & np.isfinite(raw)] = 3
    after = smooth_scores(scores, raw, cfg)
    np.testing.assert_array_equal(before[scores['state'].eq('SLEEP')], after[scores['state'].eq('SLEEP')])


def test_alignment_quality_and_offwrist(takeout, cfg):
    data = load_export(takeout, cfg)
    data.hrv.loc[data.hrv.index[:7], 'coverage'] = .7
    cutoff = data.hr['timestamp'].min() + pd.Timedelta(hours=9)
    data.hr = data.hr[~data.hr['timestamp'].between(cutoff, cutoff + pd.Timedelta(minutes=30), inclusive='left')]
    scores, report = score_export(data, cfg)
    assert report['hrv_rows_rejected'] == 7
    assert (scores['state'] == 'OFFWRIST').sum() == 6
    assert scores.loc[scores['state'].eq('OFFWRIST'), 'score'].isna().all()
    assert report['hrv_sleep_shares']['+05:30'] > .9
    assert report['hrv_sleep_shares']['+00:00'] < .9


def test_unverified_anchor_never_pairs_sleep_hrv(takeout, cfg):
    cfg['time']['hrv_window_anchor'] = 'unverified'
    scores, report = score_export(load_export(takeout, cfg), cfg)
    assert scores['z_hrv'].isna().all()
    assert not report['within_sleep_hrv_enabled']
    assert scores.loc[scores['state'].ne('SLEEP'), 'z_night'].notna().any()


def test_duplicate_sleep_ids_do_not_inflate_nights(takeout, cfg):
    data = load_export(takeout, cfg)
    original, _ = score_export(data, cfg)
    duplicate = data.sleeps.copy()
    duplicate['sleep_id'] = duplicate['sleep_id'] + '-revision'
    data.sleeps = pd.concat([data.sleeps, duplicate], ignore_index=True)
    duplicated, report = score_export(data, cfg)
    np.testing.assert_array_equal(original['baseline_nights'], duplicated['baseline_nights'])
    np.testing.assert_array_equal(original['mu_x'], duplicated['mu_x'])
    assert all(night['valid_hrv_windows'] == 83 for night in report['hrv_windows_per_night'])


def test_causal_baseline_excludes_current_and_future_day(takeout, cfg):
    data = load_export(takeout, cfg)
    retrospective, _ = score_export(data, cfg)
    assert retrospective['baseline_leaks'].all()
    cfg['baselines']['mode'] = 'causal'
    causal, _ = score_export(data, cfg)
    for date, day in causal.groupby('date'):
        assert all(d < date for d in day['baseline_dates'].iloc[0].split('|') if d)
    assert not causal['baseline_leaks'].any()
    assert causal[causal['date'].eq('2026-10-01')]['score'].isna().all()
    # A huge target-date HR change must not move its HR baseline.
    target = data.hr['timestamp'].dt.tz_convert(data.timezone).dt.date.astype(str).eq('2026-10-05')
    data.hr.loc[target, 'hr'] += 20
    altered, _ = score_export(data, cfg)
    np.testing.assert_array_equal(causal[causal['date'].eq('2026-10-05')]['mu_hr'],
                                  altered[altered['date'].eq('2026-10-05')]['mu_hr'])
    assert causal['low_confidence'].all()


def test_missing_columns_and_privacy(tmp_path, takeout, cfg, monkeypatch):
    bad = tmp_path / 'bad.csv'
    bad.write_text('timestamp,unexpected\n2026-10-01T00:00:00Z,secret\n')
    with pytest.raises(ValueError, match='missing required column.*beats per minute'):
        csv_read(bad, 'hr')
    original = pd.read_csv
    seen = []
    def guarded(path, **kwargs):
        relative = str(path.relative_to(takeout))
        assert not any(forbidden in relative.lower() for forbidden in ['gps', 'profile', 'security'])
        if kwargs.get('nrows') != 0:
            assert 'usecols' in kwargs
            assert 'location_metadata' not in kwargs['usecols']
        seen.append(relative)
        return original(path, **kwargs)
    monkeypatch.setattr(pd, 'read_csv', guarded)
    data = load_export(takeout, cfg)
    assert seen
    assert not data.files['motion']


def test_exercise_buffer_and_short_awake(takeout, cfg):
    data = load_export(takeout, cfg)
    first = data.sleeps.iloc[0]
    stages = data.stages.iloc[[0]].copy()
    stages['stage'] = 'AWAKE'
    stages['start'] = first['start'] + pd.Timedelta(hours=3)
    stages['end'] = stages['start'] + pd.Timedelta(minutes=5)
    data.stages = pd.concat([data.stages, stages])
    scores, _ = score_export(data, cfg)
    awake = scores['short_awake']
    assert awake.sum() == 1
    assert scores.loc[awake, 'state'].eq('SLEEP').all()
    assert scores.loc[awake, 'z_hrv'].isna().all()
    run = data.exercises[data.exercises['activity_name'].str.contains('Run')].iloc[0]
    after = scores[(scores.index >= run['end']) & (scores.index < run['end'] + pd.Timedelta(minutes=20))]
    assert after['state'].eq('EXERCISE').all()


def test_live_ema_is_causal_and_gaps_reset(cfg):
    cfg['smoothing']['mode'] = 'live'
    frame = pd.DataFrame({'state': ['SLEEP'] * 4 + ['STILL'] * 4 + ['OFFWRIST'] + ['STILL'] * 4})
    values = np.array([.4] * 4 + [1.] * 4 + [np.nan] + [2.] * 4)
    baseline = smooth_scores(frame, values, cfg)
    changed = values.copy()
    changed[-1] = 0
    np.testing.assert_array_equal(baseline[:-1], smooth_scores(frame, changed, cfg)[:-1])
    assert baseline[4] == 1 and baseline[9] == 2 and np.isnan(baseline[8])


def test_offwrist_gap_not_aligned_to_five_minute_grid(takeout, cfg):
    data = load_export(takeout, cfg)
    lo = data.hr['timestamp'].min() + pd.Timedelta(hours=9, minutes=2)
    data.hr = data.hr[~data.hr['timestamp'].between(lo, lo + pd.Timedelta(minutes=5), inclusive='left')]
    scores, _ = score_export(data, cfg)
    assert scores.loc[lo.floor('5min'), 'state'] == 'OFFWRIST'
    assert np.isnan(scores.loc[lo.floor('5min'), 'score'])


def test_optional_motion_streams_still_only(tmp_path, cfg):
    from stressmon.io import _motion
    path = tmp_path / 'UserActivityProbabilities_synthetic.csv'
    payload = json.dumps({'ACTIVITY_PROBABILITY_TYPE_STILL': .9, 'ACTIVITY_PROBABILITY_TYPE_WALKING': .1})
    pd.DataFrame({'activity_probabilities_start': ['2026-10-01T00:00:00Z'],
                  'activity_probabilities_end': ['2026-10-01T00:00:01Z'],
                  'activity_probabilities': [payload]}).to_csv(path, index=False)
    cfg['motion']['chunk_rows'] = 1
    still = _motion([path], cfg)
    assert len(still) == 1 and still.iloc[0] == .9


def test_auto_switch_to_causal_and_holdout_does_not_change_policy(cfg):
    dates = pd.date_range('2026-10-01', periods=14, freq='1D').strftime('%Y-%m-%d')
    frame = pd.DataFrame({'date': dates, 'valid_minutes': 5})
    mode, refs = _references(frame, '2026-10-14', cfg, ['2026-10-05'])
    assert mode == 'causal'
    assert '2026-10-05' not in refs and '2026-10-14' not in refs


def test_anchor_fit_and_reference_cv(takeout, cfg):
    data = load_export(takeout, cfg)
    features, _ = score_export(data, cfg)
    fitted, report = fit_anchors(features, cfg)
    assert cfg['calibration']['k_bounds'][0] <= fitted['score']['k'] <= cfg['calibration']['k_bounds'][1]
    assert report['rmse'] < .25
    # Known synthetic reference is an algorithm check, not external validation.
    reference = pd.DataFrame({'timestamp': features.index + pd.Timedelta(minutes=2.5), 'reference': features['score'].to_numpy()})
    reference = reference[reference['reference'].notna()]
    fitted, report = fit_reference(data, features, reference, cfg)
    assert report['reference_days'] == 5
    assert len(report['folds']) == 5
    assert all(f['held_out_day_excluded_from_baselines'] for f in report['folds'])
    assert report['leave_one_day_out']['full']['pairs'] > 0
    assert report['in_sample']['mae'] < 1e-6
    assert set(report['leave_one_day_out']) == {'hr_only', 'sleep_hrv', 'full'}


def test_cli_csv_png_and_missing_file(takeout, cfg, tmp_path, capsys):
    config = tmp_path / 'config.yaml'
    config.write_text(yaml.safe_dump(cfg))
    output = tmp_path / 'out'
    args = ['--takeout', str(takeout), '--config', str(config), '--out', str(output)]
    assert main(['score', *args, '--date', '2026-10-05']) == 0
    summary = pd.read_csv(output / 'daily_summary.csv')
    assert len(summary) == 1 and summary.loc[0, 'coverage_percent'] < 100
    assert main(['plot', *args, '--date', '2026-10-05']) == 0
    from matplotlib.image import imread
    assert imread(output / 'stress_2026-10-05.png').shape[:2] == (900, 1600)
    assert main(['calibrate', *args, '--anchors']) == 0
    assert (output / 'calibration.json').exists()
    assert main(['probe', '--takeout', str(tmp_path / 'absent')]) == 2
    assert 'Missing required files' in capsys.readouterr().err


def test_ambiguous_hrv_offset_aborts(takeout, cfg):
    data = load_export(takeout, cfg)
    data.hrv['timestamp'] += pd.Timedelta(hours=10)
    with pytest.raises(ValueError, match='HRV timezone alignment failed'):
        alignment_probe(data, preprocess_hr(data, cfg), cfg)
