"""UTC feature extraction, auditable baselines and gap-preserving scoring."""
import re

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.signal import savgol_filter

from .io import alignment_probe, sleep_membership


def preprocess_hr(data, cfg):
    h = cfg['hr']
    parts = []
    source = data.hr[data.hr['hr'].between(h['min_bpm'], h['max_bpm'])].set_index('timestamp')['hr']
    # Filtering never borrows observations from another display date.
    for _, values in source.groupby(source.index.tz_convert(data.timezone).date):
        a = values.to_numpy()
        n = h['hampel_samples']
        pad = (n - 1, 0) if cfg['smoothing']['mode'] == 'live' else (n // 2, n // 2)
        windows = np.lib.stride_tricks.sliding_window_view(np.pad(a, pad, mode='edge'), n)
        med = np.median(windows, axis=1)
        mad = np.median(np.abs(windows - med[:, None]), axis=1)
        keep = np.abs(a - med) <= h['hampel_mads'] * h['mad_scale'] * mad
        parts.append(values[keep])
    if not parts:
        raise ValueError('No physiologically valid HR samples')
    clean = pd.concat(parts).sort_index()
    minute = clean.resample('1min').agg(['median', 'count']).rename(columns={'median': 'hr', 'count': 'samples'})
    minute.loc[minute['samples'] < h['min_samples_per_minute'], 'hr'] = np.nan
    start = data.hr['timestamp'].min().tz_convert(data.timezone).normalize().tz_convert('UTC')
    end = data.hr['timestamp'].max().ceil('1min')
    return minute.reindex(pd.date_range(start, end, freq='1min', inclusive='left'))


def robust(values, floor, cfg):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return np.nan, np.nan
    mu = float(np.median(a))
    return mu, max(cfg['hr']['mad_scale'] * float(np.median(np.abs(a - mu))), floor)


def _nights(data, minute, hrv, cfg):
    rows = []
    for s in data.sleeps.itertuples():
        series = minute.loc[(minute.index >= s.start) & (minute.index < s.end), 'hr']
        rhr = series.rolling(cfg['physiology']['rhr_rolling_minutes'],
                             min_periods=cfg['physiology']['rhr_min_valid_minutes']).mean().min()
        x = hrv.loc[hrv['timestamp'].between(s.start, s.end, inclusive='left'), 'x'].median()
        rows.append({'sleep_id': s.sleep_id, 'start': s.start, 'end': s.end,
                     'date': s.end.tz_convert(data.timezone).date().isoformat(), 'rhr': rhr, 'x': x})
    sessions = pd.DataFrame(rows, columns=['sleep_id', 'start', 'end', 'date', 'rhr', 'x'])
    nights = []
    for date, group in sessions.groupby('date'):
        # Revised/overlapping sleep IDs must not count as independent nights.
        included = sleep_membership(hrv['timestamp'], group)
        nights.append({'date': date, 'end': group['end'].max(), 'rhr': group['rhr'].min(),
                       'x': hrv.loc[included, 'x'].median()})
    return pd.DataFrame(nights, columns=['date', 'end', 'rhr', 'x'])


def _base_states(data, minute, steps, cfg):
    width = cfg['hr']['window_minutes']
    # Offset-local grids are essential for offsets that are not whole hours.
    local = minute.copy()
    local.index = local.index.tz_convert(data.timezone)
    agg = local.resample(f'{width}min').agg(hr=('hr', 'median'), valid_minutes=('hr', 'count'), samples=('samples', 'sum'))
    agg.index = agg.index.tz_convert('UTC')
    agg.loc[agg['valid_minutes'] < cfg['hr']['min_valid_minutes'], 'hr'] = np.nan
    agg['end'] = agg.index + pd.Timedelta(minutes=width)
    cutoff = data.hr['timestamp'].max() + pd.Timedelta(seconds=1)
    agg['duration_minutes'] = np.minimum(width, np.maximum(0, (cutoff - agg.index).total_seconds() / 60))
    agg['date'] = [v.isoformat() for v in agg.index.tz_convert(data.timezone).date]
    level = data.levels.set_index('timestamp')['level'].reindex(minute.index)
    sedentary = level.eq(cfg['states']['sedentary_level'])
    active = level.notna() & ~sedentary
    if len(steps):
        active |= steps.reindex(minute.index).ge(cfg['steps']['active_steps_per_minute'])
    if len(data.motion):
        sedentary &= data.motion.reindex(minute.index).ge(cfg['motion']['still_probability'])
    prev = cfg['states']['still_previous_minutes']
    prior_still = sedentary.rolling(width + prev, min_periods=width + prev).sum().eq(width + prev)
    active.index = active.index.tz_convert(data.timezone)
    prior_still.index = prior_still.index.tz_convert(data.timezone)
    is_active = active.resample(f'{width}min').max().to_numpy()
    is_still = prior_still.resample(f'{width}min').last().to_numpy()
    agg['state'] = np.where(is_active, 'ACTIVE', np.where(is_still, 'STILL', 'AMBIG'))
    centers = agg.index + pd.Timedelta(minutes=width / 2)
    sleeping = sleep_membership(centers, data.sleeps)
    agg.loc[sleeping, 'state'] = 'SLEEP'
    agg['sleep_id'] = None
    for s in data.sleeps.itertuples():
        agg.loc[(centers >= s.start) & (centers < s.end), 'sleep_id'] = s.sleep_id
    agg['short_awake'] = False
    for s in data.stages[data.stages['stage'].astype(str).str.upper().eq('AWAKE')].itertuples():
        inside = (centers >= s.start) & (centers < s.end)
        if (s.end - s.start).total_seconds() / 60 < cfg['states']['short_awake_minutes']:
            agg.loc[inside, 'short_awake'] = True
        else:
            agg.loc[inside, 'state'] = 'STILL'
    for e in data.exercises.itertuples():
        inside = (centers >= e.start) & (centers < e.end) & ~sleeping
        agg.loc[inside, 'state'] = 'ACTIVE'
    absent = minute['samples'].fillna(0).eq(0)
    runs = absent.ne(absent.shift()).cumsum()
    for _, gap in absent[absent].groupby(runs[absent]):
        if len(gap) >= width:
            lo, hi = gap.index[0], gap.index[-1] + pd.Timedelta(minutes=1)
            agg.loc[(centers >= lo) & (centers < hi), 'state'] = 'OFFWRIST'
    return agg


def _references(frame, date, cfg, excluded):
    available = sorted(set(frame.loc[frame['valid_minutes'].ge(cfg['hr']['min_valid_minutes']), 'date']))
    days = sorted(set(available) - set(excluded))
    mode = cfg['baselines']['mode']
    if mode == 'auto':
        mode = 'causal' if len(available) >= cfg['baselines']['window_days'] else 'retrospective'
    eligible = [d for d in days if d < date] if mode == 'causal' else days
    # Retrospective is a bounded calendar neighbourhood, explicitly non-causal.
    if mode == 'retrospective':
        eligible = sorted(eligible, key=lambda d: (abs((pd.Timestamp(d) - pd.Timestamp(date)).days), d))
    refs = sorted(eligible[:cfg['baselines']['window_days']] if mode == 'retrospective'
                  else eligible[-cfg['baselines']['window_days']:])
    return mode, refs


def _physiology(data, minute, nights, refs, cfg):
    reference_nights = nights[nights['date'].isin(refs)]
    rhr = reference_nights['rhr'].median()
    age = cfg['physiology']['age']
    if age is None:
        local_days = pd.Index([d.isoformat() for d in minute.index.tz_convert(data.timezone).date])
        hrmax = minute.loc[local_days.isin(refs), 'hr'].quantile(cfg['physiology']['hrmax_percentile'])
    else:
        hrmax = cfg['physiology']['hrmax_intercept'] - cfg['physiology']['hrmax_age_slope'] * age
    return rhr, hrmax


def _exercise_masks(frame, data, rhr, hrmax, cfg, still=None):
    centers = frame.index + pd.Timedelta(minutes=cfg['hr']['window_minutes'] / 2)
    mask = np.zeros(len(frame), dtype=bool)
    for e in data.exercises.itertuples():
        name = str(e.activity_name).lower()
        vigorous = any(re.search(r'\b' + re.escape(v), name) for v in cfg['states']['vigorous_names'])
        vigorous |= bool(np.isfinite(rhr) and np.isfinite(hrmax) and
                         e.tracker_avg_heart_rate >= rhr + cfg['states']['exercise_mask_hrr'] * (hrmax - rhr))
        if not vigorous:
            continue
        end = e.end + pd.Timedelta(minutes=cfg['states']['post_exercise_buffer_min'])
        cap = e.end + pd.Timedelta(minutes=cfg['states']['post_exercise_max_min'])
        if still is not None and np.isfinite(still[0]):
            after = frame.loc[(frame.index >= end) & (frame.index <= cap), 'hr']
            returned = after[abs(after - still[0]) <= cfg['states']['return_to_still_sigmas'] * still[1]]
            end = returned.index[0] if len(returned) else cap
        mask |= (centers >= e.start) & (centers < end)
    return mask & ~frame['state'].isin(['SLEEP', 'OFFWRIST']).to_numpy()


def _paired_hrv(frame, hrv, cfg):
    result = pd.Series(np.nan, index=frame.index)
    anchor = cfg['time']['hrv_window_anchor']
    if anchor == 'unverified':
        return result
    width = cfg['hr']['window_minutes']
    stamps = pd.DatetimeIndex(hrv['timestamp'])
    if anchor == 'end':
        stamps -= pd.Timedelta(minutes=width)
    # Pair by measurement midpoint; reject any window crossing a sleep boundary.
    centers = stamps + pd.Timedelta(minutes=width / 2)
    asleep = frame['state'].eq('SLEEP')
    segments = (asleep.ne(asleep.shift()) | frame['sleep_id'].ne(frame['sleep_id'].shift())).cumsum()
    for _, group in frame[asleep].groupby(segments[asleep]):
        lo, hi = group.index.min(), group['end'].max()
        valid = (stamps >= lo) & (stamps + pd.Timedelta(minutes=width) <= hi)
        series = pd.Series(hrv.loc[valid, 'x'].to_numpy(), index=centers[valid])
        if not len(series):
            continue
        series = series.resample(f'{width}min', origin=lo).mean().reindex(group.index)
        series = series.where(~group['short_awake'])
        n = cfg['hrv']['smoothing_neighbours']
        live = cfg['smoothing']['mode'] == 'live'
        smoothed = series.rolling(n + 1 if live else 2 * n + 1, center=not live, min_periods=1).mean()
        # Missing central measurements remain HR-only, even if neighbours exist.
        result.loc[group.index] = smoothed.where(series.notna()).to_numpy()
    return result.where(~frame['short_awake'])


def smooth_scores(frame, raw, cfg):
    out = np.full(len(frame), np.nan)
    classes = np.where(frame['state'].eq('SLEEP'), 'SLEEP', 'AWAKE')
    classes[~np.isfinite(raw)] = 'GAP'
    cuts = np.r_[0, np.flatnonzero(classes[1:] != classes[:-1]) + 1, len(frame)]
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        if classes[lo] == 'GAP':
            continue
        a = np.asarray(raw[lo:hi], dtype=float)
        if cfg['smoothing']['mode'] == 'live':
            a = pd.Series(a).ewm(alpha=cfg['smoothing']['ema_alpha'], adjust=False).mean().to_numpy()
        elif cfg['smoothing']['method'] == 'gaussian':
            a = gaussian_filter1d(a, cfg['smoothing']['gaussian_sigma_minutes'] / cfg['hr']['window_minutes'],
                                 mode='nearest', truncate=cfg['smoothing']['gaussian_truncate'])
        else:
            window = min(cfg['smoothing']['savgol_windows'], len(a) if len(a) % 2 else len(a) - 1)
            if window > cfg['smoothing']['savgol_order']:
                a = savgol_filter(a, window, cfg['smoothing']['savgol_order'], mode='interp')
        out[lo:hi] = a
    return np.clip(out, 0, cfg['score']['max_score'])


def map_scores(frame, cfg, ablation='full'):
    c = cfg['score']
    raw = frame['z_hr'].to_numpy().copy()
    sleep = frame['state'].eq('SLEEP').to_numpy()
    paired = sleep & frame['z_hrv'].notna().to_numpy()
    if ablation != 'hr_only':
        raw[paired] = (c['w_hr_s'] * raw[paired] + c['w_hrv'] * frame.loc[paired, 'z_hrv']) / (c['w_hr_s'] + c['w_hrv'])
    if ablation == 'full':
        awake = ~sleep
        raw[awake] += c['w_ctx'] * frame.loc[awake, 'context_fraction'].to_numpy() * frame.loc[awake, 'z_night'].fillna(0).to_numpy()
    raw[frame['state'].isin(['EXERCISE', 'OFFWRIST'])] = np.nan
    scores = c['max_score'] / (1 + np.exp(-c['k'] * (raw - c['z_mid'])))
    return raw, scores, smooth_scores(frame, scores, cfg)


def score_export(data, cfg, excluded_baseline_days=()):
    minute = preprocess_hr(data, cfg)
    report, hrv, steps = alignment_probe(data, minute, cfg)
    return score_inputs(data, cfg, minute, hrv, steps, report, excluded_baseline_days)


def score_inputs(data, cfg, minute, hrv, steps, report, excluded_baseline_days=()):
    """Shared app/export calculator; API inputs already have UTC timestamps."""
    frame = _base_states(data, minute, steps, cfg)
    nights = _nights(data, minute, hrv, cfg)
    # Exercise masks never change sleep windows; pair sleep HRV once per request.
    paired_hrv = _paired_hrv(frame, hrv, cfg)
    completed = nights[nights['x'].notna()].sort_values('end').drop_duplicates('end')
    previous_x = (completed.set_index('end')['x'].reindex(frame.index, method='ffill')
                  if len(completed) else pd.Series(np.nan, index=frame.index))
    features = []
    for date in sorted(frame['date'].unique()):
        mode, refs = _references(frame, date, cfg, excluded_baseline_days)
        rhr, hrmax = _physiology(data, minute, nights, refs, cfg)
        classified = frame.copy()
        classified.loc[_exercise_masks(frame, data, rhr, hrmax, cfg), 'state'] = 'EXERCISE'
        reference = classified[classified['date'].isin(refs)]
        still = robust(reference.loc[reference['state'].eq('STILL'), 'hr'], cfg['baselines']['hr_spread_floor'], cfg)
        classified.loc[_exercise_masks(frame, data, rhr, hrmax, cfg, still), 'state'] = 'EXERCISE'
        reference = classified[classified['date'].isin(refs)]
        mu, sigma = robust(reference.loc[reference['state'].isin(['SLEEP', 'STILL']), 'hr'], cfg['baselines']['hr_spread_floor'], cfg)
        reference_nights = nights[nights['date'].isin(refs)]
        sessions = data.sleeps[data.sleeps['end'].dt.tz_convert(data.timezone).dt.date.astype(str).isin(refs)]
        ref_x = hrv.loc[sleep_membership(hrv['timestamp'], sessions), 'x']
        mux, sigmax = robust(ref_x, cfg['baselines']['hrv_spread_floor'], cfg)
        mun, sigman = robust(reference_nights['x'], cfg['baselines']['night_spread_floor'], cfg)
        count = int(reference_nights['x'].notna().sum())
        day = classified[classified['date'].eq(date)].copy()
        x = paired_hrv.reindex(day.index)
        day['x_sleep'] = x
        day['z_hr'] = ((day['hr'] - mu) / sigma).clip(*cfg['score']['z_hr_clip'])
        day['z_hrv'] = (-(x - mux) / sigmax).clip(*cfg['score']['z_hrv_clip'])
        day['z_night'] = np.nan
        if np.isfinite(sigman):
            day['z_night'] = (-(previous_x.reindex(day.index) - mun) / sigman).clip(*cfg['score']['z_night_clip'])
        day['context_fraction'] = min(1, count / cfg['baselines']['window_days'])
        day['baseline_mode'] = mode
        day['baseline_dates'] = '|'.join(refs)
        day['baseline_days'] = len(refs)
        day['baseline_nights'] = count
        day['baseline_leaks'] = any(d >= date for d in refs)
        day['low_confidence'] = len(refs) < cfg['baselines']['confidence_days']
        for key, val in {'mu_hr': mu, 'sigma_hr': sigma, 'mu_x': mux, 'sigma_x': sigmax,
                         'mu_n': mun, 'sigma_n': sigman, 'rhr_ref': rhr, 'hrmax_ref': hrmax}.items():
            day[key] = val
        if len(refs) < cfg['baselines']['min_days']:
            day[['z_hr', 'z_hrv', 'z_night']] = np.nan
        features.append(day)
    result = pd.concat(features)
    result['raw'], result['score_raw'], result['score'] = map_scores(result, cfg)
    result.index.name = 'timestamp'
    report['within_sleep_hrv_enabled'] = cfg['time']['hrv_window_anchor'] != 'unverified'
    report['warnings'] = ['Exercise HR differs from tracker average: ' + c['activity'] for c in report['exercise_checks'] if c['aligned'] is False]
    if not report['within_sleep_hrv_enabled']:
        report['warnings'].append('HRV window anchor unverified: sleep scoring is HR-only; nightly medians remain context only.')
    return result, report


def daily_summary(frame, cfg):
    rows = []
    for date, day in frame.groupby('date'):
        duration = day['duration_minutes']
        def mean(mask):
            selected = mask & day['score'].notna()
            return np.average(day.loc[selected, 'score'], weights=duration[selected]) if selected.any() else np.nan
        scored = day['score'].notna()
        rows.append({'date': date, 'sleep_stress': mean(day['state'].eq('SLEEP')),
                     'non_activity_stress': mean(day['state'].isin(['STILL', 'AMBIG'])),
                     'total_day_stress': mean(scored),
                     'minutes_high': duration[day['score'].ge(cfg['score']['high_threshold'])].sum(),
                     'scored_minutes': duration[scored].sum(), 'observed_window_minutes': duration.sum(),
                     'coverage_percent': 100 * duration[scored].sum() / duration.sum() if duration.sum() else 0,
                     'low_confidence': bool(day['low_confidence'].any()),
                     'baseline_mode': day['baseline_mode'].iloc[0], 'baseline_days': int(day['baseline_days'].iloc[0]),
                     'baseline_leaks': bool(day['baseline_leaks'].any())})
    return pd.DataFrame(rows)
