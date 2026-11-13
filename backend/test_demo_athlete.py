from datetime import date, timedelta, timezone
from statistics import mean

import demo_athlete as athlete
from recovery_analytics import mock_recovery_history
from recovery_score import recovery_from_history


START = date(2026, 1, 1)
DAYS = [START + timedelta(days=i) for i in range(300)]


def test_days_are_pure_functions_of_the_date():
    assert athlete.vitals(DAYS[10]) == athlete.vitals(DAYS[10])
    assert athlete.plan(DAYS[10]) == athlete.plan(DAYS[10])
    assert all(athlete.vitals(day) is None for day in DAYS if day.toordinal() % 37 == 0)


def test_hard_days_lower_next_morning_hrv_and_raise_rhr():
    after = lambda keys: [athlete.vitals(day + timedelta(days=1)) for day in DAYS
                          if {s['key'] for s in athlete.plan(day)} & keys and athlete.vitals(day + timedelta(days=1))
                          and athlete.illness_day(day + timedelta(days=1)) is None]
    rested = [athlete.vitals(day + timedelta(days=1)) for day in DAYS if not athlete.plan(day)
              and athlete.vitals(day + timedelta(days=1)) and athlete.illness_day(day + timedelta(days=1)) is None]
    hard = after({'intervals', 'long'})
    assert mean(v['hrv'] for v in hard) < mean(v['hrv'] for v in rested)
    assert mean(v['rhr'] for v in hard) > mean(v['rhr'] for v in rested)


def test_illness_is_flagged_and_stops_training():
    sick = next(day for day in DAYS[80:] if athlete.illness_day(day) == 1 and athlete.vitals(day))
    history = mock_recovery_history(sick - timedelta(days=70), sick)
    assert recovery_from_history(history, sick).illness_flag
    assert athlete.plan(sick) == []


def test_logged_sessions_follow_the_plan():
    day = next(day for day in DAYS if len(athlete.plan(day)) == 2)
    samples, logged, steps = athlete.day_samples(day, timezone.utc)
    assert [s['activity_name'] for s in logged] == [s['name'] for s in athlete.plan(day)]
    assert len(samples) == athlete.AWAKE_MINUTES + 1 and steps > 0
