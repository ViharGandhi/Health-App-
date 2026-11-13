"""What the user tells us: session effort ratings and morning check-ins.

Effort load is session RPE: effort (1-10, rated after any workout, grouped like
Apple Watch as Easy/Moderate/Hard/All Out) x minutes, in arbitrary units (Foster
2001; Lea et al. 2022 for resistance training). It is shown on its own and never
converted into the heart-rate 0-21 Strain.

Morning check-ins (1-5) are a single-item wellness rating (Saw et al. 2015). They
are stored so Recovery can later be compared with how the user felt.
"""

from datetime import date

SCHEMA = '''
CREATE TABLE IF NOT EXISTS user_effort_ratings (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    activity_id TEXT NOT NULL,
    activity_date TEXT NOT NULL,
    rpe INTEGER NOT NULL CHECK (rpe BETWEEN 1 AND 10),
    minutes REAL NOT NULL CHECK (minutes > 0 AND minutes <= 600),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, activity_id)
);
CREATE INDEX IF NOT EXISTS user_effort_ratings_by_date ON user_effort_ratings(user_id, activity_date);
CREATE TABLE IF NOT EXISTS user_morning_checkins (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    checkin_date TEXT NOT NULL,
    feeling INTEGER NOT NULL CHECK (feeling BETWEEN 1 AND 5),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, checkin_date)
);
'''


def _ensure(conn):
    conn.executescript(SCHEMA)


def save_effort(db, user: int, activity_id: str, day: date, rpe: int, minutes: float) -> dict:
    with db.connect() as conn:
        _ensure(conn)
        conn.execute('INSERT INTO user_effort_ratings(user_id,activity_id,activity_date,rpe,minutes) VALUES (?,?,?,?,?) '
                     'ON CONFLICT(user_id,activity_id) DO UPDATE SET activity_date=excluded.activity_date, rpe=excluded.rpe, '
                     'minutes=excluded.minutes, updated_at=CURRENT_TIMESTAMP',
                     (user, activity_id, day.isoformat(), rpe, minutes))
    return effort_row(activity_id, day.isoformat(), rpe, minutes)


def delete_effort(db, user: int, activity_id: str) -> None:
    with db.connect() as conn:
        _ensure(conn)
        conn.execute('DELETE FROM user_effort_ratings WHERE user_id=? AND activity_id=?', (user, activity_id))


def effort_row(activity_id: str, day: str, rpe: int, minutes: float) -> dict:
    return {'activity_id': activity_id, 'date': day, 'rpe': rpe, 'minutes': minutes, 'load': round(rpe * minutes)}


def efforts(db, user: int, start: date, end: date) -> dict:
    with db.connect() as conn:
        _ensure(conn)
        rows = conn.execute('SELECT activity_id, activity_date, rpe, minutes FROM user_effort_ratings '
                            'WHERE user_id=? AND activity_date BETWEEN ? AND ? ORDER BY activity_date',
                            (user, start.isoformat(), end.isoformat())).fetchall()
    ratings = [effort_row(*row) for row in rows]
    daily = {}
    for rating in ratings:
        daily[rating['date']] = daily.get(rating['date'], 0) + rating['load']
    return {'ratings': ratings, 'daily_load': daily}


def save_checkin(db, user: int, day: date, feeling: int) -> dict:
    with db.connect() as conn:
        _ensure(conn)
        conn.execute('INSERT INTO user_morning_checkins(user_id,checkin_date,feeling) VALUES (?,?,?) '
                     'ON CONFLICT(user_id,checkin_date) DO UPDATE SET feeling=excluded.feeling, updated_at=CURRENT_TIMESTAMP',
                     (user, day.isoformat(), feeling))
    return {'date': day.isoformat(), 'feeling': feeling}


def checkins(db, user: int, start: date, end: date) -> list[dict]:
    with db.connect() as conn:
        _ensure(conn)
        rows = conn.execute('SELECT checkin_date, feeling FROM user_morning_checkins WHERE user_id=? '
                            'AND checkin_date BETWEEN ? AND ? ORDER BY checkin_date',
                            (user, start.isoformat(), end.isoformat())).fetchall()
    return [{'date': day, 'feeling': feeling} for day, feeling in rows]
