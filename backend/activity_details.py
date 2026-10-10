"""Home and activity presentation data; cardio scores use the existing calculator."""
from datetime import datetime, timedelta, timezone
from math import floor, sin
from statistics import mean

from strain import StrainConfig, clean_samples, seconds
from strain_analytics import activity_id, metric_value, strain_day


def activity_type(session):
    return session.get('exercise_type') or session['activity_name'].upper()


def showcase_inputs(start, end, tz):
    """Deterministic raw HR with walking, running and lifting on every sample day."""
    samples, sessions, sleeps, rhrs, steps = [], [], [], {}, {}
    day = start - timedelta(days=7)
    while day <= end + timedelta(days=1):
        wake = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=7)
        sleeps.append({'start': wake - timedelta(hours=8), 'end': wake, 'main_sleep': True})
        rhrs[day] = 56 + day.day % 3
        variation = (day.toordinal() % 5) - 2
        planned = [(2, 38 + variation, 'Walking', 'WALKING'), (4, 26 + variation, 'Running', 'RUNNING'),
                   (9, 52 + variation, 'Weightlifting', 'WEIGHTLIFTING')]
        workouts = []
        for hour, minutes, name, kind in planned:
            session = {'start': wake + timedelta(hours=hour), 'end': wake + timedelta(hours=hour, minutes=minutes),
                       'activity_name': name, 'exercise_type': kind, 'active_minutes': minutes}
            sessions.append(session)
            workouts.append(session)
        for sec in range(0, 15 * 3600 + 1, 15):
            stamp = wake + timedelta(seconds=sec)
            bpm = 68 + 4 * sin(sec / 4000)
            for session in workouts:
                if session['start'] <= stamp <= session['end']:
                    elapsed = seconds(session['start'], stamp) / 60
                    length = session['active_minutes']
                    ramp = max(0, min(elapsed / 3, (length - elapsed) / 3, 1))
                    target = 110 if session['exercise_type'] == 'WALKING' else 182 if session['exercise_type'] == 'RUNNING' else 125 + 20 * sin(elapsed / 2)
                    bpm = 76 + (target + variation - 76) * ramp + 2 * sin(sec / 19)
            samples.append((stamp, bpm))
        steps[day] = 8100 + 220 * variation
        day += timedelta(days=1)
    return (samples, sessions, sleeps, rhrs), steps


def activity_summary(session, result):
    workout = next((w for w in result['workouts'] if w['start'] == session['start'] and w['end'] == session['end']
                    and w['activity_name'] == session['activity_name']), None)
    return {'id': activity_id(session), 'activity_name': session['activity_name'], 'exercise_type': session.get('exercise_type'),
            'start': session['start'].isoformat(), 'end': session['end'].isoformat(),
            'duration_min': seconds(session['start'], session['end']) / 60,
            'strain': floor(workout['strain'] * 10) / 10 if workout else None,
            'avg_hr': workout['avg_hr'] if workout else None, 'max_hr': workout['max_hr'] if workout else None}


def build_activity(session, current, samples, history, sessions, day, is_mock, config=StrainConfig()):
    result = activity_summary(session, current)
    cleaned = clean_samples(samples, current['day_window'], config)
    trace = [(stamp, bpm) for stamp, bpm in cleaned if session['start'] <= stamp <= session['end']]
    owners = sorted((s for s in sessions if s['end'] >= current['day_window']['start'] and s['start'] <= current['day_window']['end']), key=lambda s: s['start'])
    counted = 0.
    zones = [0.] * 6 if current['params']['hr_max'] else None
    hr_max = current['params']['hr_max']
    for (first, a), (last, b) in zip(cleaned, cleaned[1:]):
        elapsed = seconds(first, last)
        if not 0 < elapsed <= config.max_gap_s:
            continue
        midpoint = first.astimezone(timezone.utc) + timedelta(seconds=elapsed / 2)
        owner = next((s for s in owners if s['start'] <= midpoint <= s['end']), None)
        if owner is None or activity_id(owner) != result['id']:
            continue
        counted += elapsed / 60
        if zones is not None:
            fraction = (a + b) / 2 / hr_max
            index = sum(fraction >= edge for edge in (.5, .6, .7, .8, .9))
            zones[index] += elapsed / 60
    if counted == 0:
        result.update(strain=None, avg_hr=None, max_hr=None)
        zones = None
    elif result['avg_hr'] is None and trace:
        result.update(avg_hr=mean(b for _, b in trace), max_hr=max(b for _, b in trace))
    prior = []
    for when, value in history.items():
        if day - timedelta(days=30) <= when < day:
            prior.extend(w for w in value['workouts'] if activity_type(w) == activity_type(session))
    averages = {key: mean(values) if (values := [w[key] for w in prior if w.get(key) is not None]) else None
                for key in ('strain', 'avg_hr', 'max_hr')}
    duration = result['duration_min']
    active_steps = round(duration * (112 if activity_type(session) == 'WALKING' else 165)) if is_mock and activity_type(session) in ('WALKING', 'RUNNING') else None
    calorie_rate = 4 if activity_type(session) == 'WALKING' else 11 if activity_type(session) == 'RUNNING' else 6
    calories = round(duration * calorie_rate) if is_mock else None
    averages.update(steps=round(mean(w['duration_min'] * (112 if activity_type(session) == 'WALKING' else 165) for w in prior)) if active_steps is not None and prior else None,
                    calories=round(mean(w['duration_min'] * calorie_rate for w in prior)) if is_mock and prior else None)
    edges = (0, .5, .6, .7, .8, .9, None)
    zone_rows = []
    for index in range(5, -1, -1):
        fraction = zones[index] / duration if zones is not None and duration > 0 else None
        zone_rows.append({'zone': index, 'minutes': zones[index] if zones is not None else None,
                          'percent': 100 * fraction if fraction is not None else None,
                          'low': hr_max * edges[index] if hr_max else None,
                          'high': hr_max * edges[index + 1] if hr_max and edges[index + 1] is not None else None,
                          'typical': {'low': max(0, fraction * 100 - 8), 'high': min(100, fraction * 100 + 10)} if is_mock and fraction is not None else None})
    result.update(date=str(day), is_mock=is_mock, steps=active_steps, calories=calories, averages=averages,
                  comparison_count=len(prior), coverage=min(1, counted / duration) if duration > 0 else 0,
                  unrecorded_minutes=max(0, duration - counted), zones=zone_rows,
                  heart_rate=[{'timestamp': stamp.isoformat(), 'bpm': round(bpm, 1)} for stamp, bpm in trace],
                  muscular_split={'cardio': 35, 'muscular': 65} if is_mock and activity_type(session) == 'WEIGHTLIFTING' else None,
                  route_sample=is_mock and activity_type(session) in ('WALKING', 'RUNNING'))
    return result


