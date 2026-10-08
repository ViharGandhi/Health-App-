"""Pure baseline-relative Recovery estimate for connected daily Fitbit summaries."""

from dataclasses import dataclass
from datetime import date, timedelta
from math import erf, isfinite, log, sqrt
from statistics import mean, median
from typing import Sequence


BASELINE_DAYS = 60
EXCLUDE_RECENT_DAYS = 7
RECENT_WINDOW = 7
MIN_BASELINE_DAYS = 21
MIN_RECENT_NIGHTS = 4
W_RECENT = 0.7
W_TODAY = 0.3
W_HRV = 0.6
W_RHR = 0.4
HRV_SIGMA_FLOOR = 0.05
RHR_SD_FLOOR = 1.0
Z_CLIP = 3.0
SLEEP_OK_THRESHOLD = 0.85
SLEEP_RANGE = 0.25
SLEEP_MAX_PENALTY = 0.5
ZONE_BAND = 0.5
MIN_SLEEP_MIN = 180
ILLNESS_Z_CAP = -0.5
ILLNESS_SD_MULTIPLIER = 2.0
CONFIDENCE_HIGH_BASELINE = 45
CONFIDENCE_MED_BASELINE = 28


def positive(value: float | None) -> bool:
    return value is not None and isfinite(value) and value > 0


def robust(values: Sequence[float], sd_floor: float) -> tuple[float, float]:
    center = median(values)
    return center, max(1.4826 * median(abs(value - center) for value in values), sd_floor)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class RecoveryEstimate:
    status: str
    z: float | None
    percent: int | None
    zone: str | None
    confidence: str | None
    components: dict[str, float | None]
    sleep_context: dict[str, float | None]
    baseline_days: int
    recent_nights: int
    rhr_baseline_days: int
    illness_flag: bool
    estimated: bool = True


def calculate_recovery(
    baseline_hrv: Sequence[float], recent_hrv: Sequence[float],
    today_hrv: float | None = None, baseline_rhr: Sequence[float] = (),
    today_rhr: float | None = None, sleep_min: float | None = None,
    need_min: float | None = None, illness_flag: bool = False,
) -> RecoveryEstimate:
    baseline = [log(value) for value in baseline_hrv if positive(value)]
    recent = [log(value) for value in recent_hrv if positive(value)]
    rhr = [value for value in baseline_rhr if positive(value)]
    sleep_min = sleep_min if positive(sleep_min) and sleep_min >= MIN_SLEEP_MIN else None
    need_min = need_min if positive(need_min) else None
    performance = min(sleep_min / need_min, 1.0) if sleep_min is not None and need_min is not None else None
    context = {"sleep_min": sleep_min, "need_min": need_min, "performance": performance}
    sleep_adj = (-SLEEP_MAX_PENALTY * clamp((SLEEP_OK_THRESHOLD - performance) / SLEEP_RANGE, 0, 1)
                 if performance is not None else 0.0)
    counts = dict(baseline_days=len(baseline), recent_nights=len(recent),
                  rhr_baseline_days=len(rhr), illness_flag=illness_flag)
    if len(baseline) < MIN_BASELINE_DAYS or len(recent) < MIN_RECENT_NIGHTS:
        return RecoveryEstimate("building_reference", None, None, None, None,
                                {"z_hrv": None, "z_rhr": None, "sleep_adj": sleep_adj}, context, **counts)

    mu, sigma = robust(baseline, HRV_SIGMA_FLOOR)
    recent_mean = mean(recent)
    signal = W_RECENT * recent_mean + W_TODAY * log(today_hrv) if positive(today_hrv) else recent_mean
    z_hrv = (signal - mu) / sigma
    z_rhr = None
    if positive(today_rhr) and len(rhr) >= MIN_BASELINE_DAYS:
        rmed, rsd = robust(rhr, RHR_SD_FLOOR)
        z_rhr = -(today_rhr - rmed) / rsd
    z_base = W_HRV * z_hrv + W_RHR * z_rhr if z_rhr is not None else z_hrv
    z = clamp(z_base + sleep_adj, -Z_CLIP, Z_CLIP)
    if illness_flag:
        z = min(z, ILLNESS_Z_CAP)
    zone = "below_normal" if z < -ZONE_BAND else "above_normal" if z > ZONE_BAND else "normal"
    if len(baseline) >= CONFIDENCE_HIGH_BASELINE and len(recent) >= 6 and z_rhr is not None and performance is not None:
        confidence = "high"
    elif len(baseline) >= CONFIDENCE_MED_BASELINE and len(recent) >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    percent = round(100 * 0.5 * (1 + erf(z / sqrt(2)))) if confidence != "low" else None
    # Classify and rescale before rounding; rounded z must not move a zone boundary.
    return RecoveryEstimate("ok", round(z, 2), percent, zone, confidence,
                            {"z_hrv": z_hrv, "z_rhr": z_rhr, "sleep_adj": sleep_adj}, context, **counts)


def baseline_bounds(day: date) -> tuple[date, date]:
    end = day - timedelta(days=EXCLUDE_RECENT_DAYS + 1)
    return end - timedelta(days=BASELINE_DAYS - 1), end


def recovery_from_history(history: dict[str, list[dict]], day: date,
                          sleep_min: float | None = None, need_min: float | None = None) -> RecoveryEstimate:
    """Join reconciled local-date daily records without imputing or counting dates twice.

    The 180-minute exclusion applies to the supplied sleep modifier; daily RMSSD
    summaries have no duration/coverage field, so no historical coverage is inferred.
    Recent HRV uses the seven prior dates; today appears only in its 30% term.
    """
    start, end = baseline_bounds(day)
    recent_start = day - timedelta(days=RECENT_WINDOW)
    points = {key: {date.fromisoformat(point["date"]): point for point in values}
              for key, values in history.items()}
    hrv = points.get("hrv", {})
    rhr = points.get("rhr", {})
    today_hrv = hrv.get(day, {}).get("value")
    today_rhr = rhr.get(day, {}).get("value")
    method = rhr.get(day, {}).get("method")
    # Unreported/unspecified methods cannot establish that readings are comparable.
    known_method = method in ("WITH_SLEEP", "ONLY_WITH_AWAKE_DATA")
    baseline_rhr = [point["value"] for when, point in rhr.items()
                    if start <= when <= end and known_method and point.get("method") == method]
    illness_flag = False
    for metric in ("respiratory_rate", "skin_temperature"):
        readings = points.get(metric, {})
        current = readings.get(day, {}).get("value")
        reference = [point["value"] for when, point in readings.items()
                     if start <= when <= end and positive(point.get("value"))]
        if positive(current) and len(reference) >= MIN_BASELINE_DAYS:
            center, spread = robust(reference, 0.0)
            # Flat or insufficient references remain unassessed, as requested.
            illness_flag |= spread > 0 and abs(current - center) > ILLNESS_SD_MULTIPLIER * spread
    return calculate_recovery(
        [point["value"] for when, point in hrv.items() if start <= when <= end],
        [point["value"] for when, point in hrv.items() if recent_start <= when < day],
        today_hrv, baseline_rhr, today_rhr if known_method else None,
        sleep_min, need_min, illness_flag,
    )
