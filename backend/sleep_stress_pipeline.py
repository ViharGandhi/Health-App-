"""Fetch, adapt, score, and upsert connected sleep stress nights."""

from __future__ import annotations

from datetime import date, timedelta

from google_health_client import GoogleHealthClient
from sleep_stress import adapt_google_hr, adapt_google_hrv, adapt_google_sleep, prepare_night, score_night
from sleep_stress_store import SleepStressStore


async def compute_connected_sleep_stress(
    client: GoogleHealthClient, start: date, end: date, anchor: str, store: SleepStressStore,
) -> list[dict]:
    raw_sleep, raw_hrv, raw_hr = await client.get_sleep_stress_points(start - timedelta(days=14), end)
    windows = adapt_google_hrv(raw_hrv, anchor)
    samples = [adapt_google_hr(point) for point in raw_hr]
    prepared = sorted((prepare_night(adapt_google_sleep(point), windows, samples)
                       for point in raw_sleep), key=lambda item: item.night.end_utc)
    nights = []
    for item in prepared:
        if start <= item.night.night_date <= end and not item.night.nap:
            scored = score_night(item, prepared)
            store.upsert(scored, item)
            nights.append(scored)
    return nights
