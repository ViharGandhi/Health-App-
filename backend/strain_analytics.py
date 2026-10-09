"""Display aggregates from the same HRR/TRIMP result used by /api/strain."""

from datetime import date, timedelta
from statistics import mean

from sleep_trends import range_start


ZONE_KEYS = tuple(f"zone{i}" for i in range(1, 6))
METRICS = ("strain", "zones_1_3", "zones_4_5", "strength", "steps")
STRENGTH_TYPES = {"WEIGHTLIFTING", "WEIGHT_MACHINES", "WEIGHTS", "STRENGTH_TRAINING",
                  "FREE_WEIGHTS", "FUNCTIONAL_STRENGTH_TRAINING", "POWERLIFTING", "RESISTANCE_BANDS"}


def strain_range_start(end: date, timeframe: str, metric: str) -> date:
    if timeframe == "M" and metric in ("zones_1_3", "zones_4_5", "strength"):
        return end - timedelta(days=27)
    return range_start(end, timeframe)


def metric_value(day: dict, metric: str):
    if metric == "strain":
        return day["score"]
    if metric in ("strength", "steps"):
        return day["strength_minutes"] if metric == "strength" else day["steps"]
    zones = day["zones"]
    if zones is None:
        return None
    keys = ZONE_KEYS[:3] if metric == "zones_1_3" else ZONE_KEYS[3:]
    return sum(zones[key] for key in keys)


def strain_day(day: date, samples: list, sessions: list, snapshot, steps: int | None) -> dict:
    """Activity-only display zones; day cardio load still includes incidental effort."""
    lower, upper = snapshot.day_window['start'], snapshot.day_window['end']
    sessions = [session for session in sessions if session['end'] >= lower and session['start'] <= upper]
    zones = snapshot.activity_zone_minutes.model_dump() if snapshot.activity_zone_minutes is not None else None
    strength = {}
    activities = []
    for session in sessions:
        duration = session.get("active_minutes")
        if duration is None:
            duration = max(0, (session["end"] - session["start"]).total_seconds() / 60)
        name = session["activity_name"]
        if session.get("exercise_type") in STRENGTH_TYPES:
            strength[name] = strength.get(name, 0) + duration
        activities.append({"name": name, "start": session["start"].isoformat(), "end": session["end"].isoformat(),
                           "minutes": duration, "strain": next((workout.strain for workout in snapshot.workouts
                               if workout.start == session["start"] and workout.end == session["end"]), None)})
    return {"date": day.isoformat(), "score": snapshot.strain if snapshot.coverage > 0 and not snapshot.age_missing else None,
            "load": snapshot.load, "coverage": snapshot.coverage, "low_coverage": snapshot.low_coverage,
            "zones": zones, "strength_minutes": sum(strength.values()), "strength_activities": strength,
            "steps": steps, "activities": activities}


def build_strain_analytics(history: list[dict], current, start: date, end: date, timeframe: str, metric: str, is_mock: bool, today: date) -> dict:
    previous_end = start - timedelta(days=1)
    previous_start = strain_range_start(previous_end, timeframe, metric)
    days = [day for day in history if start.isoformat() <= day["date"] <= end.isoformat()]
    previous = [day for day in history if previous_start.isoformat() <= day["date"] <= previous_end.isoformat()]
    prior = [day for day in history if (end - timedelta(days=30)).isoformat() <= day["date"] < end.isoformat()]
    averages = {}
    for key in METRICS:
        values = [metric_value(day, key) for day in prior]
        valid = [value for value in values if value is not None]
        averages[key] = mean(valid) if valid else None
    return {"date": end.isoformat(), "today": today.isoformat(), "timeframe": timeframe, "range_start": start.isoformat(), "range_end": end.isoformat(),
            "previous_range_start": previous_start.isoformat(), "previous_range_end": previous_end.isoformat(),
            "is_mock": is_mock, "current": current.model_dump(mode='json'), "days": days, "previous_days": previous,
            "prior_30_day_averages": averages}


