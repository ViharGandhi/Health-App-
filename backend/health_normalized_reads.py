"""Compatibility reads from normalized records when the old cache is empty."""
from datetime import date


def resting_hr_points(db, user, query):
    with db.connect() as conn:
        rows = conn.execute('SELECT r.* FROM sleeping_hr_results r JOIN calc_runs c USING(calc_run_id) WHERE r.user_id=? AND c.is_current=1 AND r.sleep_date>=? AND r.sleep_date<? AND r.bpm IS NOT NULL', (user, query.start[:10], query.end[:10])).fetchall()
    points = []
    for row in rows:
        day = date.fromisoformat(row['sleep_date'])
        points.append({'dailyRestingHeartRate': {'date': {'year': day.year, 'month': day.month, 'day': day.day}, 'beatsPerMinute': row['bpm'], 'dailyRestingHeartRateMetadata': {'calculationMethod': row['method']}}})
    return points


def daily_steps(db, user, start, end):
    with db.connect() as conn:
        return {r['metric_date']: int(r['value']) for r in conn.execute("SELECT metric_date,value FROM daily_measurements WHERE user_id=? AND metric_code='steps' AND metric_date>=? AND metric_date<=?", (user, str(start), str(end)))}


def awake_baseline(db, user, day):
    with db.connect() as conn:
        row = conn.execute('SELECT r.* FROM awake_hr_results r JOIN calc_runs c USING(calc_run_id) WHERE r.user_id=? AND r.source_date=? AND c.is_current=1 ORDER BY c.calc_run_id DESC LIMIT 1', (user, str(day))).fetchone()
    return {'date': str(day), 'value': row['mean_bpm'], 'sample_count': row['retained_count'], 'status': 'ok' if row['mean_bpm'] is not None else 'no_readings'} if row else None
