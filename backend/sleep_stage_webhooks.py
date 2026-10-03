"""Authenticated Google Health webhook receiver; jobs survive process restarts."""

import base64
from datetime import date, timedelta
import json
import os
from pathlib import Path
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
import httpx
import tink
from tink import signature

from sleep_stage_store import SleepStageStore


router = APIRouter()
PUBLIC_KEYSET_URL = "https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json"
_verifier = None
_keyset_loaded_at = 0.0


def stage_store():
    return SleepStageStore(os.getenv("SLEEP_STAGE_DB_PATH", str(Path(__file__).with_name("data") / "sleep_stage_ranges.sqlite3")))


async def verify_notification(body: bytes, encoded_signature: str):
    global _verifier, _keyset_loaded_at
    try:
        sig = base64.b64decode(encoded_signature, validate=True)
    except ValueError as error:
        raise HTTPException(401, "Invalid webhook signature") from error
    signature.register()
    for attempt in range(2):
        if _verifier is None or time.monotonic() - _keyset_loaded_at > 3600 or attempt:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(PUBLIC_KEYSET_URL)
                response.raise_for_status()
            _verifier = tink.json_proto_keyset_format.parse_without_secret(response.text).primitive(signature.PublicKeyVerify)
            _keyset_loaded_at = time.monotonic()
        try:
            _verifier.verify(sig, body)
            return
        except tink.TinkError:
            pass  # Retry once with fresh keys to handle rotation.
    raise HTTPException(401, "Invalid webhook signature")


def enqueue_sleep_notifications(payload, store):
    notifications = payload if isinstance(payload, list) else [payload]
    jobs = []
    for notification in notifications:
        data = notification["data"]
        if data["dataType"] != "sleep":
            continue
        if data["operation"] not in ("UPSERT", "DELETE"):
            raise ValueError("Unsupported sleep notification operation")
        user_id = data["healthUserId"]
        for interval in data["intervals"]:
            civil = interval.get("civilIso8601TimeInterval")
            if civil:
                start, end = date.fromisoformat(civil["startTime"][:10]), date.fromisoformat(civil["endTime"][:10])
            else:
                civil = interval["civilDateTimeInterval"]
                def civil_date(field):
                    value = civil[field]["date"]
                    return date(value["year"], value["month"], value["day"])
                start, end = civil_date("startDateTime"), civil_date("endDateTime")
            if end < start or not user_id:
                raise ValueError("Invalid notification interval or user")
            key = data.get("recordId") or f"sleep-{start}-{end}"
            jobs.append((user_id, key, start - timedelta(days=1), end + timedelta(days=1)))
    for job in jobs:
        store.enqueue(*job)


@router.post("/api/webhooks/google-health/sleep-stages")
async def sleep_stage_webhook(request: Request):
    expected = os.getenv("GOOGLE_HEALTH_WEBHOOK_AUTHORIZATION", "")
    if not expected:
        raise HTTPException(503, "Webhook authorization is not configured")
    if not secrets.compare_digest(request.headers.get("Authorization", ""), expected):
        raise HTTPException(401, "Unauthorized webhook")
    body = await request.body()
    try:
        payload = json.loads(body)
    except ValueError as error:
        raise HTTPException(400, "Invalid notification JSON") from error
    if payload == {"type": "verification"}:
        return Response(status_code=200)  # Google's authorized subscriber handshake.
    signed = request.headers.get("GOOGLE-HEALTH-API-SIGNATURE")
    if not signed:
        raise HTTPException(401, "Missing webhook signature")
    await verify_notification(body, signed)
    try:
        enqueue_sleep_notifications(payload, stage_store())
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(400, "Invalid sleep notification") from error
    return Response(status_code=204)  # Processing is performed separately by the worker.
