"""Appearance anchors and held-out reference agreement, never accuracy claims."""
from copy import deepcopy

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import pearsonr
import yaml

from .pipeline import map_scores, score_export


def _fit(frame, cfg, residual, keys):
    c = cfg['calibration']
    bounds = {'k': c['k_bounds'], 'z_mid': c['z_mid_bounds'], 'w_hr_s': c['weight_bounds'],
              'w_hrv': c['weight_bounds'], 'w_ctx': c['context_weight_bounds']}
    initial = [cfg['score'][key] for key in keys]
    def candidate(values):
        trial = deepcopy(cfg)
        trial['score'].update({key: float(value) for key, value in zip(keys, values)})
        # Weights are normalized by the scoring formula; both zero is invalid.
        if trial['score']['w_hr_s'] + trial['score']['w_hrv'] == 0:
            trial['score']['w_hr_s'] = np.finfo(float).eps
        return trial
    result = least_squares(lambda values: residual(candidate(values)), initial,
                           bounds=([bounds[k][0] for k in keys], [bounds[k][1] for k in keys]),
                           max_nfev=c['fit_max_evaluations'])
    if not result.success:
        raise ValueError('Calibration did not converge: ' + result.message)
    return candidate(result.x), float(np.sqrt(np.mean(result.fun ** 2)))


def fit_anchors(frame, cfg):
    targets = cfg['calibration']['anchors']
    present = {state: target for state, target in targets.items()
               if ((frame['state'] == state) & frame['score'].notna()).any()}
    if len(present) < 2:
        raise ValueError('Anchor calibration needs at least two scored anchor states')
    trial = deepcopy(cfg)
    keys = ['k', 'z_mid']
    if (frame['state'].eq('ACTIVE') & frame['score'].notna()).sum() < cfg['calibration']['min_active_windows']:
        trial['score']['k'] = cfg['calibration']['sparse_active_k']
        keys = ['z_mid']
    def residual(c):
        score = map_scores(frame, c)[2]
        return np.array([np.nanmedian(score[frame['state'].eq(s)]) - t for s, t in present.items()])
    fitted, error = _fit(frame, trial, residual, keys)
    values = map_scores(frame, fitted)[2]
    return fitted, {'method': 'appearance anchors, not validation', 'fitted_parameters': keys, 'rmse': error,
                    'states': {s: {'target': t, 'fitted_median': float(np.nanmedian(values[frame['state'].eq(s)]))} for s, t in present.items()}}


def read_reference(path, cfg):
    frame = pd.read_csv(path, usecols=['timestamp', 'score'])
    if not frame['timestamp'].astype(str).str.contains(r'(?:Z|[+-]\d{2}:\d{2})$', regex=True).all():
        raise ValueError('Reference timestamps must include Z or an explicit UTC offset')
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], format='mixed', utc=True)
    frame['reference'] = pd.to_numeric(frame['score'], errors='raise')
    if not frame['reference'].between(0, cfg['score']['max_score']).all():
        raise ValueError('Reference scores must be finite and within 0–3')
    return frame[['timestamp', 'reference']].sort_values('timestamp').drop_duplicates('timestamp')


def pair_reference(features, reference, cfg):
    centers = features.index + pd.Timedelta(minutes=cfg['hr']['window_minutes'] / 2)
    candidates = pd.DataFrame({'center': centers, 'feature_timestamp': features.index,
                               'date': features['date'].to_numpy(), 'state': features['state'].to_numpy(),
                               'available': features['score'].notna().to_numpy()})
    pairs = pd.merge_asof(reference, candidates, left_on='timestamp', right_on='center', direction='nearest',
                          tolerance=pd.Timedelta(minutes=cfg['calibration']['reference_tolerance_minutes']))
    pairs = pairs[pairs['available'].eq(True)].dropna(subset=['feature_timestamp'])
    # Several digitized points in one window count as one observation.
    return pairs.groupby('feature_timestamp').agg(reference=('reference', 'mean'), date=('date', 'first'), state=('state', 'first'))


