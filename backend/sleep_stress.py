"""Sleep-only HRV/heart-rate stress detection on UTC, per-window observations."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from math import exp, isfinite, log
from statistics import median
from validity import valid_metric
from sleep_selection import main_sleep_key
from provider_payload import payload_boundary


@dataclass(frozen=True)
class StressConfig:
    baseline_nights_target: int = 14
    baseline_nights_min: int = 7
    baseline_min_windows_per_stage: int = 30
    k_hrv: float = 1.0
    k_hr: float = 1.0
    min_consecutive_windows: int = 2
    hr_valid_min: float = 35
    hr_valid_max: float = 130
    hr_min_coverage: float = 0.6
    min_night_coverage: float = 0.5
    spread_scale: float = 1.4826
    ln_hrv_spread_floor: float = 0.02
    hr_spread_floor: float = 0.5
    min_sleep_hours: float = 3.0


DEFAULT_CONFIG = StressConfig()
ALGO_VERSION = "sleep-stress-9"


@dataclass(frozen=True)
class StageSegment:
    start_utc: datetime
    end_utc: datetime
    stage: str


@dataclass(frozen=True)
class HrvWindow:
    start_utc: datetime
    end_utc: datetime
    rmssd_ms: float | None


@dataclass(frozen=True)
class HrSample:
    time_utc: datetime
    bpm: float


@dataclass(frozen=True)
class SleepNight:
    sleep_id: str
    night_date: date
    start_utc: datetime
    end_utc: datetime
    type: str
    stages: tuple[StageSegment, ...]
    awakenings: tuple[tuple[datetime, datetime], ...] = ()
    processed: bool = True
    main_sleep: bool = True
    nap: bool = False
    main_sleep_explicit: bool = True


@dataclass(frozen=True)
class ValidWindow:
    start_utc: datetime
    end_utc: datetime
    stage: str
    ln_hrv: float
    hr: float
    minutes: float


@dataclass(frozen=True)
class NightWindows:
    night: SleepNight
    windows: tuple[ValidWindow, ...]
    asleep_minutes: float
    coverage: float
    withheld_reason: str | None = None


@dataclass(frozen=True)
class StageBaseline:
    ln_hrv_median: float
    ln_hrv_spread: float
    hr_median: float
    hr_spread: float
    window_count: int
    fallback: bool = False


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Physical timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _overlap(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> float:
    return max(0.0, (min(end, other_end) - max(start, other_start)).total_seconds())


@payload_boundary
def adapt_google_sleep(point: dict) -> SleepNight:
    """Adapt the documented v4 sleep DataPoint; reject incomplete processing later."""
    sleep = point["sleep"]
    interval = sleep["interval"]
    end = _instant(interval["endTime"])
    offset_seconds = float(interval.get("endUtcOffset", "0s").removesuffix("s"))
    night_date = (end + timedelta(seconds=offset_seconds)).date()
    stages = tuple(StageSegment(_instant(item["startTime"]), _instant(item["endTime"]), item["type"])
                   for item in sleep.get("stages", []))
    awakenings = tuple((_instant(item["startTime"]), _instant(item["endTime"]))
                       for item in sleep.get("shortAwakenings", []) + sleep.get("outOfBedSegments", []))
    metadata = sleep.get("metadata", {})
    sleep_type = sleep.get("type", "SLEEP_TYPE_UNSPECIFIED")
    processed = metadata.get("processed") is True and (
        sleep_type == "CLASSIC" or metadata.get("stagesStatus") == "SUCCEEDED"
    )
    return SleepNight(
        sleep_id=point.get("name") or metadata.get("externalId") or f"sleep-{end.isoformat()}",
        night_date=night_date,
        start_utc=_instant(interval["startTime"]), end_utc=end,
        type=sleep_type, stages=stages, awakenings=awakenings,
        processed=processed, main_sleep=metadata.get("mainSleep") is not False,
        nap=metadata.get("nap") is True,
        main_sleep_explicit=metadata.get("mainSleep") is True,
    )


@payload_boundary
def adapt_google_hr(point: dict) -> HrSample:
    metric = point["heartRate"]
    return HrSample(_instant(metric["sampleTime"]["physicalTime"]), float(metric["beatsPerMinute"]))


@payload_boundary
def adapt_google_hrv(points: list[dict], anchor: str) -> list[HrvWindow]:
    """Infer cadence from adjacent samples; anchor must be verified on a real device.

    v4 documents `sampleTime.physicalTime` and RMSSD in milliseconds, but no
    window duration or whether the timestamp marks its start or end. `anchor`
    is therefore explicit. Gaps over 1.5 times the typical cadence remain gaps.
    """
    if anchor not in ("start", "end"):
        raise ValueError("HRV sample-time anchor must be 'start' or 'end'")
    samples = sorted((
        (_instant(item["heartRateVariability"]["sampleTime"]["physicalTime"]),
         item["heartRateVariability"].get("rootMeanSquareOfSuccessiveDifferencesMilliseconds"))
        for item in points
        if "heartRateVariability" in item and item["heartRateVariability"].get("sampleTime", {}).get("physicalTime")
    ), key=lambda item: item[0])
    deltas = [(following[0] - previous[0]).total_seconds()
              for previous, following in zip(samples, samples[1:])
              if 0 < (following[0] - previous[0]).total_seconds() <= 3600]
    if not deltas:
        return []
    cadence = median(deltas)
    windows = []
    for index, (stamp, value) in enumerate(samples):
        neighbor = samples[index + 1][0] if anchor == "start" and index + 1 < len(samples) else (
            samples[index - 1][0] if anchor == "end" and index else None
        )
        duration = abs((neighbor - stamp).total_seconds()) if neighbor else cadence
        if duration <= 0 or duration > cadence * 1.5:
            continue
        start = stamp if anchor == "start" else stamp - timedelta(seconds=duration)
        windows.append(HrvWindow(start, start + timedelta(seconds=duration),
                                 float(value) if value is not None else None))
    return windows


def _merged_minutes(intervals: list[tuple[datetime, datetime]]) -> float:
    if not intervals:
        return 0.0
    intervals.sort()
    total = 0.0
    start, end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += (end - start).total_seconds()
            start, end = next_start, next_end
    return (total + (end - start).total_seconds()) / 60


def asleep_minutes(night: SleepNight) -> float:
    asleep_stages = [segment for segment in night.stages if segment.stage in ("LIGHT", "REM", "DEEP", "ASLEEP")]
    asleep = sum((segment.end_utc - segment.start_utc).total_seconds() for segment in asleep_stages) / 60
    interruptions = [(max(segment.start_utc, start), min(segment.end_utc, end))
                     for segment in asleep_stages for start, end in night.awakenings
                     if _overlap(segment.start_utc, segment.end_utc, start, end) > 0]
    return max(0.0, asleep - _merged_minutes(interruptions))


def infer_hr_interval_seconds(samples: list[HrSample]) -> float | None:
    ordered = sorted(sample.time_utc for sample in samples)
    deltas = sorted((later - earlier).total_seconds() for earlier, later in zip(ordered, ordered[1:])
                    if 0 < (later - earlier).total_seconds() <= 60)
    # Fitbit's reconciled stream varies between one and several seconds. A
    # short burst must not make every other window fail the coverage check.
    return median(deltas) if deltas else None


def prepare_night(
    night: SleepNight, hrv_windows: list[HrvWindow], hr_samples: list[HrSample],
    config: StressConfig = DEFAULT_CONFIG,
) -> NightWindows:
    duration = (night.end_utc - night.start_utc).total_seconds()
    cursor = night.start_utc
    allowed = ('ASLEEP', 'AWAKE', 'RESTLESS') if night.type == 'CLASSIC' else ('LIGHT', 'REM', 'DEEP', 'AWAKE')
    for segment in sorted(night.stages, key=lambda item: item.start_utc):
        if (segment.start_utc != cursor or segment.end_utc <= segment.start_utc
                or segment.end_utc > night.end_utc or segment.stage not in allowed):
            return NightWindows(night, (), 0.0, 0.0, 'invalid_stage_partition')
        cursor = segment.end_utc
    if not 0 < duration <= 86400 or cursor != night.end_utc:
        return NightWindows(night, (), 0.0, 0.0, 'invalid_stage_partition')
    asleep = asleep_minutes(night)
    if (night.nap or not night.processed or
            (night.end_utc - night.start_utc).total_seconds() < config.min_sleep_hours * 3600):
        return NightWindows(night, (), asleep, 0.0)
    ordered_hr = sorted(hr_samples, key=lambda item: item.time_utc)
    times = [sample.time_utc for sample in ordered_hr]
    interval = infer_hr_interval_seconds(ordered_hr)
    valid = []
    for window in sorted(hrv_windows, key=lambda item: item.start_utc):
        duration = (window.end_utc - window.start_utc).total_seconds()
        if (duration <= 0 or interval is None or window.start_utc < night.start_utc
                or window.end_utc > night.end_utc or window.rmssd_ms is None
                or not valid_metric('sample_hrv', window.rmssd_ms)
                or (valid and window.start_utc < valid[-1].end_utc)):
            continue
        if any(_overlap(window.start_utc, window.end_utc, start, end) > 0
               for start, end in night.awakenings):
            continue
        overlaps = [(segment.stage, _overlap(window.start_utc, window.end_utc,
                                             segment.start_utc, segment.end_utc))
                    for segment in night.stages]
        stage, covered = max(overlaps, key=lambda item: item[1], default=("AWAKE", 0))
        if covered / duration < 0.7 or stage not in ("LIGHT", "REM", "DEEP", "ASLEEP"):
            continue
        first = bisect_left(times, window.start_utc)
        last = bisect_left(times, window.end_utc)
        heart_rates = [sample.bpm for sample in ordered_hr[first:last]
                       if config.hr_valid_min <= sample.bpm <= config.hr_valid_max]
        if len(heart_rates) < config.hr_min_coverage * duration / interval:
            continue
        valid.append(ValidWindow(window.start_utc, window.end_utc, stage,
                                 log(window.rmssd_ms), median(heart_rates), duration / 60))
    covered = sum(window.minutes for window in valid)
    return NightWindows(night, tuple(valid), asleep, min(1.0, covered / asleep) if asleep else 0.0)


def _stage_baseline(windows: list[ValidWindow], config: StressConfig, fallback: bool) -> StageBaseline:
    ln_median = median(window.ln_hrv for window in windows)
    hr_median = median(window.hr for window in windows)
    ln_spread = config.spread_scale * median(abs(window.ln_hrv - ln_median) for window in windows)
    hr_spread = config.spread_scale * median(abs(window.hr - hr_median) for window in windows)
    return StageBaseline(ln_median, max(config.ln_hrv_spread_floor, ln_spread),
                         hr_median, max(config.hr_spread_floor, hr_spread), len(windows), fallback)


def build_baseline(current: NightWindows, history: list[NightWindows],
                   config: StressConfig = DEFAULT_CONFIG) -> tuple[dict[str, StageBaseline], int, bool]:
    first_date = current.night.night_date - timedelta(days=config.baseline_nights_target)
    # Match stage-store/main-sleep selection: longest main session, then ID.
    by_id = {}
    for item in sorted(history, key=lambda n: (n.night.end_utc, n.night.sleep_id)):
        if (first_date <= item.night.night_date < current.night.night_date
                and item.night.sleep_id != current.night.sleep_id
                and item.night.main_sleep and not item.night.nap
                and item.coverage >= config.min_night_coverage and item.windows):
            by_id[item.night.sleep_id] = item
    by_date = {}
    for item in by_id.values():
        day = item.night.night_date
        previous_item = by_date.get(day)
        key = lambda n: main_sleep_key(True if n.night.main_sleep_explicit else None,
            n.night.start_utc, n.night.end_utc, n.night.sleep_id)
        if previous_item is None or key(item) > key(previous_item):
            by_date[day] = item
    previous = [by_date[day] for day in sorted(by_date, reverse=True)][:config.baseline_nights_target]
    if len(previous) < config.baseline_nights_min:
        return {}, len(previous), False
    pooled = [window for item in previous for window in item.windows]
    stage_names = ("ASLEEP",) if current.night.type == "CLASSIC" else ("LIGHT", "REM", "DEEP")
    stages = {}
    fallback_used = False
    for stage in stage_names:
        stage_windows = [window for window in pooled if window.stage == stage]
        fallback = len(stage_windows) < config.baseline_min_windows_per_stage
        stages[stage] = (_stage_baseline(stage_windows, config, False) if not fallback
                         else _stage_baseline(pooled, config, True))
        fallback_used |= fallback
    return stages, len(previous), fallback_used


def score_night(current: NightWindows, history: list[NightWindows],
                config: StressConfig = DEFAULT_CONFIG, computed_at: datetime | None = None) -> dict:
    night = current.night
    valid_minutes = sum(window.minutes for window in current.windows)
    result = {
        "sleep_id": night.sleep_id, "night_date": night.night_date.isoformat(),
        'main_sleep_explicit': night.main_sleep_explicit,
        'physical_duration_minutes': (night.end_utc - night.start_utc).total_seconds() / 60,
        "main_sleep": night.main_sleep,
        "computed_at": (computed_at or datetime.now(timezone.utc)).isoformat(),
        "algo_version": ALGO_VERSION, "stressed_minutes": None, "stressed_hours": None,
        "stress_pct": None, "valid_minutes": round(valid_minutes, 2),
        "asleep_minutes": round(current.asleep_minutes, 2), "coverage": round(current.coverage, 3),
        "confidence": "low", "status": "ok", "nights_available": 0,
        "withheld_reason": None, "anchor_verification": "synthetic_or_caller_asserted",
        "baseline": {"nights_used": 0, "fallback_used": False, "per_stage": {}},
        "peak_level": None, "mean_level": None, "hrv_only_minutes": None,
        "episodes": [], "type_fallback": night.type == "CLASSIC",
        "config_snapshot": asdict(config),
    }
    if current.withheld_reason:
        result['status'] = current.withheld_reason
        result['withheld_reason'] = current.withheld_reason
        return result
    if night.nap or (night.end_utc - night.start_utc).total_seconds() < config.min_sleep_hours * 3600:
        result["status"] = "short_sleep"
        result['withheld_reason'] = result['status']
        return result
    if not night.processed:
        result["status"] = "pending_processing"
        result['withheld_reason'] = result['status']
        return result
    baselines, nights_used, fallback_used = build_baseline(current, history, config)
    result["nights_available"] = nights_used
    result["baseline"] = {"nights_used": nights_used, "fallback_used": fallback_used,
                          "per_stage": {stage: asdict(value) for stage, value in baselines.items()}}
    if not baselines:
        result["status"] = "insufficient_baseline"
        result['withheld_reason'] = result['status']
        return result
    if not current.windows:
        result["status"] = "no_valid_windows"
        result['withheld_reason'] = result['status']
        return result
    result["confidence"] = ("high" if current.coverage >= 0.75 and not fallback_used
                            and night.type != "CLASSIC" else
                            "medium" if current.coverage >= config.min_night_coverage else "low")
    scored = []
    hrv_only = 0.0
    for window in current.windows:
        baseline = baselines[window.stage if night.type != "CLASSIC" else "ASLEEP"]
        z_hrv = (baseline.ln_hrv_median - window.ln_hrv) / baseline.ln_hrv_spread
        z_hr = (window.hr - baseline.hr_median) / baseline.hr_spread
        level = max(0.0, min(z_hrv, z_hr))
        candidate = z_hrv >= config.k_hrv and z_hr >= config.k_hr
        if z_hrv >= config.k_hrv and z_hr < config.k_hr:
            hrv_only += window.minutes
        scored.append((window, baseline, level, candidate))
    runs = []
    run = []
    for item in scored:
        if item[3]:
            if run and item[0].start_utc != run[-1][0].end_utc:
                if len(run) >= config.min_consecutive_windows:
                    runs.append(run)
                run = []
            run.append(item)
        elif run:
            if len(run) >= config.min_consecutive_windows:
                runs.append(run)
            run = []
    if len(run) >= config.min_consecutive_windows:
        runs.append(run)
    episodes = []
    stressed = [item for run in runs for item in run]
    for run in runs:
        minutes = sum(item[0].minutes for item in run)
        stages = {stage: sum(item[0].minutes for item in run if item[0].stage == stage)
                  for stage in {item[0].stage for item in run}}
        episodes.append({
            "start": run[0][0].start_utc.isoformat(), "end": run[-1][0].end_utc.isoformat(),
            "minutes": round(minutes, 2), "dominant_stage": max(stages, key=stages.get),
            "mean_hr_delta_bpm": round(sum((item[0].hr - item[1].hr_median) * item[0].minutes
                                            for item in run) / minutes, 2),
            "mean_hrv_drop_pct": round(sum((1 - exp(item[0].ln_hrv - item[1].ln_hrv_median))
                                            * 100 * item[0].minutes for item in run) / minutes, 2),
            "peak_level": round(max(item[2] for item in run), 2),
        })
    stressed_minutes = sum(item[0].minutes for item in stressed)
    result.update({
        "stressed_minutes": round(stressed_minutes, 2),
        "stressed_hours": round(stressed_minutes / 60, 3),
        "stress_pct": round(100 * stressed_minutes / valid_minutes, 2),
        "peak_level": round(max((item[2] for item in stressed), default=0.0), 2),
        "mean_level": round(sum(item[2] * item[0].minutes for item in stressed) / stressed_minutes, 2)
        if stressed_minutes else 0.0,
        "hrv_only_minutes": round(hrv_only, 2), "episodes": episodes,
    })
    return result


def summarize_nights(results: list[dict] | tuple[dict, ...]) -> list[dict]:
    """Report the main session and a time-weighted total for each wake date."""
    by_date: dict[str, list[dict]] = {}
    for item in results:
        by_date.setdefault(item["night_date"], []).append(item)
    totals = []
    for day, sessions in sorted(by_date.items()):
        candidates = [item for item in sessions if item['main_sleep']]
        main = max(candidates, key=lambda item: (item.get('main_sleep_explicit', True),
            item.get('physical_duration_minutes', 0), item['sleep_id']), default=None)
        scored = [item for item in sessions if item["stressed_minutes"] is not None]
        stressed = sum(item["stressed_minutes"] for item in scored)
        valid = sum(item["valid_minutes"] for item in scored)
        totals.append({"night_date": day, "main_sleep_id": main["sleep_id"] if main else None,
                       "sessions": len(sessions), "stressed_minutes": round(stressed, 2) if scored else None,
                       "valid_minutes": round(valid, 2),
                       "stress_pct": round(100 * stressed / valid, 2) if valid else None})
    return totals
