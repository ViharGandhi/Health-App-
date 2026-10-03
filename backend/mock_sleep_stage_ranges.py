"""Varied, date-seeded Google v4 fixtures. These are synthetic, not wearable readings."""

from datetime import date, datetime, time, timedelta, timezone
import random

from sleep_stage_ranges import DEFAULT_CONFIG, adapt_google_sleep, stage_stats, score_stages


def mock_stage_points(today: date, days: int = 45) -> list[dict]:
    points = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        if day.toordinal() % 13 == 0 and offset:
            continue  # Device not worn: a genuine gap.
        rng = random.Random(day.toordinal() + 7731)
        start = datetime.combine(day - timedelta(days=1), time(21), timezone.utc) + timedelta(minutes=rng.randint(-90, 110))
        duration = rng.randint(350, 590)
        weights = [rng.uniform(0, 0.12), rng.uniform(0.42, 0.66), rng.uniform(0.06, 0.26), rng.uniform(0.12, 0.32)]
        if day.toordinal() % 11 == 0:
            weights[2] = 0  # A valid zero-deep night.
        amounts = [int(duration * w / sum(weights)) for w in weights]
        amounts[1] += duration - sum(amounts)
        cursor, stages = start, []
        for cycle in range(4):
            for stage, amount in zip(("AWAKE", "LIGHT", "DEEP", "REM"), amounts):
                minutes = amount // 4 + (1 if cycle < amount % 4 else 0)
                if minutes:
                    end = cursor + timedelta(minutes=minutes)
                    stages.append({"startTime": cursor.isoformat(), "endTime": end.isoformat(), "type": stage})
                    cursor = end
        sleep_type = "CLASSIC" if day.toordinal() % 17 == 0 and offset else "STAGES"
        processed = not (day.toordinal() % 19 == 0 and offset)
        if sleep_type == "CLASSIC":
            stages = [{"startTime": start.isoformat(), "endTime": cursor.isoformat(), "type": "ASLEEP"}]
        point = {"name": f"users/demo/dataTypes/sleep/dataPoints/demo-{day.isoformat()}",
                 "dataSource": {"platform": "FITBIT"}, "sleep": {
            "interval": {"startTime": start.isoformat(), "endTime": cursor.isoformat(),
                         "startUtcOffset": "7200s", "endUtcOffset": "7200s"},
            "type": sleep_type, "stages": stages,
            "shortAwakenings": [{"startTime": (start + timedelta(minutes=100)).isoformat(),
                                 "endTime": (start + timedelta(minutes=101)).isoformat(), "type": "AWAKE"}],
            "metadata": {"processed": processed, "stagesStatus": "SUCCEEDED" if processed else "STAGES_STATE_UNSPECIFIED",
                         "mainSleep": True, "nap": False},
        }}
        points.append(point)
    return points


def mock_stage_ranges(today: date, days: int, config=DEFAULT_CONFIG) -> list[dict]:
    observations = [adapt_google_sleep(p) for p in mock_stage_points(today, days + 40)]
    computed = [(night, *stage_stats(night, config)) for night in observations]
    history = [stats for _, stats, _ in computed if stats]
    start = today - timedelta(days=days - 1)
    return [{**(score_stages(stats, history, config) if stats else {
                "sleep_id": night.sleep_id, "night_date": night.night_date.isoformat(), "status": state, "stages": {}}),
             "computed_at": night.end_utc.isoformat()}
            for night, stats, state in computed if start <= night.night_date <= today]
