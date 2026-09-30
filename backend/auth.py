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
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

# ──────────────────────────────────────────────────────────────────────────────
# Session helpers (signed cookie — no DB needed for personal use)
# ──────────────────────────────────────────────────────────────────────────────

_signer = URLSafeTimedSerializer(SECRET_KEY)


def _sign(data: dict) -> str:
    return _signer.dumps(data)


def _unsign(token: str) -> Optional[dict]:
    try:
        return _signer.loads(token, max_age=COOKIE_MAX_AGE)
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
        secure=False,  # set True in production (HTTPS)
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
    return resp.json()


async def get_valid_access_token(session: dict) -> Optional[str]:
    """
    Returns a valid access token from the session, refreshing if needed.
    Updates session in-place with new token data.
    """
    if not session:
        return None
    expires_at = session.get("expires_at", 0)
    if time.time() < expires_at - 60:  # 60s buffer
        return session.get("access_token")
    # Token expired — refresh
    refresh = session.get("refresh_token")
    if not refresh:
        return None
    new_tokens = await refresh_access_token(refresh)
    if not new_tokens:
        return None
    session["access_token"] = new_tokens["access_token"]
    session["expires_at"]   = time.time() + new_tokens.get("expires_in", 3600)
    return session["access_token"]


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirect the user to Google's OAuth consent screen."""
    if not CLIENT_ID:
        return JSONResponse(
            {"error": "GOOGLE_CLIENT_ID not configured. Please set up your .env file."},
            status_code=503,
        )
    state = secrets.token_urlsafe(16)
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str = "", error: str = "", state: str = ""):
    """Handle Google's redirect back with auth code; exchange for tokens."""
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error={error}")
    if not code:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=no_code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(TOKEN_URL, data={
            "code":          code,
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        })

    if token_resp.status_code != 200:
        return RedirectResponse(f"{FRONTEND_URL}/connect?error=token_exchange_failed")

    tokens = token_resp.json()

    # Fetch user profile
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    user_info = user_resp.json() if user_resp.status_code == 200 else {}

    session_data = {
        "access_token":  tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at":    time.time() + tokens.get("expires_in", 3600),
        "user_email":    user_info.get("email", ""),
        "user_name":     user_info.get("name", ""),
    }

    response = RedirectResponse(f"{FRONTEND_URL}/?connected=true")
    set_session(response, session_data)
    return response


@router.get("/status")
async def status(request: Request):
    """Returns connection status. Frontend polls this on load."""
    session = get_session(request)
    if not session:
        return {"connected": False, "is_mock": True, "user_email": None, "user_name": None}
    return {
        "connected":  True,
        "is_mock":    False,
        "user_email": session.get("user_email"),
        "user_name":  session.get("user_name"),
    }


@router.post("/disconnect")
async def disconnect(request: Request):
    """Clear session cookie — user returns to mock mode."""
    response = JSONResponse({"disconnected": True})
    clear_session(response)
    return response
