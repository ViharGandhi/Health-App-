"""Pure HR-reserve/TRIMP cardio strain; no network, storage, or UI dependencies."""
from dataclasses import dataclass, fields
from datetime import date, datetime, time, timedelta, timezone
from enum import IntEnum
import math
from statistics import mean, median


@dataclass(frozen=True)
class StrainConfig:
    strain_l: float = 90
    min_hrr: float = .20
    max_gap_s: float = 300
    spike_bpm: float = 35
    hr_floor: float = 30
    hr_ceiling: float = 230
    auto_workout_hrr: float = .45
    auto_workout_min: float = 10
    min_main_sleep_h: float = 3
    low_coverage_threshold: float = .6
    recovery_low_threshold: float = 34
    recovery_high_threshold: float = 67
    target_low_low: float = 4
    target_low_high: float = 10
    target_mid_low: float = 10
    target_mid_high: float = 14
    target_high_low: float = 14
    target_high_high: float = 18

    @classmethod
    def from_env(cls, env):
        values = {}
        for field in fields(cls):
            key = 'STRAIN_L' if field.name == 'strain_l' else f'STRAIN_{field.name.upper()}'
            if key in env:
                values[field.name] = float(env[key])
        config = cls(**values)
        if (any(not math.isfinite(v) for v in config.__dict__.values()) or config.strain_l <= 0
                or config.max_gap_s <= 0 or config.spike_bpm < 0 or config.min_main_sleep_h <= 0
                or not 0 < config.hr_floor < config.hr_ceiling
                or config.auto_workout_min <= 0 or not 0 <= config.min_hrr <= 1.1
                or not 0 <= config.auto_workout_hrr <= 1.1 or not 0 <= config.low_coverage_threshold <= 1
                or not 0 <= config.recovery_low_threshold < config.recovery_high_threshold <= 100
                or any(not 0 <= low <= high <= 21 for low, high in (
                    (config.target_low_low, config.target_low_high), (config.target_mid_low, config.target_mid_high),
                    (config.target_high_low, config.target_high_high)))):
            raise ValueError('Invalid Strain configuration')
        return config


class HeartRateZone(IntEnum):
    ZONE1 = 1
    ZONE2 = 2
    ZONE3 = 3
    ZONE4 = 4
    ZONE5 = 5

    @staticmethod
    def zone_for(hr, max_hr):
        return HeartRateZone(1 if hr < .6 * max_hr else 2 if hr < .7 * max_hr else 3 if hr < .8 * max_hr else 4 if hr < .9 * max_hr else 5)


