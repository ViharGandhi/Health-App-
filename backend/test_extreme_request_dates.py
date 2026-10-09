from fastapi.testclient import TestClient
from main import app
import pytest


@pytest.mark.parametrize('day', ['0001-01-01', '0001-01-05', '9999-12-31'])
@pytest.mark.parametrize('route', ['/api/strain', '/api/recovery?demo=estimate', '/api/sleep', '/api/health'])
def test_unrepresentable_date_arithmetic_returns_clear_client_error(day, route):
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(route, headers={'X-User-Date': day})
    assert response.status_code == 400
    assert response.json()['detail']
