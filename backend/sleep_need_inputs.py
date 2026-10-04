"""Join existing daily sleep, nap and strain readings without imputing missing nights."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

from sleep_need import SleepNeedNight, SleepNeedResult, calculate_sleep_need


def need_components(result: SleepNeedResult) -> dict:
    return {"baseline": result.baseline_min, "strain": result.strain_add_min,
            "debt": result.debt_add_min, "nap_credit": result.nap_credit_min}


@dataclass(frozen=True)
class SleepNeedInputs:
    sleep_minutes: Mapping[date, float | None]
    strain_percentages: Mapping[date, float | None]
    nap_minutes: Mapping[date, float]

    def for_tonight(self, day: date, baseline_need_min: float | None = None) -> SleepNeedResult | None:
        strain = self.strain_percentages.get(day)
        if strain is None:
            return None
        # A sleep ending on D follows the activity on D-1. Tonight's estimate can
        # use this morning's sleep; a historical pre-sleep estimate cannot use it.
        history = [SleepNeedNight(self.sleep_minutes.get(day - timedelta(days=i)),
                                 self.strain_percentages.get(day - timedelta(days=i + 1)))
                   for i in range(7)]
        return calculate_sleep_need(strain, history, self.nap_minutes.get(day, 0.0), baseline_need_min)
