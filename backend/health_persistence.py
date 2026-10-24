"""Capture complete provider downloads; failed pagination never advances cursors."""
import asyncio
from datetime import timedelta
from contextvars import ContextVar
from functools import wraps

_pages = ContextVar('normalized_provider_pages', default=None)


def capture_page(payload):
    pages = _pages.get()
    if pages is not None:
        pages.append(payload)


def normalized_fetch(function):
    @wraps(function)
    async def fetch(client, kind, expression, **options):
        db, account = getattr(client, 'database', None), getattr(client, 'db_account', None)
        if db is None or account is None:
            return await function(client, kind, expression, **options)
        sync_id = await asyncio.to_thread(db.start_sync, account['provider_account_id'], kind, expression)
        pages = []
        context = _pages.set(pages)
        try:
            points = await function(client, kind, expression, **options)
            endpoint = f'https://health.googleapis.com/v4/users/me/dataTypes/{kind}/dataPoints' + (':reconcile' if options.get('reconcile', True) else '')
            await asyncio.to_thread(db.ingest, account['provider_account_id'], kind, points, pages=pages,
                                    endpoint=endpoint, sync_id=sync_id, expression=expression)
            return points
        except BaseException as error:
            await asyncio.to_thread(db.fail_sync, sync_id, type(error).__name__)
            raise
        finally:
            _pages.reset(context)
    return fetch


def normalized_steps(function):
    @wraps(function)
    async def fetch(client, start, end):
        db, account = getattr(client, 'database', None), getattr(client, 'db_account', None)
        if db is None or account is None:
            return await function(client, start, end)
        expression = f'steps.date >= "{start}" AND steps.date < "{end + timedelta(days=1)}"'
        sync_id = await asyncio.to_thread(db.start_sync, account['provider_account_id'], 'steps', expression)
        pages = []
        context = _pages.set(pages)
        try:
            values = await function(client, start, end)
            await asyncio.to_thread(db.save_steps, account['provider_account_id'], values, pages=pages, sync_id=sync_id)
            return values
        except BaseException as error:
            await asyncio.to_thread(db.fail_sync, sync_id, type(error).__name__)
            raise
        finally:
            _pages.reset(context)
    return fetch
