import hashlib
import base64
import unittest
import time
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from auth import router
from fastapi import FastAPI


class AuthTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_login_uses_matching_pkce_challenge_and_state_cookie(self):
        with patch("auth.CLIENT_ID", "client"), patch("auth.CLIENT_SECRET", "secret"):
            response = self.client.get("/api/auth/login", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        params = parse_qs(urlparse(response.headers["location"]).query)
        from auth import _unsign, OAUTH_COOKIE_NAME
        oauth = _unsign(response.cookies[OAUTH_COOKIE_NAME])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(oauth["verifier"].encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(params["state"], [oauth["state"]])
        self.assertEqual(params["code_challenge"], [challenge])
        self.assertEqual(params["code_challenge_method"], ["S256"])

    def test_callback_rejects_state_without_exchanging_code(self):
        response = self.client.get("/api/auth/callback?code=sample&state=wrong", follow_redirects=False)
        self.assertIn("error=invalid_state", response.headers["location"])

    def test_callback_does_not_connect_unlinked_health_account(self):
        with patch("auth.CLIENT_ID", "client"), patch("auth.CLIENT_SECRET", "secret"):
            login = self.client.get("/api/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
        requests = []

        def respond(request):
            requests.append(request)
            if request.url.path == "/token":
                return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
            return httpx.Response(400, json={"error": {"status": "ACCOUNT_NOT_LINKED"}})

        original_client = httpx.AsyncClient
        with patch("auth.httpx.AsyncClient", side_effect=lambda: original_client(transport=httpx.MockTransport(respond))):
            callback = self.client.get(f"/api/auth/callback?code=sample&state={state}", follow_redirects=False)
        self.assertIn("error=health_account_not_linked", callback.headers["location"])
        self.assertEqual([r.url.path for r in requests], ["/token", "/v4/users/me/identity"])
        self.assertNotIn("soma_session", callback.cookies)

    def test_status_persists_refreshed_access_token(self):
        from auth import _sign, _unsign, COOKIE_NAME
        self.client.cookies.set(COOKIE_NAME, _sign({
            "access_token": "old", "refresh_token": "refresh",
            "expires_at": time.time() - 1, "user_email": "test@example.com",
        }))
        with patch("auth.refresh_access_token", new=AsyncMock(return_value={"access_token": "new", "expires_in": 3600})):
            response = self.client.get("/api/auth/status")
        self.assertTrue(response.json()["connected"])
        self.assertEqual(_unsign(response.cookies[COOKIE_NAME])["access_token"], "new")


if __name__ == "__main__":
    unittest.main()
