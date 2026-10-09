"""Personal, descriptive sleep-stage ranges; never clinical reference intervals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median
import logging
from validity import finite_number


STAGES = ("awake", "light", "deep", "rem")
METRICS = STAGES + ("restorative",)
ALGO_VERSION = "sleep-stage-ranges-2"


@dataclass(frozen=True)
class StageRangeConfig:
    window_nights: int = 7
    min_nights: int = 4
    denominator: str = "time_in_bed"
    spread_scale: float = 1.4826
    spread_floor_pct: float = 1.0
    min_sleep_hours: float = 3.0

    def __post_init__(self):
        if not 1 <= self.min_nights <= self.window_nights:
            raise ValueError("Require 1 <= min_nights <= window_nights")
        if self.denominator not in ("time_in_bed", "time_asleep"):
            raise ValueError("Unknown denominator")
        if any(not finite_number(value) or value <= 0
               for value in (self.spread_scale, self.spread_floor_pct, self.min_sleep_hours)):
            raise ValueError("Spread and sleep limits must be positive")


DEFAULT_CONFIG = StageRangeConfig()


@dataclass(frozen=True)
class StageSegment:
    start_utc: datetime
    end_utc: datetime
    stage: str


@dataclass(frozen=True)
class SleepNight:
    sleep_id: str
    night_date: date
    start_utc: datetime
    end_utc: datetime
    type: str
    stages_status: str
    processed: bool
    segments: tuple[StageSegment, ...]
    nap: bool = False
    main_sleep: bool | None = None


@dataclass(frozen=True)
class NightStageStats:
    sleep_id: str
    night_date: date
    start_utc: datetime
    end_utc: datetime
    total_minutes: float
    minutes: dict[str, float]
    pct: dict[str, float | None]
    denominator: str


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Physical timestamps must carry a UTC offset")
    return parsed.astimezone(timezone.utc)


def adapt_google_sleep(point: dict) -> SleepNight:
    """Documented v4 DataPoint, not yet checked against a live Fitbit Air response.

    RFC3339 timestamps: sleep.interval.startTime/endTime; stages[].type and
    stages[].startTime/endTime. endUtcOffset is a seconds-duration string used
    for the historical local wake date (including DST/travel). Processing:
    sleep.metadata.processed/stagesStatus. Ignore shortAwakenings entirely:
    they may overlap stages. Do not substitute summary stage minutes.
    """
    sleep = point["sleep"]
    interval, metadata = sleep["interval"], sleep.get("metadata", {})
    end = instant(interval["endTime"])
    offset = float(interval["endUtcOffset"].removesuffix("s"))
    return SleepNight(
        point["name"], (end + timedelta(seconds=offset)).date(),
        instant(interval["startTime"]), end, sleep.get("type", ""),
        metadata.get("stagesStatus", ""), metadata.get("processed") is True,
        tuple(StageSegment(instant(s["startTime"]), instant(s["endTime"]), s["type"].lower())
              for s in sleep.get("stages", [])),
        metadata.get("nap") is True, metadata.get("mainSleep"),
    )


def stage_stats(night: SleepNight, config: StageRangeConfig = DEFAULT_CONFIG) -> tuple[NightStageStats | None, str]:
    if night.type == "CLASSIC":
        return None, "stage_breakdown_unavailable"
    if night.type != "STAGES":
        return None, "stage_breakdown_unavailable"
    if not night.processed or night.stages_status != "SUCCEEDED":
        return None, "stages_pending" if not night.processed or night.stages_status in ("", "STAGES_STATE_UNSPECIFIED") else "stages_unavailable"
    if night.nap:
        return None, "nap_excluded"
    minutes = {s: 0.0 for s in STAGES}
    cursor = night.start_utc
    for segment in sorted(night.segments, key=lambda s: s.start_utc):
        if (segment.stage not in STAGES or segment.start_utc != cursor
                or segment.end_utc <= segment.start_utc or segment.end_utc > night.end_utc):
            logging.warning("Skipping invalid stage partition")
            return None, "invalid_stage_partition"
        minutes[segment.stage] += (segment.end_utc - segment.start_utc).total_seconds() / 60
        cursor = segment.end_utc
    if cursor != night.end_utc or not night.segments:
        logging.warning("Skipping incomplete stage partition")
        return None, "invalid_stage_partition"
    asleep = sum(minutes[s] for s in ("light", "deep", "rem"))
    if asleep < config.min_sleep_hours * 60:
        return None, "short_sleep_excluded"
    total = sum(minutes.values()) if config.denominator == "time_in_bed" else asleep
    minutes["restorative"] = minutes["deep"] + minutes["rem"]
    pct = {s: (None if s == "awake" and config.denominator == "time_asleep"
               else 100 * minutes[s] / total) for s in METRICS}
    if config.denominator == "time_in_bed" and abs(sum(pct[s] for s in STAGES) - 100) > 0.5:
        logging.warning("Skipping invalid stage percentages")
        return None, "invalid_stage_percentages"
    return NightStageStats(night.sleep_id, night.night_date, night.start_utc, night.end_utc,
                           total, minutes, pct, config.denominator), "ok"


def personal_ranges(current: NightStageStats, history: list[NightStageStats],
                    config: StageRangeConfig = DEFAULT_CONFIG) -> tuple[dict, list[NightStageStats]]:
    # Unique local wake dates; selection of main sleeps happens before this layer.
    by_date = {}
    for night in sorted(history, key=lambda n: (n.night_date, n.end_utc, n.sleep_id)):
        if night.night_date < current.night_date and night.sleep_id != current.sleep_id:
            if night.denominator != config.denominator:
                raise ValueError("Baseline denominator differs from current config")
            by_date[night.night_date] = night
    baseline = [by_date[day] for day in sorted(by_date)][-config.window_nights:]
    if len(baseline) < config.min_nights:
        return {}, baseline
    ranges = {}
    for stage in METRICS:
        if current.pct[stage] is None:
            continue
        values = [n.pct[stage] for n in baseline]
        med = median(values)
        spread = max(config.spread_scale * median(abs(v - med) for v in values), config.spread_floor_pct)
        center = 100 * sum(n.minutes[stage] for n in baseline) / sum(n.total_minutes for n in baseline)
        ranges[stage] = {"low": max(0, center - spread), "high": min(100, center + spread),
                         "center": center, "spread": spread, "n": len(baseline)}
    return ranges, baseline


def score_stages(current: NightStageStats, history: list[NightStageStats],
                 config: StageRangeConfig = DEFAULT_CONFIG) -> dict:
    if current.denominator != config.denominator:
        raise ValueError("Current denominator differs from config")
    ranges, baseline = personal_ranges(current, history, config)
    stages = {}
    for stage in METRICS:
        pct, band = current.pct[stage], ranges.get(stage)
        stages[stage] = {
            "minutes": current.minutes[stage], "pct": pct, "range": band,
            "range_minutes": {k: band[k] * current.total_minutes / 100 for k in ("low", "high")} if band else None,
            "status": ("below" if pct < band["low"] else "above" if pct > band["high"] else "within") if band else None,
            "delta_vs_center_pct": pct - band["center"] if band else None,
            "source": "personal" if band else None,
        }
    return {
        "sleep_id": current.sleep_id, "night_date": current.night_date.isoformat(),
        "algo_version": ALGO_VERSION, "denominator": config.denominator,
        "total_minutes": current.total_minutes, "stages": stages,
        "status": "ok" if ranges else "building_baseline",
        # Even a complete seven-night window has uncertain spread; 'ok' means complete, not validated.
        "reliability": "ok" if len(baseline) == config.window_nights else "low",
        "range_is_provisional": True, "nights_used": len(baseline), "nights_available": len(baseline),
        "baseline_sleep_ids": [n.sleep_id for n in baseline], "config_snapshot": asdict(config),
    }


def stats_to_dict(stats: NightStageStats) -> dict:
    result = asdict(stats)
    for key in ("night_date", "start_utc", "end_utc"):
        result[key] = result[key].isoformat()
    return result


def stats_from_dict(value: dict) -> NightStageStats:
    return NightStageStats(**{**value, "night_date": date.fromisoformat(value["night_date"]),
                             "start_utc": instant(value["start_utc"]), "end_utc": instant(value["end_utc"])})
