"""Pure, user-specified sleep-need estimate. All calculations use float minutes."""

from dataclasses import dataclass
import math
from typing import Sequence


BASELINE_NEED_MIN = 450.0
STRAIN_MAX_MIN = 26.0
STRAIN_X0 = 14.38
STRAIN_K = 0.476
STRAIN_CUTOFF_MIN = 1.0
DEBT_WEIGHTS = (1.0, 0.85, 0.7, 0.55, 0.4, 0.25, 0.1)
DEBT_REPAY_FRACTION = 0.34
DEBT_CAP_MIN = 240.0
TOTAL_NEED_MIN_LIMIT = 360.0
TOTAL_NEED_MAX_LIMIT = 660.0


@dataclass(frozen=True)
class SleepNeedNight:
    actual_sleep_min: float | None
    strain_pct: float | None


@dataclass(frozen=True)
class SleepNeedResult:
    baseline_min: float
    strain_add_min: float
    debt_add_min: float
    nap_credit_min: float
    total_need_min: float
    sleep_debt_min: float


def strain_sleep_add(strain_21: float) -> float:
    if not math.isfinite(strain_21):
        raise ValueError("Strain must be finite")
    strain = max(0.0, min(21.0, strain_21))
    def logistic(value):
        return 1.0 / (1.0 + math.exp(-STRAIN_K * (value - STRAIN_X0)))
    minutes = STRAIN_MAX_MIN * (logistic(strain) - logistic(0)) / (logistic(21) - logistic(0))
    return 0.0 if minutes < STRAIN_CUTOFF_MIN else minutes


def sleep_debt(history: Sequence[SleepNeedNight | None], baseline_need_min: float | None = None) -> float:
    baseline = BASELINE_NEED_MIN if baseline_need_min is None else float(baseline_need_min)
    if not math.isfinite(baseline) or baseline <= 0:
        raise ValueError("Baseline must be positive and finite")
    weighted_balance = weight_sum = 0.0
    for weight, night in zip(DEBT_WEIGHTS, history):
        if night is None or night.actual_sleep_min is None or night.strain_pct is None:
            continue
        if not math.isfinite(night.actual_sleep_min) or night.actual_sleep_min < 0:
            raise ValueError("Actual sleep must be nonnegative and finite")
        need = baseline + strain_sleep_add(night.strain_pct * 0.21)
        weighted_balance += weight * (night.actual_sleep_min - need)
        weight_sum += weight
    return max(0.0, min(DEBT_CAP_MIN, -weighted_balance / weight_sum)) if weight_sum else 0.0


def calculate_sleep_need(
    strain_pct: float, history: Sequence[SleepNeedNight | None] = (),
    nap_min_today: float = 0.0, baseline_need_min: float | None = None,
) -> SleepNeedResult:
    baseline = BASELINE_NEED_MIN if baseline_need_min is None else float(baseline_need_min)
    if not math.isfinite(nap_min_today) or nap_min_today < 0:
        raise ValueError("Nap minutes must be nonnegative and finite")
    debt = sleep_debt(history, baseline)
    strain_add = strain_sleep_add(strain_pct * 0.21)
    debt_add = debt * DEBT_REPAY_FRACTION
    total = max(TOTAL_NEED_MIN_LIMIT, min(TOTAL_NEED_MAX_LIMIT, baseline + strain_add + debt_add - nap_min_today))
    return SleepNeedResult(baseline, strain_add, debt_add, float(nap_min_today), total, debt)


def format_sleep_minutes(minutes: float) -> str:
    """Round only here; carry a rounded 60 minutes into the next hour."""
    if not math.isfinite(minutes) or minutes < 0:
        raise ValueError("Minutes must be nonnegative and finite")
    rounded = math.floor(minutes + 0.5)
    hours, remainder = divmod(rounded, 60)
    return f"{hours}h {remainder}m"
