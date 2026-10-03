"""Manual backfill and durable job worker for the personal account."""

import argparse
import asyncio
from datetime import date, timedelta
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from google_health_client import GoogleHealthClient
from mock_sleep_stage_ranges import mock_stage_ranges
from sleep_stage_pipeline import sync_stage_ranges, run_stage_jobs
from sleep_stage_webhooks import stage_store


async def run(args):
    if args.demo:
        print(json.dumps({"is_mock": True, "nights": mock_stage_ranges(args.end_date, args.days)}, indent=2))
        return
    token = os.getenv("GOOGLE_HEALTH_ACCESS_TOKEN")
    if not token:
        raise SystemExit("GOOGLE_HEALTH_ACCESS_TOKEN is required; expired tokens must be renewed through OAuth")
    client = GoogleHealthClient(token)
    user_id = await client.get_health_user_id()
    if args.raw_output:
        points = await client.get_sleep_stage_points(args.end_date, args.end_date)
        args.raw_output.write_text(json.dumps(points, indent=2), encoding="utf-8")
        print(f"Saved {len(points)} raw sleep records for live adapter inspection")
        return
    store = stage_store()
    if args.jobs:
        await run_stage_jobs(client, user_id, store)
    else:
        results = await sync_stage_ranges(client, user_id, store, args.end_date - timedelta(days=args.days - 1), args.end_date)
        print(f"Updated {len(results)} nightly records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--jobs", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--raw-output", type=Path, help="Save one recent day's raw API JSON for discovery; contains health data")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("days must be positive")
    load_dotenv(Path(__file__).with_name(".env"))
    asyncio.run(run(args))
