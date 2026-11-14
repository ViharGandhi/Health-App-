"""Apple Watch-style training load: effort x minutes per workout, this week vs usual.

Effort is the user's 1-10 rating, or, for unrated workouts, an estimate from the
workout's heart-rate Strain (same mapping as frontend/lib/effort.ts). Apple compares
the last 7 days with the last 28; here the week is compared with the 21 days before
it, so it cannot pull its own reference (as for the heart-rate load trend). Status
bands are display judgements, not validated thresholds: steady within 15%,
above/below 15-40%, well above/below beyond 40%.
"""
from datetime import date, timedelta
from statistics import mean

from strain_analytics import activity_id

CHART_DAYS = 28
WEEK_MIN_WORN = 4
USUAL_MIN_WORN = 14
STEADY_BAND = .15
WELL_BAND = .40


def estimate_effort(strain) -> int | None:
    """Strain bands (Light <10, Moderate 10-14, High 14-18, All Out 18+) spread over effort 1-3, 4-6, 7-8, 9-10."""
    if strain is None or not 0 <= strain < float('inf'):
        return None
    def spread(value, low, high, first, count):
        return first + min(count - 1, int((value - low) / (high - low) * count))
    if strain < 10:
        return spread(strain, 0, 10, 1, 3)
    if strain < 14:
        return spread(strain, 10, 14, 4, 3)
    if strain < 18:
        return spread(strain, 14, 18, 7, 2)
    return spread(min(strain, 21), 18, 21, 9, 2)


def workout_loads(days: dict, ratings: list[dict]) -> list[dict]:
    """One row per workout. A rating always counts, even for a workout with too
    little heart-rate load to be scored; unrated workouts use the Strain estimate."""
    rated = {rating['activity_id']: rating for rating in ratings}
    rows = []
    for day, value in days.items():
        for workout in value.get('workouts') or []:
            key = activity_id(workout)
            rating = rated.pop(key, None)
            effort = rating['rpe'] if rating else estimate_effort(workout.get('strain'))
            minutes = rating['minutes'] if rating else workout.get('duration_min')
            if effort is None or not minutes:
                continue
            rows.append({'id': key, 'date': day.isoformat(), 'name': workout['activity_name'], 'effort': effort,
                         'rated': rating is not None, 'minutes': minutes, 'load': effort * minutes})
    rows += [{'id': key, 'date': rating['date'], 'name': None, 'effort': rating['rpe'], 'rated': True,
              'minutes': rating['minutes'], 'load': rating['rpe'] * rating['minutes']} for key, rating in rated.items()]
    return rows


def status(change: float) -> str:
    if change < -WELL_BAND:
        return 'well_below'
    if change < -STEADY_BAND:
        return 'below'
    if change <= STEADY_BAND:
        return 'steady'
    return 'above' if change <= WELL_BAND else 'well_above'


def summarize(rows: list[dict], worn: set, end: date) -> dict:
    daily = {}
    for row in rows:
        daily[row['date']] = daily.get(row['date'], 0.) + row['load']

    def weekly(first: date, last: date, minimum: int):
        dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        seen = [day for day in dates if day in worn]
        # Days without the band are unknown, not rest: scale the worn-day mean to a week.
        return mean(daily.get(day.isoformat(), 0.) for day in seen) * 7 if len(seen) >= minimum else None

    chart = []
    for offset in range(CHART_DAYS - 1, -1, -1):
        day = end - timedelta(days=offset)
        week = weekly(day - timedelta(days=6), day, WEEK_MIN_WORN)
        usual = weekly(day - timedelta(days=27), day - timedelta(days=7), USUAL_MIN_WORN)
        chart.append({'date': day.isoformat(), 'load': daily.get(day.isoformat(), 0.) if day in worn else None,
                      'week_load': week, 'usual_week_load': usual})
    today = chart[-1]
    current = None
    if today['week_load'] is not None and today['usual_week_load']:
        change = today['week_load'] / today['usual_week_load'] - 1
        current = {'week_load': today['week_load'], 'usual_week_load': today['usual_week_load'],
                   'change': change, 'status': status(change)}
    recent = [row for row in rows if row['date'] >= (end - timedelta(days=6)).isoformat()]
    return {'current': current, 'days': chart,
            'week_workouts': {'rated': sum(r['rated'] for r in recent), 'estimated': sum(not r['rated'] for r in recent)},
            'worn_days': {'week': sum(end - timedelta(days=i) in worn for i in range(7)),
                          'usual': sum(end - timedelta(days=i) in worn for i in range(7, 28))}}
