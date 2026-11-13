"""Deterministic demo athlete: one training story feeds demo Strain and Recovery.

Every date is a pure function of the calendar, so any range shows the same days.
The responses are rough, literature-shaped effects for previewing the UI, not a
validated physiology model:
  - hard sessions lower next-morning HRV and raise resting HR, fading over ~2 days
  - a 4-week block: three build weeks, then a lighter deload week
  - a short illness every 50 days: temperature and breathing rate rise first,
    then HRV drops and resting HR rises; training stops, then restarts easy
  - occasional late nights (Friday/Saturday) lower HRV and raise resting HR once
  - missed sessions, a night without the band every 37 days and an HRV artefact every 23 days
"""

import math
import random
from datetime import date, datetime, timedelta

# key: (activity name, exercise type, minutes, target bpm, HR shape, effort per hour)
SESSIONS = {
    'easy': ('Easy Run', 'RUNNING', 40, 145, 'steady', .6),
    'tempo': ('Tempo Run', 'RUNNING', 45, 160, 'steady', 1.),
    'intervals': ('Interval Run', 'RUNNING', 50, 172, 'intervals', 1.3),
    'long': ('Long Run', 'RUNNING', 85, 147, 'steady', .8),
    'strength': ('Weightlifting', 'WEIGHTLIFTING', 50, 128, 'sets', .5),
    'ride': ('Outdoor Bike', 'BIKING', 60, 140, 'steady', .7),
}
# weekday -> [(session, hours after waking)]
WEEK = {0: [('strength', 5), ('easy', 10.5)], 1: [('intervals', 10.5)], 2: [],
        3: [('strength', 5), ('tempo', 10.5)], 4: [], 5: [('long', 2.5)], 6: [('ride', 3)]}
BUILD = (.9, 1., 1.1, .65)  # minutes multiplier by week of the 4-week block
ILLNESS_CYCLE = 50
# day of the illness episode -> (ln HRV, RHR bpm, breaths/min, skin °C, SpO2 %)
ILLNESS = {0: (-.05, 1, .9, .5, 0), 1: (-.3, 6, 1.6, .9, -.8), 2: (-.25, 5, 1.3, .7, -.6),
           3: (-.15, 3, .6, .3, -.3), 4: (-.05, 1, .2, .1, 0)}
WAKE_HOUR = 7
AWAKE_MINUTES = 900


def _rng(day: date, salt: int) -> random.Random:
    return random.Random(day.toordinal() * 7919 + salt)


def illness_day(day: date) -> int | None:
    phase = day.toordinal() % ILLNESS_CYCLE
    return phase if phase in ILLNESS else None


def late_night(day: date) -> bool:
    """Late night or alcohol on the evening of `day`; shows up the next morning."""
    return day.weekday() in (4, 5) and _rng(day, 3).random() < .3