def metrics(pred, ref, states):
    valid = np.isfinite(pred) & np.isfinite(ref)
    pred, ref, states = np.asarray(pred)[valid], np.asarray(ref)[valid], np.asarray(states)[valid]
    r = float(pearsonr(pred, ref).statistic) if len(pred) > 1 and np.std(pred) > 0 and np.std(ref) > 0 else None
    return {'pairs': len(pred), 'pearson_r': r, 'mae': float(np.mean(abs(pred - ref))) if len(pred) else None,
            'mean_per_state': {s: {'prediction': float(pred[states == s].mean()), 'reference': float(ref[states == s].mean())}
                               for s in sorted(set(states))}}


def fit_reference(data, features, reference, cfg):
    pairs = pair_reference(features, reference, cfg)
    if len(pairs) < cfg['calibration']['min_reference_pairs']:
        raise ValueError('Too few matched scored reference windows for calibration')
    def fit(current, p, ablation='full'):
        trial = deepcopy(cfg)
        keys = ['k', 'z_mid']
        if p['date'].nunique() >= cfg['calibration']['reference_min_days_full_fit'] and ablation == 'full':
            keys += ['w_hr_s', 'w_hrv', 'w_ctx']
        # Refit k/z_mid for each ablation using training observations only.
        def residual(c):
            values = pd.Series(map_scores(current, c, ablation)[2], index=current.index).reindex(p.index)
            return (values - p['reference']).to_numpy()
        return _fit(current, trial, residual, keys)
    fitted, error = fit(features, pairs)
    cv = {name: [] for name in ('hr_only', 'sleep_hrv', 'full')}
    folds = []
    for held_out in sorted(pairs['date'].unique()):
        # Exclude the held-out day's HR and HRV from every fold baseline.
        fold_features, _ = score_export(data, cfg, excluded_baseline_days=[held_out])
        fold_pairs = pair_reference(fold_features, reference, cfg)
        train = fold_pairs[fold_pairs['date'].ne(held_out)]
        test = fold_pairs[fold_pairs['date'].eq(held_out)]
        if len(train) < cfg['calibration']['min_reference_pairs'] or test.empty:
            folds.append({'held_out_date': held_out, 'status': 'insufficient training or test data'})
            continue
        folds.append({'held_out_date': held_out, 'status': 'evaluated', 'training_pairs': len(train), 'test_pairs': len(test),
                      'held_out_day_excluded_from_baselines': True})
        for name in cv:
            fit_cfg, _ = fit(fold_features, train, name)
            prediction = pd.Series(map_scores(fold_features, fit_cfg, name)[2], index=fold_features.index).reindex(test.index)
            cv[name].append(pd.DataFrame({'prediction': prediction, 'reference': test['reference'], 'state': test['state']}))
    reports = {}
    for name, parts in cv.items():
        combined = pd.concat(parts) if parts else pd.DataFrame(columns=['prediction', 'reference', 'state'])
        reports[name] = metrics(combined['prediction'].to_numpy(dtype=float), combined['reference'].to_numpy(dtype=float), combined['state'])
    predicted = pd.Series(map_scores(features, fitted)[2], index=features.index).reindex(pairs.index)
    report = {'method': 'digitized reference agreement, not physiological validation', 'training_rmse': error,
              'reference_rows': len(reference), 'matched_unique_windows': len(pairs), 'reference_days': pairs['date'].nunique(),
              'full_weights_fitted': pairs['date'].nunique() >= cfg['calibration']['reference_min_days_full_fit'],
              'in_sample': metrics(predicted.to_numpy(), pairs['reference'].to_numpy(), pairs['state']),
              'leave_one_day_out': reports, 'folds': folds}
    return fitted, report


def write_config(path, fitted):
    with open(path, 'w', encoding='utf-8') as stream:
        yaml.safe_dump(fitted, stream, sort_keys=False)
