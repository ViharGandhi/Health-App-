"""Manual 3-day late-sync backfill; schedule externally after live API validation."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from google_health_client import GoogleHealthClient
from sleep_stress_pipeline import compute_connected_sleep_stress
from sleep_stress_store import SleepStressStore


async def _run(today: date, days: int, token: str, anchor: str, database: Path) -> None:
    results = await compute_connected_sleep_stress(
        GoogleHealthClient(token), today - timedelta(days=days - 1), today,
        anchor, SleepStressStore(database),
    )
    print(f"Updated {len(results)} sleep session(s) through {today.isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    if not 1 <= args.days <= 31:
        parser.error("--days must be between 1 and 31")
    load_dotenv(Path(__file__).with_name(".env"))
    token = os.getenv("GOOGLE_HEALTH_ACCESS_TOKEN")
    anchor = os.getenv("SLEEP_STRESS_HRV_ANCHOR")
    if not token or anchor not in ("start", "end"):
        parser.error("A live access token and validated SLEEP_STRESS_HRV_ANCHOR are required")
    database = Path(os.getenv("SLEEP_STRESS_DB_PATH", str(Path(__file__).with_name("data") / "sleep_stress.sqlite3")))
    asyncio.run(_run(args.end_date, args.days, token, anchor, database))


if __name__ == "__main__":
    main()
