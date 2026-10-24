from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request

from google_health_client import GoogleHealthClient
from health_read_store import HealthReadStore, read_range


def sleep(owner, suffix='one'):
    return {'name': f'users/{owner}/dataTypes/sleep/dataPoints/{suffix}', 'sleep': {
        'interval': {'startTime': '2026-10-13T18:00:00Z', 'endTime': '2026-10-14T02:00:00Z',
                     'startUtcOffset': '0s', 'endUtcOffset': '0s'}}}


def write(store, account, points):
    query = read_range('sleep.interval.civil_end_time >= "2026-10-14" AND sleep.interval.civil_end_time < "2026-10-15"')
    store.range_write(account, 'sleep', query, False, points)
    return query


def test_reconnect_restores_only_verified_owner_and_persists_alias(tmp_path):
    path = tmp_path / 'health.db'
    store = HealthReadStore(path)
    query = write(store, 'legacy-email-hash', [sleep('123', 'one'), sleep('123', 'two')])
    write(store, 'unrelated', [sleep('456')])
    canonical = sha256(b'account:123').hexdigest()
    write(store, canonical, [sleep('123', 'one')])
    client = GoogleHealthClient('token', cache=True, account_id='123', store=store)
    assert client.account_key == 'legacy-email-hash'
    assert len(store.local_read(client.account_key, 'sleep', query, False)) == 2
    reopened = HealthReadStore(path)
    assert GoogleHealthClient('new-token', cache=True, account_id='123', store=reopened).account_key == client.account_key
    other = GoogleHealthClient('token', cache=True, account_id='789', store=reopened)
    assert other.account_key != client.account_key
    assert store.local_read(other.account_key, 'sleep', query, False) == []


def test_mixed_owner_cache_is_never_adopted(tmp_path):
    store = HealthReadStore(tmp_path / 'health.db')
    write(store, 'mixed', [sleep('123', 'one'), sleep('456', 'two')])
    key = sha256(b'account:123').hexdigest()
    assert store.health_account_key(key, '123') == key


def test_unverified_email_identity_cannot_adopt_history(tmp_path):
    store = HealthReadStore(tmp_path / 'health.db')
    write(store, 'old', [sleep('123')])
    assert store.health_account_key('new', 'an-email') == 'new'


def test_partition_registered_to_another_identity_cannot_be_adopted(tmp_path):
    store = HealthReadStore(tmp_path / 'health.db')
    write(store, 'legacy', [sleep('123')])
    with store.connection() as conn, conn:
        conn.execute('INSERT INTO health_account_aliases VALUES (?,?)', ('another-identity', 'legacy'))
    key = sha256(b'account:123').hexdigest()
    assert store.health_account_key(key, '123') == key


def test_empty_account_mapping_is_pinned_before_first_download(tmp_path):
    path = tmp_path / 'health.db'
    store = HealthReadStore(path)
    key = sha256(b'account:123').hexdigest()
    assert store.health_account_key(key, '123') == key
    # A later stale partition cannot steal the account mapping.
    write(store, 'later-cache', [sleep('123', 'one'), sleep('123', 'two')])
    assert HealthReadStore(path).health_account_key(key, '123') == key


def test_simultaneous_first_connections_use_one_permanent_mapping(tmp_path):
    store = HealthReadStore(tmp_path / 'health.db')
    key = sha256(b'account:123').hexdigest()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: store.health_account_key(key, '123'), range(4))) == [key] * 4
    with store.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM health_account_aliases').fetchone()[0] == 1


def test_connected_session_without_health_id_cannot_create_email_partition():
    from main import _google_client
    request = Request({'type': 'http', 'headers': []})
    with patch('main.get_session', return_value={'user_email': 'same@example.test'}), \
         patch('main.GoogleHealthClient', side_effect=AssertionError('email/token partition')):
        with pytest.raises(HTTPException) as error:
            _google_client('new-token', request)
        assert error.value.status_code == 401


def test_email_and_token_changes_preserve_permanent_storage_account(tmp_path):
    from main import _google_client
    store = HealthReadStore(tmp_path / 'health.db')
    query = write(store, 'legacy', [sleep('123')])
    request = Request({'type': 'http', 'headers': []})
    with patch('google_health_client.read_store', return_value=store):
        with patch('main.get_session', return_value={'health_user_id': '123', 'user_email': 'old@example.test'}):
            first = _google_client('old-token', request)
        with patch('main.get_session', return_value={'health_user_id': '123', 'user_email': 'new@example.test'}):
            second = _google_client('new-token', request)
    assert first.account_key == second.account_key == 'legacy'
    assert store.local_read(second.account_key, 'sleep', query, False) == [sleep('123')]
