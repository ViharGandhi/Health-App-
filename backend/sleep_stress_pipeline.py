"""Fetch, adapt, score, and upsert connected sleep stress nights."""

from __future__ import annotations

from datetime import date, timedelta

from google_health_client import GoogleHealthClient
from sleep_stress import adapt_google_hr, adapt_google_hrv, adapt_google_sleep, prepare_night, score_night
from sleep_stress_store import SleepStressStore


async def compute_connected_sleep_stress(
    client: GoogleHealthClient, start: date, end: date, anchor: str | None, store: SleepStressStore,
) -> list[dict]:
    raw_sleep, raw_hrv, raw_hr = await client.get_sleep_stress_points(start - timedelta(days=14), end)
    samples = [adapt_google_hr(point) for point in raw_hr]
    candidates = {}
    for candidate in ((anchor,) if anchor else ("start", "end")):
        windows = adapt_google_hrv(raw_hrv, candidate)
        candidates[candidate] = sorted((prepare_night(adapt_google_sleep(point), windows, samples)
                          for point in raw_sleep), key=lambda item: item.night.end_utc)
    prepared = candidates[anchor or "start"]
    nights = []
    for item in prepared:
        if start <= item.night.night_date <= end and not item.night.nap:
            scored = score_night(item, prepared)
            scored["alignment_verified"] = anchor is not None
            scored['anchor_verification'] = 'operator_configured' if anchor else 'unconfigured'
            if anchor:
                store.upsert(scored, item)
            else:
                other = next(n for n in candidates["end"] if n.night.sleep_id == item.night.sleep_id)
                alternative = score_night(other, candidates["end"])
                scored["nights_available"] = min(scored["nights_available"], alternative["nights_available"])
                scored["baseline"]["nights_used"] = scored["nights_available"]
                scored["valid_minutes"] = min(scored["valid_minutes"], alternative["valid_minutes"])
                scored["coverage"] = min(scored["coverage"], alternative["coverage"])
                if alternative["status"] == "insufficient_baseline":
                    scored["status"] = "insufficient_baseline"
                elif scored["status"] == "ok":
                    scored["status"] = "timing_unverified"
                for key in ("stress_pct", "stressed_minutes", "stressed_hours", "peak_level", "mean_level", "hrv_only_minutes"):
                    scored[key] = None
                scored["episodes"] = []
                scored["confidence"] = "low"
                scored['withheld_reason'] = 'hrv_anchor_unconfigured'
            nights.append(scored)
    return nights
