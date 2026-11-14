from datetime import date, datetime, timedelta, timezone

import pytest

from strain_analytics import activity_id
from training_load import estimate_effort, status, summarize, workout_loads

END = date(2026, 11, 14)


def test_effort_estimate_matches_the_frontend_table():
    # Same cases as frontend/lib/effort.test.mjs.
    assert estimate_effort(None) is None and estimate_effort(float('nan')) is None
    assert [estimate_effort(s) for s in (0, 3.4, 6.7, 9.99)] == [1, 2, 3, 3]
    assert [estimate_effort(s) for s in (10, 11.4, 12.7, 13.99)] == [4, 5, 6, 6]
    assert [estimate_effort(s) for s in (14, 16, 17.99)] == [7, 8, 8]
    assert [estimate_effort(s) for s in (18, 19.5, 21, 25)] == [9, 10, 10, 10]


@pytest.mark.parametrize('change,expected', [(-.41, 'well_below'), (-.4, 'below'), (-.16, 'below'), (-.15, 'steady'),
                                             (.15, 'steady'), (.16, 'above'), (.4, 'above'), (.41, 'well_above')])
def test_status_bands(change, expected):
    assert status(change) == expected


def workout(day, name='Run', strain=12., minutes=40):
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=18)
    return {'activity_name': name, 'exercise_type': 'RUNNING', 'start': start, 'end': start + timedelta(minutes=minutes),
            'strain': strain, 'duration_min': minutes}


def test_ratings_replace_estimates_and_always_count():
    run = workout(END)
    days = {END: {'workouts': [run]}}
    estimated = workout_loads(days, [])
    assert estimated[0]['effort'] == 5 and not estimated[0]['rated'] and estimated[0]['load'] == 200
    rated = workout_loads(days, [{'activity_id': activity_id(run), 'date': END.isoformat(), 'rpe': 8, 'minutes': 40}])
    assert rated[0]['effort'] == 8 and rated[0]['rated'] and rated[0]['load'] == 320
    # A lifting session too light on heart rate to be scored still counts once rated.
    lifted = workout_loads({END: {'workouts': []}}, [{'activity_id': 'lift', 'date': END.isoformat(), 'rpe': 7, 'minutes': 50}])
    assert lifted == [{'id': 'lift', 'date': END.isoformat(), 'name': None, 'effort': 7, 'rated': True, 'minutes': 50, 'load': 350}]


def rows_for(loads):
    return [{'date': (END - timedelta(days=i)).isoformat(), 'load': load, 'rated': False} for i, load in enumerate(loads) if load]


def test_week_is_compared_with_the_three_weeks_before_it():
    worn = {END - timedelta(days=i) for i in range(28)}
    result = summarize(rows_for([100] * 7 + [50] * 21), worn, END)
    assert result['current']['week_load'] == pytest.approx(700)
    assert result['current']['usual_week_load'] == pytest.approx(350)
    assert result['current']['status'] == 'well_above'
    assert len(result['days']) == 28


def test_days_without_the_band_are_unknown_not_rest():
    worn = {END - timedelta(days=i) for i in range(28) if i not in (1, 2)}
    result = summarize(rows_for([100] * 28), worn, END)
    assert result['current']['week_load'] == pytest.approx(700)  # 5 worn days scaled to a week
    assert result['current']['status'] == 'steady'


def test_needs_enough_worn_days():
    assert summarize(rows_for([100] * 28), {END - timedelta(days=i) for i in range(3)}, END)['current'] is None
    assert summarize(rows_for([100] * 28), {END - timedelta(days=i) for i in range(20)}, END)['current'] is None