def dashboard_rows(sleep, health, values, sessions, steps, snapshots, day):
    prior_start = day - timedelta(days=30)
    latest = sleep['days'][-1]
    rows = []
    def add(key, title, value, previous, unit, href):
        rows.append({'key': key, 'title': title, 'value': value, 'previous': previous, 'unit': unit, 'href': href})
    def health_reading(key):
        points = health['metrics'].get(key, [])
        latest = next((p for p in reversed(points) if p['value'] is not None and (p['date'] == str(day) or key == 'vo2_max')), None)
        prior = [p['value'] for p in points if str(prior_start) <= p['date'] < str(day) and p['value'] is not None]
        return latest['value'] if latest else None, mean(prior) if prior else None
    hrv, hrv_prior = health_reading('hrv')
    add('hrv', 'HEART RATE VARIABILITY', hrv, hrv_prior, '', '/health/hrv')
    for key, title, unit, slug in [('performance', 'SLEEP PERFORMANCE', '%', 'performance'), ('consistency', 'SLEEP CONSISTENCY', '%', 'consistency'), ('asleep_minutes', 'HOURS OF SLEEP', 'duration', 'hours-needed')]:
        add(key, title, latest.get(key), sleep['prior_30_averages'][key], unit, f'/sleep/{slug}')
    for key, title, slug, unit in [('rhr', 'RESTING HEART RATE', 'resting-heart-rate', ''), ('vo2_max', 'VO₂ MAX', 'cardio-fitness', '')]:
        value, previous = health_reading(key)
        add(key, title, value, previous, unit, f'/health/{slug}')
    history = [strain_day(when, [], sessions, snapshots[when], steps.get(when)) for when in sorted(values)]
    current = history[-1]
    prior = history[:-1]
    add('steps', 'STEPS', current['steps'], mean(v) if (v := [d['steps'] for d in prior if d['steps'] is not None]) else None, '', '/strain/steps')
    for key, title, slug in [('zones_1_3', 'HR ZONES 1–3 (WEEKLY)', 'heart-rate-zones-1-3'), ('zones_4_5', 'HR ZONES 4–5 (WEEKLY)', 'heart-rate-zones-4-5'), ('strength', 'STRENGTH ACTIVITY TIME', 'strength-activity-time')]:
        week = history[-7:]
        items = [metric_value(d, key) for d in week]
        total = sum(items) if len(items) == 7 and all(v is not None for v in items) else None
        buckets = [prior[-28:][i:i + 7] for i in range(0, 28, 7)]
        totals = []
        for bucket in buckets:
            items = [metric_value(d, key) for d in bucket]
            if len(items) == 7 and all(v is not None for v in items):
                totals.append(sum(items))
        add(key, title, total, mean(totals) if totals else None, 'duration', f'/strain/{slug}')
    value, previous = health_reading('respiratory_rate')
    add('respiratory_rate', 'RESPIRATORY RATE', value, previous, '', '/health/respiratory-rate')
    add('strain', 'DAY STRAIN', current['_json_score'], mean(v) if (v := [d['score'] for d in prior if d['score'] is not None]) else None, '', '/strain/day-strain')
    return rows
