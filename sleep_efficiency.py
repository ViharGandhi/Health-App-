"""Sleep efficiency: sleep time divided by the observed sleep period."""

from __future__ import annotations

import math
from typing import Optional


class SleepEfficiencyCalculator:
    @staticmethod
    def calculate_single_night(
        time_asleep_seconds: float,
        time_in_bed_seconds: float,
    ) -> Optional[float]:
        """Return None when the device did not provide a valid denominator."""
        if not all(math.isfinite(value) for value in (time_asleep_seconds, time_in_bed_seconds)):
            return None
        if not 0 < time_asleep_seconds <= time_in_bed_seconds <= 24 * 3600:
            return None
        return round(100 * time_asleep_seconds / time_in_bed_seconds, 1)
