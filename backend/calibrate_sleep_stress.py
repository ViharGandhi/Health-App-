"""Compare candidate K thresholds on labeled, date-seeded demonstration nights."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date

from mock_sleep_stress import prepared_mock_nights
from sleep_stress import DEFAULT_CONFIG, score_night


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nights", type=int, default=14)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    if not 1 <= args.nights <= 31:
        parser.error("--nights must be between 1 and 31")
    prepared = prepared_mock_nights(args.end_date, args.nights)
    thresholds = (0.5, 0.75, 1.0, 1.25, 1.5)
    print("MOCK DATA ONLY — percentages are illustrative, not calibrated")
    print("date       " + "  ".join(f"K={value:g}" for value in thresholds))
    for current in prepared[-args.nights:]:
        values = []
        for threshold in thresholds:
            config = replace(DEFAULT_CONFIG, k_hrv=threshold, k_hr=threshold)
            result = score_night(current, prepared, config)
            values.append("—" if result["stress_pct"] is None else f'{result["stress_pct"]:.1f}%')
        print(f"{current.night.night_date}  " + "  ".join(f"{value:>6}" for value in values))


if __name__ == "__main__":
    main()
