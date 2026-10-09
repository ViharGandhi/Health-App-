"""Representative sleep: explicit main, UTC elapsed time, greatest stable ID.

Naps/secondary sessions and calculator-specific ineligibility are excluded by
callers. Wake dates retain provider civil offsets. This is not strain's
wake-to-next-sleep activity-day boundary rule.
"""
from datetime import timezone


def main_sleep_key(main, start, end, sleep_id):
    if main is False or start.tzinfo is None or end.tzinfo is None:
        return None
    duration = (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
    return (main is True, duration, str(sleep_id)) if duration > 0 else None
