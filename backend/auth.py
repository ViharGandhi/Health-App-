"""
auth.py
=======
Google OAuth2 PKCE flow for the Google Health API.

Flow:
  1. GET  /api/auth/login     → redirect user to Google consent screen
  2. GET  /api/auth/callback  → Google redirects back here with ?code=...
                                we exchange for access+refresh token
                                and store in a signed cookie session
  3. GET  /api/auth/status    → tells the frontend if user is connected
  4. POST /api/auth/disconnect → clears the session token

Required env vars (in .env):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BACKEND_URL, FRONTEND_URL, SECRET_KEY
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import base64
import secrets
import urllib.parse
from typing import Optional

import httpx
from validity import finite_number
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
BACKEND_URL   = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")
SECRET_KEY    = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

REDIRECT_URI  = f"{BACKEND_URL}/api/auth/callback"

# Google OAuth2 endpoints
AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
IDENTITY_URL = "https://health.googleapis.com/v4/users/me/identity"

# Google Health API scopes required
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
]

COOKIE_NAME = "soma_session"
OAUTH_COOKIE_NAME = "soma_oauth"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

# ──────────────────────────────────────────────────────────────────────────────
# Session helpers (signed cookie — no DB needed for personal use)
# ──────────────────────────────────────────────────────────────────────────────

_signer = URLSafeTimedSerializer(SECRET_KEY)


def _sign(data: dict) -> str:
    return _signer.dumps(data)


def _unsign(token: str) -> Optional[dict]:
    try:
        value = _signer.loads(token, max_age=COOKIE_MAX_AGE)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def get_session(request: Request) -> Optional[dict]:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    return _unsign(cookie)


def set_session(response: Response, data: dict) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=_sign(data),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=BACKEND_URL.startswith("https://"),
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


# ──────────────────────────────────────────────────────────────────────────────
# Token refresh
# ──────────────────────────────────────────────────────────────────────────────

async def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Exchange a refresh token for a new access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type":    "refresh_token",
        })
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _valid_tokens(tokens) -> bool:
    if not isinstance(tokens, dict):
        return False
    expires = tokens.get('expires_in', 3600)
    return (isinstance(tokens.get('access_token'), str) and bool(tokens['access_token'])
            and finite_number(expires) and expires > 0
            and isinstance(tokens.get('refresh_token', ''), str))


async def get_valid_access_token(session: dict) -> Optional[str]:
    """
    Returns a valid access token from the session, refreshing if needed.
    Updates session in-place with new token data.
    """
    if not isinstance(session, dict) or not session:
        return None
    expires_at = session.get("expires_at", 0)
    if not finite_number(expires_at):
        return None
    if time.time() < expires_at - 60:  # 60s buffer
        token = session.get('access_token')
        return token if isinstance(token, str) and token else None
    # Token expired — refresh
    refresh = session.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        return None
    new_tokens = await refresh_access_token(refresh)
    if not _valid_tokens(new_tokens):
        return None
    session["access_token"] = new_tokens["access_token"]
    session["refresh_token"] = new_tokens.get("refresh_token", refresh)
    session["expires_at"]   = time.time() + new_tokens.get("expires_in", 3600)
    return session["access_token"]


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirect the user to Google's OAuth consent screen."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return JSONResponse(
            {"error": "Google OAuth credentials are not configured. Please set up your .env file."},
            status_code=503,
        )
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(url)
    response.set_cookie(
        OAUTH_COOKIE_NAME, _sign({"state": state, "verifier": verifier}),
        max_age=600, httponly=True, samesite="lax",
        secure=BACKEND_URL.startswith("https://"),
    )
    return response


@router.get("/callback")
async def callback(request: Request, code: str = "", error: str = "", state: str = ""):
    """Handle Google's redirect back with auth code; exchange for tokens."""
    oauth = _unsign(request.cookies.get(OAUTH_COOKIE_NAME, ""))
    if not oauth or not secrets.compare_digest(state, oauth.get("state", "")):
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=invalid_state")
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error={urllib.parse.quote(error)}")
    if not code:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=no_code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(TOKEN_URL, data={
            "code":          code,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
            "code_verifier": oauth["verifier"],
        })

    if token_resp.status_code != 200:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=token_exchange_failed")

    try:
        tokens = token_resp.json()
    except ValueError:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=token_exchange_failed")
    if not _valid_tokens(tokens):
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=token_exchange_failed")

    # OAuth can succeed for a Google account with no Google Health profile.
    async with httpx.AsyncClient() as client:
        identity_resp = await client.get(
            IDENTITY_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    if identity_resp.status_code != 200:
        failure = "health_account_not_linked" if identity_resp.status_code == 400 else "health_access_failed"
        return RedirectResponse(f"{FRONTEND_URL}/connect?error={failure}")

    # Fetch user profile
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    user_info = user_resp.json() if user_resp.status_code == 200 else {}

    session_data = {
        "health_user_id": identity_resp.json().get("healthUserId"),
        "access_token":  tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at":    time.time() + tokens.get("expires_in", 3600),
        "user_email":    user_info.get("email", ""),
        "user_name":     user_info.get("name", ""),
    }

    response = RedirectResponse(f"{FRONTEND_URL}/?connected=true")
    response.delete_cookie(OAUTH_COOKIE_NAME)
    set_session(response, session_data)
    return response


@router.get("/status")
async def status(request: Request, response: Response):
    """Returns connection status. Frontend polls this on load."""
    session = get_session(request)
    if not session:
        return {"connected": False, "is_mock": True, "can_connect": bool(CLIENT_ID and CLIENT_SECRET), "user_email": None, "user_name": None}
    old_token = session.get("access_token")
    token = await get_valid_access_token(session)
    if not token:
        return {"connected": False, "is_mock": True, "can_connect": bool(CLIENT_ID and CLIENT_SECRET), "user_email": None, "user_name": None}
    if token != old_token:
        set_session(response, session)
    return {
        "connected":  True,
        "is_mock":    False,
        "can_connect": True,
        "user_email": session.get("user_email"),
        "user_name":  session.get("user_name"),
    }


@router.post("/disconnect")
async def disconnect(request: Request):
    """Clear session cookie — user returns to mock mode."""
    response = JSONResponse({"disconnected": True})
    clear_session(response)
    return response
