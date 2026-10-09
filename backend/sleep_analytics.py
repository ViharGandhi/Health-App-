"""Sleep cards from identifiable Google v4 main sleeps, with explicit missing values."""

from datetime import date, datetime, timedelta, timezone
import random

from sleep_heart_rate import local_time, select_sleep
from sleep_stage_ranges import adapt_google_sleep, stage_stats, instant
from sleep_trends import range_start
from sleep_consistency import SleepNight, score_main_sleep
from sleepscore import SleepCalculator, SleepData
from sleep_need_inputs import SleepNeedInputs, need_components
from provider_payload import payload_boundary


def demo_sleep_need_inputs(observations: list[dict], today: date, today_strain_pct: float | None = None) -> SleepNeedInputs:
    sleep = {date.fromisoformat(n["date"]): n["asleep_minutes"] for n in observations}
    start = min(sleep, default=today) - timedelta(days=1)
    strain = {start + timedelta(days=i): random.Random((start + timedelta(days=i + 1)).toordinal() + 821).uniform(3, 19) / 0.21
              for i in range((today - start).days + 1)}
    if today_strain_pct is not None:
        strain[today] = today_strain_pct
    return SleepNeedInputs(sleep, strain, {})


@payload_boundary
def sleep_observations(points: list[dict], today: date, *, is_mock: bool = False) -> list[dict]:
    # Select one completed main sleep per historical local wake date, as the HR chart does.
    now = datetime.fromisoformat(f"{today}T23:59:59+00:00") if is_mock else datetime.now(timezone.utc)
    by_day = {}
    for point in points:
        selected = select_sleep([point], today, now=now)
        if selected is None:
            continue
        interval = point["sleep"]["interval"]
        day = local_time(interval["endTime"], interval["endUtcOffset"])[:10]
        by_day.setdefault(day, []).append(point)
    observations = []
    for day, candidates in sorted(by_day.items()):
        point = select_sleep(candidates, today, now=now)
        sleep, night = point["sleep"], adapt_google_sleep(point)
        interval = sleep["interval"]
        start_local = local_time(interval["startTime"], interval["startUtcOffset"])
        end_local = local_time(interval["endTime"], interval["endUtcOffset"])
        stats, status = stage_stats(night)
        segments = [{"stage": s.stage, "start": s.start_utc.isoformat(), "end": s.end_utc.isoformat()}
                    for s in night.segments] if stats else []
        summary = sleep.get("summary", {})
        # Summary onset/wake offsets are minutes, not seconds. Physical period endpoints
        # remain distinct from sleep onset/wake, used by consistency.
        sleeping_segments = [s for s in night.segments if stats and s.stage != "awake"]
        onset = (datetime.fromisoformat(start_local) + timedelta(minutes=float(summary["minutesToFallAsleep"]))
                 if "minutesToFallAsleep" in summary else sleeping_segments[0].start_utc.astimezone(datetime.fromisoformat(start_local).tzinfo)
                 if sleeping_segments else datetime.fromisoformat(start_local))
        wake = (datetime.fromisoformat(end_local) - timedelta(minutes=float(summary["minutesAfterWakeUp"]))
                if "minutesAfterWakeUp" in summary else sleeping_segments[-1].end_utc.astimezone(datetime.fromisoformat(end_local).tzinfo)
                if sleeping_segments else datetime.fromisoformat(end_local))
        asleep = sum(stats.minutes[s] for s in ("light", "deep", "rem")) if stats else None
        period = (night.end_utc - night.start_utc).total_seconds() / 60
        awake = stats.minutes["awake"] if stats else None
        # Count the union of awakenings; short awakenings can overlap the stage timeline.
        awakenings = [(s.start_utc, s.end_utc) for s in night.segments if stats and s.stage == "awake"]
        if stats:
            awakenings += [(max(night.start_utc, instant(s["startTime"])), min(night.end_utc, instant(s["endTime"])))
                           for s in sleep.get("shortAwakenings", [])]
        merged = []
        for left, right in sorted(awakenings):
            if left >= right:
                continue
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        item = {"date": day, "sleep_id": point["name"], "status": status,
                "bed_time": start_local, "wake_time": end_local,
                "onset_time": onset.isoformat(), "sleep_wake_time": wake.isoformat(),
                "period_minutes": period, "asleep_minutes": asleep, "awake_minutes": awake,
                "deep_minutes": stats.minutes["deep"] if stats else None,
                "rem_minutes": stats.minutes["rem"] if stats else None,
                "efficiency": 100 * asleep / period if asleep is not None else None,
                "wake_events": len(merged) if stats else None, "segments": segments,
                "performance": None, "need_minutes": None, "need_components": None}
        observations.append(item)
    if is_mock:
        inputs = demo_sleep_need_inputs(observations, today)
        for item in observations:
            if item["status"] != "ok":
                continue
            need = inputs.for_tonight(date.fromisoformat(item["date"]) - timedelta(days=1))
            rng = random.Random(date.fromisoformat(item["date"]).toordinal() + 821)
            rng.uniform(3, 19)  # Retain the existing demo's HRV and HR readings.
            data = SleepData(item["asleep_minutes"] * 60, item["deep_minutes"] * 60, item["rem_minutes"] * 60,
                             (item["asleep_minutes"] - item["deep_minutes"] - item["rem_minutes"]) * 60,
                             item["awake_minutes"] * 60, item["period_minutes"] * 60,
                             datetime.fromisoformat(item["bed_time"]), datetime.fromisoformat(item["wake_time"]), item["wake_events"])
            item.update(performance=SleepCalculator.calculate_score(data, need.total_need_min / 60,
                        sleeping_hrv=rng.uniform(30, 65), sleeping_hr=rng.uniform(50, 65),
                        waking_hr=72, hrv_baseline=45, sleeping_hr_baseline=58),
                        need_minutes=need.total_need_min, need_components=need_components(need))
    return observations


