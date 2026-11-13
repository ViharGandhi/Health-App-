import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main
import user_inputs
from health_database import HealthDatabase


HEADERS = {'X-User-Date': '2026-11-13', 'X-User-Timezone': 'UTC'}


@pytest.fixture
def owner():
    with tempfile.TemporaryDirectory() as directory:
        db = HealthDatabase(Path(directory) / 'health.sqlite3')
        user = db.ensure_account('provider-user')['user_id']
        yield db, user


def test_effort_load_is_rpe_times_minutes_and_upserts(owner):
    db, user = owner
    user_inputs.save_effort(db, user, 'a1', date(2026, 11, 12), 7, 50)
    user_inputs.save_effort(db, user, 'a1', date(2026, 11, 12), 8, 50)
    user_inputs.save_effort(db, user, 'a2', date(2026, 11, 12), 5, 30)
    result = user_inputs.efforts(db, user, date(2026, 11, 1), date(2026, 11, 13))
    assert [r['load'] for r in result['ratings']] == [400, 150]
    assert result['daily_load'] == {'2026-11-12': 550}
    user_inputs.delete_effort(db, user, 'a2')
    assert user_inputs.efforts(db, user, date(2026, 11, 1), date(2026, 11, 13))['daily_load'] == {'2026-11-12': 400}


def test_checkins_upsert_per_day_and_stay_per_user(owner):
    db, user = owner
    other = db.ensure_account('someone-else')['user_id']
    user_inputs.save_checkin(db, user, date(2026, 11, 13), 2)
    user_inputs.save_checkin(db, user, date(2026, 11, 13), 4)
    assert user_inputs.checkins(db, user, date(2026, 11, 1), date(2026, 11, 13)) == [{'date': '2026-11-13', 'feeling': 4}]
    assert user_inputs.checkins(db, other, date(2026, 11, 1), date(2026, 11, 13)) == []


def test_endpoints_validate_and_round_trip(owner):
    client = TestClient(main.app)
    with patch.object(main, '_input_owner', AsyncMock(return_value=owner)):
        saved = client.put('/api/effort', headers=HEADERS, json={'activity_id': 'abc', 'date': '2026-11-13', 'rpe': 6, 'minutes': 45})
        assert saved.status_code == 200 and saved.json()['load'] == 270
        for body in ({'activity_id': 'abc', 'date': '2026-11-13', 'rpe': 11, 'minutes': 45},
                     {'activity_id': 'abc', 'date': '2026-11-13', 'rpe': 6, 'minutes': 0},
                     {'activity_id': 'a b', 'date': '2026-11-13', 'rpe': 6, 'minutes': 45}):
            assert client.put('/api/effort', headers=HEADERS, json=body).status_code == 422
        assert client.put('/api/effort', headers=HEADERS, json={'activity_id': 'abc', 'date': '2026-11-14', 'rpe': 6, 'minutes': 45}).status_code == 400
        assert client.get('/api/effort', headers=HEADERS).json()['daily_load'] == {'2026-11-13': 270}
        assert client.put('/api/checkins', headers=HEADERS, json={'date': '2026-11-13', 'feeling': 6}).status_code == 422
        assert client.put('/api/checkins', headers=HEADERS, json={'date': '2026-11-13', 'feeling': 3}).status_code == 200
        assert client.get('/api/checkins', headers=HEADERS).json() == {'checkins': [{'date': '2026-11-13', 'feeling': 3}]}


def test_saving_needs_a_connected_account():
    response = TestClient(main.app).put('/api/checkins', headers=HEADERS, json={'date': '2026-11-13', 'feeling': 3})
    assert response.status_code == 401
