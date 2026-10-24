"""Local account's 22:00 job, using its configured signed session cookie."""
import asyncio
from datetime import datetime, time, timedelta, timezone
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

from awake_heart_rate import collect_awake_hr, read_baseline


async def run_due(now=None):
    # Reload the file so replacing an expired cookie needs no server restart.
    settings = {**dotenv_values(Path(__file__).with_name('.env')), **os.environ}
    cookie = settings.get('GOOGLE_HEALTH_SESSION_COOKIE', '')
    if cookie.startswith('soma_session='):
        cookie = cookie.split('=', 1)[1].split(';', 1)[0]
    from auth import _unsign, get_valid_access_token
    from google_health_client import GoogleHealthClient
    session = _unsign(cookie) if cookie else None
    if not session or not session.get('health_user_id'):
        # After migration, persisted active jobs and encrypted refresh tokens
        # keep working beyond the bootstrap cookie's lifetime.
        from health_database import database
        db = database()
        with db.connect() as conn:
            accounts = conn.execute("SELECT DISTINCT a.*,u.timezone FROM scheduled_jobs j JOIN provider_accounts a USING(provider_account_id) JOIN users u ON u.user_id=a.user_id WHERE j.job_type='awake_hr' AND j.enabled=1 AND a.status='active'").fetchall()
        for account in accounts:
            credentials = await asyncio.to_thread(db.credentials, account['provider_account_id'])
            if credentials:
                await _run_session({'health_user_id': account['provider_user_id'], **credentials}, ZoneInfo(account['timezone']), now)
        return
    tz = ZoneInfo(settings.get('AWAKE_HR_TIMEZONE', 'Asia/Calcutta'))
    await _run_session(session, tz, now)


async def _run_session(session, tz, now=None):
    from auth import get_valid_access_token
    from google_health_client import GoogleHealthClient
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(tz).date()
    client = GoogleHealthClient('scheduled', cache=True, account_id=session['health_user_id'])
    client.strain_timezone = tz
    if getattr(client, 'database', None) is not None:
        if client.db_account['status'] != 'active':
            return
        credentials = await asyncio.to_thread(client.database.credentials, client.db_account['provider_account_id'])
        if credentials:
            session.update(credentials)
    # Yesterday repairs today's score; today supplies tomorrow after 22:00.
    days = [today - timedelta(days=1)]
    if now >= datetime.combine(today, time(22), tzinfo=tz):
        days.append(today)
    for day in days:
        saved = await asyncio.to_thread(read_baseline, client.store, client.account_key, day, tz)
        if saved and saved['status'] == 'ok':
            continue
        token = await get_valid_access_token(session)
        if not token:
            raise ValueError('Reconnect Google Health for the scheduled awake HR job')
        if getattr(client, 'database', None) is not None:
            await asyncio.to_thread(client.database.save_credentials, client.db_account['provider_account_id'], session)
        client.headers['Authorization'] = f'Bearer {token}'
        await collect_awake_hr(client, day, now=now)
    if getattr(client, 'database', None) is not None:
        with client.database.connect() as conn:
            next_due = datetime.combine(today + timedelta(days=1 if now >= datetime.combine(today, time(22), tzinfo=tz) else 0), time(22), tzinfo=tz)
            conn.execute("UPDATE scheduled_jobs SET last_run_at=?,last_status='ok',next_run_at=? WHERE provider_account_id=? AND job_type='awake_hr'", (int(now.timestamp()), int(next_due.timestamp()), client.db_account['provider_account_id']))


async def scheduler_loop():
    retry_at = 0.
    while True:
        try:
            if asyncio.get_running_loop().time() >= retry_at:
                await run_due()
        except Exception as error:
            # No provider payloads, session cookies or tokens in logs.
            logging.getLogger('uvicorn.error').warning('Awake HR daily job failed (%s); retrying in five minutes', type(error).__name__)
            retry_at = asyncio.get_running_loop().time() + 300
        else:
            retry_at = asyncio.get_running_loop().time() + 300
        # Wake exactly on the next local 22:00 boundary; otherwise check for
        # replaced cookies / missed work every five minutes.
        settings = dotenv_values(Path(__file__).with_name('.env'))
        tz = ZoneInfo(os.getenv('AWAKE_HR_TIMEZONE') or settings.get('AWAKE_HR_TIMEZONE') or 'Asia/Calcutta')
        now = datetime.now(tz)
        due = datetime.combine(now.date(), time(22), tzinfo=tz)
        if due <= now:
            due += timedelta(days=1)
        delay = min(300, max(.1, due.timestamp() - now.timestamp()))
        await asyncio.sleep(delay)
        if delay < 300:
            retry_at = 0.