def plan(day: date) -> list[dict]:
    """Sessions done on `day`, with their own small day-to-day variation."""
    rng = _rng(day, 1)
    sick = illness_day(day)
    if sick in (1, 2, 3):
        return []
    block = BUILD[(day.toordinal() // 7) % 4]
    sessions = []
    for key, hours in WEEK[day.weekday()]:
        if rng.random() < .08:  # missed session
            continue
        if sick is not None or block < 1 and key == 'intervals':
            key = 'easy'
        name, kind, minutes, target, shape, effort = SESSIONS[key]
        sessions.append({'key': key, 'name': name, 'type': kind, 'shape': shape,
                         'start_hours': hours + rng.uniform(-.25, .25),
                         'minutes': round(minutes * block * rng.uniform(.9, 1.1)),
                         'target': target + rng.gauss(0, 3), 'effort': effort})
    return sessions


def effort(day: date) -> float:
    return sum(s['effort'] * s['minutes'] / 60 for s in plan(day))


def vitals(day: date) -> dict | None:
    """Overnight values Google reports for the night ending on the morning of `day`."""
    ordinal = day.toordinal()
    if ordinal % 37 == 0:
        return None  # band not worn overnight
    rng = _rng(day, 2)
    fatigue = sum(effort(day - timedelta(days=k)) * math.exp(-(k - 1) / 1.2) for k in range(1, 5))
    trend = math.sin(2 * math.pi * ordinal / 120)
    late = late_night(day - timedelta(days=1))
    hrv_ill, rhr_ill, resp_ill, temp_ill, spo2_ill = ILLNESS.get(illness_day(day), (0, 0, 0, 0, 0))
    ln_hrv = math.log(52) + .06 * trend - .07 * fatigue - .18 * late + hrv_ill + rng.gauss(0, .07)
    hrv = math.exp(ln_hrv) * (1.45 if ordinal % 23 == 0 else 1)  # a sensor artefact
    values = {
        'hrv': hrv,
        'rhr': 54 - 1.5 * trend + 2 * fatigue + 4 * late + rhr_ill + rng.gauss(0, 1),
        'respiratory_rate': 15.4 + .3 * late + resp_ill + rng.gauss(0, .2),
        'skin_temperature': 33.4 + .15 * late + temp_ill + rng.gauss(0, .15),
        'spo2': min(100, 96.8 + spo2_ill + rng.gauss(0, .5)),
    }
    if ordinal % 13 == 0:
        del values['skin_temperature']
    return values


def _session_target(session: dict, minute: float, base: float) -> float:
    """Target bpm `minute` minutes into a session, before the heart's lag."""
    target, length = session['target'], session['minutes']
    if minute < 8 or minute > length - 4:
        return base + 30
    if session['shape'] == 'intervals':
        return target if (minute - 8) % 5 < 3 else target - 40
    if session['shape'] == 'sets':
        return target + 12 if minute % 4 < 1.5 else target - 22
    return target + 3 * math.sin(minute / 4)


def day_samples(day: date, tz) -> tuple[list, list, int]:
    """Per-minute heart rate from waking to 22:00, logged sessions and steps."""
    rng = _rng(day, 4)
    wake = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=WAKE_HOUR)
    morning = vitals(day)
    rest = morning['rhr'] if morning else 56
    sessions = [{**s, 'begin': wake + timedelta(hours=s['start_hours'])} for s in plan(day)]
    walks = [(rng.uniform(1, 2), rng.randint(10, 20)), (rng.uniform(5, 6), rng.randint(10, 25)),
             (rng.uniform(9, 10), rng.randint(10, 20))]
    unlogged = rng.uniform(4, 8) if rng.random() < .25 else None  # stairs or a brisk walk
    if illness_day(day) in (1, 2, 3):  # stays home while sick
        walks, unlogged = walks[:1], None
    samples, steps, bpm = [], 0, rest + 10
    for minute in range(AWAKE_MINUTES + 1):
        stamp = wake + timedelta(minutes=minute)
        hours = minute / 60
        base = rest + 15 + 5 * math.sin(minute / 83.333)
        target = base
        for start, length in walks:
            if start <= hours < start + length / 60:
                target, steps = base + 30, steps + 105
        if unlogged is not None and unlogged <= hours < unlogged + 1 / 3:
            target, steps = 122, steps + 110
        for session in sessions:
            into = (stamp - session['begin']).total_seconds() / 60
            if 0 <= into <= session['minutes']:
                target = _session_target(session, into, base)
                steps += 160 if session['type'] == 'RUNNING' else 15
        bpm += (target - bpm) * .35  # the heart lags changes in effort
        samples.append((stamp, round(bpm + rng.gauss(0, 2), 1)))
    steps += round(4300 + rng.gauss(0, 900))
    logged = [{'start': s['begin'], 'end': s['begin'] + timedelta(minutes=s['minutes']),
               'activity_name': s['name'], 'exercise_type': s['type'], 'active_minutes': s['minutes']}
              for s in sessions]
    return samples, logged, max(0, steps)
