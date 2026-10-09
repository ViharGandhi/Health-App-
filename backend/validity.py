"""Shared existing numeric/unit gates; these are not clinical reference ranges."""
from math import isfinite


def positive(value) -> bool:
    return type(value) in (int, float) and isfinite(value) and value > 0


def resting_hr(value, age=None, *, parse_strings=False, low=30, high=230) -> float | None:
    if parse_strings and isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not positive(value) or not low <= value <= high:
        return None
    if age is not None and value >= 208 - .7 * age:
        return None
    return value


def valid_metric(metric: str, value, age=None) -> bool:
    if metric == 'rhr':
        return resting_hr(value, age) is not None
    if metric == 'nrem_hr':
        return resting_hr(value) is not None
    if not positive(value):
        return False
    return value <= 100 if metric == 'spo2' else True


def sleep_duration(value, *, unit='seconds') -> bool:
    """Zero is measured absence; durations are bounded by one calendar day."""
    limit = {'seconds': 86400, 'minutes': 1440, 'hours': 24}[unit]
    return type(value) in (int, float) and isfinite(value) and 0 <= value <= limit
