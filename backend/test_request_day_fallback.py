from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import Request

from main import _client_day


def test_missing_date_uses_request_timezone():
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 23, 30, tzinfo=timezone.utc).astimezone(tz)
    request = Request({'type': 'http', 'headers': [(b'x-user-timezone', b'Pacific/Kiritimati')]})
    with patch('main.datetime', Clock):
        assert _client_day(request).isoformat() == '2026-10-08'