def timing_records(observations: list[dict]) -> list[dict]:
    return [{"date": date.fromisoformat(n["date"]),
             "bed_time": datetime.fromisoformat(n["onset_time"]),
             "wake_time": datetime.fromisoformat(n["sleep_wake_time"]),
             "time_asleep_minutes": n["asleep_minutes"], "time_in_bed_minutes": n["period_minutes"]}
            for n in observations if datetime.fromisoformat(n["onset_time"]) < datetime.fromisoformat(n["sleep_wake_time"])]


def build_sleep_analytics(observations: list[dict], today: date, timeframe: str, is_mock: bool) -> dict:
    observations = [dict(night) for night in observations]
    start = range_start(today, timeframe)
    previous_end = start - timedelta(days=1)
    previous_start = range_start(previous_end, timeframe)
    records = timing_records(observations)
    by_date = {r["date"]: SleepNight(r["date"], r["bed_time"], r["wake_time"]) for r in records}
    for night in observations:
        timing = by_date.get(date.fromisoformat(night["date"]))
        night["consistency"] = score_main_sleep(timing, by_date).score if timing else None
        need, asleep = night["need_minutes"], night["asleep_minutes"]
        night["hours_percentage"] = min(100, 100 * asleep / need) if need and asleep is not None else None
        night["restorative"] = night["deep_minutes"] + night["rem_minutes"] if night["deep_minutes"] is not None else None
    by_day = {n["date"]: n for n in observations}
    days = []
    cursor = start
    while cursor <= today:
        days.append(by_day.get(cursor.isoformat(), {"date": cursor.isoformat(), "status": "no_sleep"}))
        cursor += timedelta(days=1)
    metrics = ("performance", "hours_percentage", "asleep_minutes", "need_minutes", "restorative", "consistency", "period_minutes", "efficiency")
    def averages(first, last):
        nights = [n for n in observations if first.isoformat() <= n["date"] <= last.isoformat()]
        return {key: (sum(values) / len(values) if values else None)
                for key in metrics for values in [[n[key] for n in nights if n.get(key) is not None]]}
    return {"is_mock": is_mock, 'estimator': 'legacy_composite_sleep', "timeframe": timeframe, "range_start": start.isoformat(), "range_end": today.isoformat(),
            "days": days, "averages": averages(start, today), "previous_averages": averages(previous_start, previous_end),
            "prior_30_averages": averages(today - timedelta(days=30), today - timedelta(days=1)),
            "notes": {"period": "Fitbit-recorded sleep period; not measured physical time in bed.",
                      "need": "App estimate. Earlier connected sleep-need and performance results are unavailable.",
                      "timing": "Dashed lines describe usual timing, not an optimal schedule."}}