def seconds(start: datetime, end: datetime) -> float:
    """Physical elapsed time, including a DST transition within one timezone."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError('Strain requires timezone-aware timestamps')
    return (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()


def day_window(target: date, now: datetime, sleeps: list[dict], tz, config=StrainConfig()) -> dict:
    midnight = datetime.combine(target, time.min, tzinfo=tz)
    main = sorted((s for s in sleeps if not s.get('nap') and s.get('main_sleep') is not False
                   and seconds(s['start'], s['end']) >= config.min_main_sleep_h * 3600), key=lambda s: s['end'])
    current = target == now.astimezone(tz).date()
    candidates = [s for s in main if s['end'] <= now and (current or s['end'].astimezone(tz).date() == target)]
    start = candidates[-1]['end'].astimezone(tz) if candidates else midnight
    end = now.astimezone(tz) if current else midnight + timedelta(days=1)
    if not current and candidates:
        following = [s['start'] for s in main if start <= s['start'] <= now]
        if following:
            end = min(following).astimezone(tz)
    return {'start': start, 'end': max(start, end), 'source': 'sleep' if candidates else 'midnight_fallback'}


def clean_samples(samples: list, window: dict, config=StrainConfig()) -> list:
    unique = {}
    for stamp, bpm in samples:
        seconds(window['start'], stamp)
        physical = stamp.astimezone(timezone.utc)
        if window['start'].astimezone(timezone.utc) <= physical <= window['end'].astimezone(timezone.utc):
            unique.setdefault(physical, (stamp, float(bpm)))
    ordered = [(stamp, bpm) for _, (stamp, bpm) in sorted(unique.items()) if math.isfinite(bpm) and config.hr_floor <= bpm <= config.hr_ceiling]
    if len(ordered) < 5:
        return ordered
    # Match the reference's centered five-sample median with repeated edge values.
    values = [ordered[0][1]] * 2 + [bpm for _, bpm in ordered] + [ordered[-1][1]] * 2
    return [(stamp, bpm) for i, (stamp, bpm) in enumerate(ordered)
            if abs(bpm - median(values[i:i + 5])) <= config.spike_bpm]


def strain_score(load: float, config=StrainConfig()) -> float:
    return min(math.nextafter(21., 0), -21 * math.expm1(-max(0., load) / config.strain_l))


def strain_label(score):
    return None if score is None else 'Light' if score < 10 else 'Moderate' if score < 14 else 'High' if score < 18 else 'All Out'


def empty_zones():
    return {f'zone{i}': 0. for i in range(1, 6)}


def calculate_strain(samples: list, sessions: list[dict], window: dict, age: int | None,
                     resting_hrs=(), sex='m', sex_defaulted=False, config=StrainConfig()) -> dict:
    if age is not None and not 18 <= age <= 100:
        raise ValueError('Age must be between 18 and 100')
    if sex not in ('m', 'f'):
        raise ValueError('Sex must be m or f')
    cleaned = clean_samples(samples, window, config)
    hr_max = 208 - .7 * age if age is not None else None
    rest = []
    rejected = 0
    for value in resting_hrs:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            rejected += 1
            continue
        if (not math.isfinite(parsed) or not config.hr_floor <= parsed <= config.hr_ceiling
                or (hr_max is not None and parsed >= hr_max)):
            rejected += 1
        else:
            rest.append(parsed)
    rest = rest[-7:]
    hr_rest = median(rest) if rest else 60.
    params = {'hr_max': hr_max, 'hr_rest': hr_rest, 'hr_rest_source': 'recovery' if rest else 'default',
              'strain_l': config.strain_l, 'sex': sex, 'sex_source': 'default' if sex_defaulted else 'profile',
              'rhr_rejected_count': rejected}
    workouts = sorted((s for s in sessions if s['end'] >= window['start'] and s['start'] <= window['end']), key=lambda s: s['start'])
    details = [{**s, 'load': 0., 'zone_minutes': empty_zones(), 'hr_sum': 0., 'counted_minutes': 0., 'recorded': False, 'max_hr': None} for s in workouts]
    zones, activity_zones = empty_zones(), empty_zones()
    load = workout_load = counted = hr_sum = 0.
    a, b = (.64, 1.92) if sex == 'm' else (.86, 1.67)
    for (first, hr1), (last, hr2) in zip(cleaned, cleaned[1:]):
        elapsed = seconds(first, last)
        if not 0 < elapsed <= config.max_gap_s:
            continue
        minutes, hr = elapsed / 60, (hr1 + hr2) / 2
        counted += minutes
        hr_sum += minutes * hr
        if age is None:
            continue
        hrr = max(0., min(1.1, (hr - hr_rest) / max(hr_max - hr_rest, 1.)))
        interval_load = minutes * hrr * a * math.exp(b * hrr) if hrr >= config.min_hrr else 0.
        load += interval_load
        zone = f'zone{int(HeartRateZone.zone_for(hr, hr_max))}' if hr >= .5 * hr_max else None
        if zone:
            zones[zone] += minutes
        # Compute midpoint in physical time; wall-clock arithmetic is unsafe at DST.
        midpoint = first.astimezone(timezone.utc) + timedelta(seconds=elapsed / 2)
        for detail in details:
            if detail['start'] <= midpoint <= detail['end']:
                detail['recorded'] = True
        match = next((d for d in details if d['start'] <= midpoint <= d['end']), None)
        if match is not None:
            workout_load += interval_load
            match['load'] += interval_load
            match['hr_sum'] += hr * minutes
            match['counted_minutes'] += minutes
            match['max_hr'] = max(match['max_hr'] or 0, hr1, hr2)
            if zone:
                match['zone_minutes'][zone] += minutes
                activity_zones[zone] += minutes
    duration = max(0., seconds(window['start'], window['end']) / 60)
    coverage = min(1., counted / duration) if duration else 0.
    output = []
    for d in details:
        if d['load'] < .5:
            continue
        output.append({'name': d['activity_name'], 'activity_name': d['activity_name'], 'exercise_type': d.get('exercise_type'),
                       'start': d['start'], 'end': d['end'], 'duration_min': seconds(d['start'], d['end']) / 60,
                       'strain': strain_score(d['load'], config), 'load': d['load'],
                       'avg_hr': mean(hr for stamp, hr in cleaned if d['start'] <= stamp <= d['end']) if any(d['start'] <= stamp <= d['end'] for stamp, _ in cleaned) else None,
                       'max_hr': max((hr for stamp, hr in cleaned if d['start'] <= stamp <= d['end']), default=None), 'zone_minutes': d['zone_minutes']})
    score = strain_score(load, config) if age is not None else None
    return {'strain': score, 'label': strain_label(score), 'load': load if age is not None else None,
            'coverage': coverage, 'low_coverage': coverage < config.low_coverage_threshold,
            'calibrating': not rest or sex_defaulted or rejected > 0, 'age_missing': age is None, 'params': params,
            'avg_hr': mean(hr for _, hr in cleaned) if cleaned else None,
            'max_hr': max((bpm for _, bpm in cleaned), default=None), 'zone_minutes': zones if age is not None else None,
            'workouts': output, 'activity_zone_minutes': activity_zones if age is not None and all(d['recorded'] for d in details) else None,
            'workout_load': workout_load if age is not None else None,
            'incidental_load': max(0., load - workout_load) if age is not None else None,
            'suggested_workouts': detect_unlogged_workouts(cleaned, workouts, hr_rest, hr_max, config) if hr_max else [], 'counted_minutes': counted, 'sample_count': len(cleaned)}


def strain_analytics(history: list[dict], end: date, score, recovery, config=StrainConfig()):
    valid = [d for d in history if d['load'] is not None and d.get('coverage', 0) > 0 and end - timedelta(days=27) <= d['date'] <= end]
    recent = [d for d in valid if d['date'] >= end - timedelta(days=6)]
    chronic = mean(d['load'] for d in valid) if valid else 0
    target = None
    if recovery is not None and score is not None:
        low, high = ((config.target_high_low, config.target_high_high) if recovery >= config.recovery_high_threshold else
                     (config.target_mid_low, config.target_mid_high) if recovery >= config.recovery_low_threshold else
                     (config.target_low_low, config.target_low_high))
        target = {'low': low, 'high': high, 'status': 'under' if score < low else 'over' if score > high else 'on'}
    return {'avg_strain_7d': mean(d['strain'] for d in recent) if recent else None,
            'avg_strain_28d': mean(d['strain'] for d in valid) if valid else None,
            'acute_chronic_ratio': mean(d['load'] for d in recent) / chronic if len(valid) >= 21 and recent and chronic > 0 else None,
            'strain_target': target}


def detect_unlogged_workouts(samples, workouts, hr_rest, hr_max, config=StrainConfig()):
    found, run = [], []
    def finish():
        if run and seconds(run[0][0], run[-1][0]) >= config.auto_workout_min * 60:
            start, end = run[0][0], run[-1][0]
            if not any(start < w['end'] and end > w['start'] for w in workouts):
                found.append({'start': start, 'end': end, 'avg_hr': mean(hr for _, hr in run)})
        run.clear()
    for stamp, hr in samples:
        if run and seconds(run[-1][0], stamp) > config.max_gap_s:
            finish()
        if (hr - hr_rest) / max(hr_max - hr_rest, 1.) >= config.auto_workout_hrr:
            run.append((stamp, hr))
        else:
            finish()
    finish()
    return found
