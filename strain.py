"""
strain.py
=========
Python port of:
  - Soma/Calculators/StrainCalculator.swift
  - Soma/Models/HeartRateZone.swift

How Strain Is Measured (see docstrings and explanation below).
"""

from datetime import datetime, timedelta
from enum import IntEnum
from typing import Optional, NamedTuple


# ──────────────────────────────────────────────────────────────────────────────
# Heart Rate Zones & Weights (Convex / TRIMP-inspired)
# ──────────────────────────────────────────────────────────────────────────────

class HeartRateZone(IntEnum):
    """
    Heart rate zones based on percentage of Max Heart Rate (% MaxHR).
    Weights are convex (TRIMP-inspired) rather than linear, reflecting the
    disproportionately higher cardiovascular and metabolic cost of high-intensity effort:
      - Zone 1 (50-60% MaxHR): weight 0.0 (active recovery, no strain)
      - Zone 2 (60-70% MaxHR): weight 0.8
      - Zone 3 (70-80% MaxHR): weight 1.7
      - Zone 4 (80-90% MaxHR): weight 2.9
      - Zone 5 (90-100% MaxHR): weight 4.6
    (Note: HR below 50% MaxHR is considered resting/passive physiology and skipped).
    """
    ZONE1 = 1  # 50–60% MaxHR
    ZONE2 = 2  # 60–70% MaxHR
    ZONE3 = 3  # 70–80% MaxHR
    ZONE4 = 4  # 80–90% MaxHR
    ZONE5 = 5  # 90–100% MaxHR

    @property
    def weight(self) -> float:
        weights = {
            HeartRateZone.ZONE1: 0.0,
            HeartRateZone.ZONE2: 0.8,
            HeartRateZone.ZONE3: 1.7,
            HeartRateZone.ZONE4: 2.9,
            HeartRateZone.ZONE5: 4.6,
        }
        return weights[self]

    @property
    def label(self) -> str:
        labels = {
            HeartRateZone.ZONE1: "Zone 1 (Warm Up / Recovery)",
            HeartRateZone.ZONE2: "Zone 2 (Fat Burn / Aerobic Base)",
            HeartRateZone.ZONE3: "Zone 3 (Aerobic / Tempo)",
            HeartRateZone.ZONE4: "Zone 4 (Anaerobic / Threshold)",
            HeartRateZone.ZONE5: "Zone 5 (Max / Neuromuscular)",
        }
        return labels[self]

    @staticmethod
    def zone_for(heart_rate: float, max_hr: float) -> "HeartRateZone":
        """Classify a heart rate into a zone using % MaxHR thresholds."""
        if max_hr <= 0:
            return HeartRateZone.ZONE1
        pct = heart_rate / max_hr
        if pct < 0.60:
            return HeartRateZone.ZONE1
        elif pct < 0.70:
            return HeartRateZone.ZONE2
        elif pct < 0.80:
            return HeartRateZone.ZONE3
        elif pct < 0.90:
            return HeartRateZone.ZONE4
        else:
            return HeartRateZone.ZONE5


# ──────────────────────────────────────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────────────────────────────────────

class WorkoutInterval(NamedTuple):
    start: datetime
    end: datetime
    activity_name: str


class WorkoutStrainDetail:
    def __init__(self, activity_name: str, strain: float, zone_minutes: dict[HeartRateZone, float]):
        self.activity_name = activity_name
        self.strain = strain
        self.zone_minutes = zone_minutes


class WorkoutStrainResult:
    def __init__(self, total: float, workout_strain: float, incidental_strain: float, details: list[WorkoutStrainDetail]):
        self.total = total
        self.workout_strain = workout_strain
        self.incidental_strain = incidental_strain
        self.details = details


# ──────────────────────────────────────────────────────────────────────────────
# Strain Calculator
# ──────────────────────────────────────────────────────────────────────────────

class StrainCalculator:
    """
    Computes StrainLoad (raw cardiovascular load units) and StrainScore (0-100)
    relative to rolling personal capacity.
    """

    # Estimated daily capacity during the initial 7-day calibration phase
    ESTIMATED_CALIBRATION_CAPACITY: float = 500.0

    # Minimum days of history required before leaving calibration
    CALIBRATION_DAYS: int = 7

    # Rolling window size for personalized daily capacity
    ROLLING_CAPACITY_DAYS: int = 14

    @staticmethod
    def estimated_max_hr(age: int) -> float:
        """
        Estimates max heart rate using Tanaka formula: 208 - 0.7 * age.
        Preferred over Haskell (220 - age) because it avoids overestimating max HR
        in young adults and underestimating it in older adults.
        """
        return 208.0 - 0.7 * float(age)

    @staticmethod
    def calculate(samples: list[tuple[datetime, float]], max_hr: float) -> tuple[float, dict[HeartRateZone, float]]:
        """
        Computes raw StrainLoad from timestamped HR samples: [(datetime, bpm), ...]
        
        Formula:
          StrainLoad = SUM(minutes_in_zone * zone_weight)

        Rules:
          1. Gap capping: Inter-sample duration is capped at 1.0 minute.
             Outside workouts, Apple Watch / health trackers record sporadically
             (every 5-10 min). Capping prevents gaps from being counted as continuous effort.
          2. Passive filter: Average HR < 50% max_hr is resting physiology and skipped.
          3. Zone 1 (50-60%) has weight 0.0 (active recovery, contributes 0 load).

        Returns:
          (total_strain_load, zone_minutes_dict)
        """
        zone_minutes: dict[HeartRateZone, float] = {z: 0.0 for z in HeartRateZone}
        if len(samples) < 2:
            return 0.0, zone_minutes

        for i in range(1, len(samples)):
            prev_time, prev_hr = samples[i - 1]
            curr_time, curr_hr = samples[i]

            raw_minutes = (curr_time - prev_time).total_seconds() / 60.0
            if raw_minutes <= 0:
                continue

            # Gap capping: cap to 1.0 minute
            minutes = min(raw_minutes, 1.0)
            avg_hr = (prev_hr + curr_hr) / 2.0

            # Passive HR filter: below 50% max_hr is resting, not strain
            if avg_hr < 0.50 * max_hr:
                continue

            zone = HeartRateZone.zone_for(avg_hr, max_hr)
            zone_minutes[zone] += minutes

        total_load = sum(zone_minutes[z] * z.weight for z in HeartRateZone)
        return total_load, zone_minutes

    @staticmethod
    def calculate_workout_aware(
        workout_intervals: list[WorkoutInterval],
        all_samples: list[tuple[datetime, float]],
        max_hr: float
    ) -> WorkoutStrainResult:
        """
        Partitions daily StrainLoad into workout vs incidental (non-workout) windows.
        Preserves timeline continuity by evaluating each consecutive sample pair and
        checking if its midpoint falls inside a workout interval.
        """
        if not all_samples:
            return WorkoutStrainResult(total=0.0, workout_strain=0.0, incidental_strain=0.0, details=[])

        if not workout_intervals:
            total_load, _ = StrainCalculator.calculate(all_samples, max_hr)
            return WorkoutStrainResult(total=total_load, workout_strain=0.0, incidental_strain=total_load, details=[])

        total_load = 0.0
        w_load = 0.0
        i_load = 0.0

        detail_loads: dict[int, float] = {}
        detail_zones: dict[int, dict[HeartRateZone, float]] = {}

        for i in range(1, len(all_samples)):
            prev_time, prev_hr = all_samples[i - 1]
            curr_time, curr_hr = all_samples[i]

            delta_sec = (curr_time - prev_time).total_seconds()
            raw_minutes = delta_sec / 60.0
            if raw_minutes <= 0:
                continue

            minutes = min(raw_minutes, 1.0)
            avg_hr = (prev_hr + curr_hr) / 2.0

            if avg_hr < 0.50 * max_hr:
                continue

            zone = HeartRateZone.zone_for(avg_hr, max_hr)
            interval_load = minutes * zone.weight
            if interval_load <= 0:
                continue

            total_load += interval_load

            # Midpoint timestamp of this interval
            midpoint = prev_time + timedelta(seconds=delta_sec / 2.0)

            # Check if midpoint falls within any workout window
            matched_idx = None
            for idx, w in enumerate(workout_intervals):
                if w.start <= midpoint <= w.end:
                    matched_idx = idx
                    break

            if matched_idx is not None:
                w_load += interval_load
                detail_loads[matched_idx] = detail_loads.get(matched_idx, 0.0) + interval_load
                if matched_idx not in detail_zones:
                    detail_zones[matched_idx] = {z: 0.0 for z in HeartRateZone}
                detail_zones[matched_idx][zone] += minutes
            else:
                i_load += interval_load

        details = []
        for idx, interval in enumerate(workout_intervals):
            load = detail_loads.get(idx, 0.0)
            if load > 0.5:  # meaningful threshold
                details.append(
                    WorkoutStrainDetail(
                        activity_name=interval.activity_name,
                        strain=load,
                        zone_minutes=detail_zones.get(idx, {z: 0.0 for z in HeartRateZone})
                    )
                )

        return WorkoutStrainResult(
            total=total_load,
            workout_strain=w_load,
            incidental_strain=i_load,
            details=details
        )

    @staticmethod
    def capacity(load_history: list[float]) -> float:
        """
        Determines the user's daily capacity for normalization:
          - First 7 days (< CALIBRATION_DAYS): returns fixed default 500.0
          - 7+ days: returns the rolling average of up to the last 14 days of StrainLoad.
        """
        if len(load_history) < StrainCalculator.CALIBRATION_DAYS:
            return StrainCalculator.ESTIMATED_CALIBRATION_CAPACITY
        recent = load_history[-StrainCalculator.ROLLING_CAPACITY_DAYS:]
        if not recent:
            return StrainCalculator.ESTIMATED_CALIBRATION_CAPACITY
        return sum(recent) / len(recent)

    @staticmethod
    def is_calibrating(load_history: list[float]) -> bool:
        """True while user has < 7 days of historical strain data."""
        return len(load_history) < StrainCalculator.CALIBRATION_DAYS

    @staticmethod
    def score(load: float, capacity: float) -> float:
        """
        Converts raw StrainLoad to a 0–100 score relative to personal capacity:
          StrainScore = min(100.0, (StrainLoad / Capacity) * 100.0)
        """
        if capacity <= 0:
            return 0.0
        return min(100.0, (load / capacity) * 100.0)

    @staticmethod
    def score_to_whoop_scale(strain_score: float) -> float:
        """
        Converts 0–100 StrainScore to the WHOOP-style 0–21 scale
        used by RecoveryCalculator and SleepCalculator:
          strain_0_21 = (strain_score / 100.0) * 21.0
        """
        return (strain_score / 100.0) * 21.0


# ──────────────────────────────────────────────────────────────────────────────
# Demo / Run block
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("  SOMA STRAIN CALCULATOR DEMO")
    print("=" * 65)

    age = 22
    max_hr = StrainCalculator.estimated_max_hr(age)
    print(f"\nUser Age: {age}  --> Estimated Max HR (Tanaka): {max_hr:.1f} bpm")
    print("HR Zones thresholds:")
    print(f"  < 50%  (< {0.50*max_hr:.1f} bpm)   : Resting / Passive (0 load)")
    print(f"  Zone 1 ({0.50*max_hr:.1f}-{0.60*max_hr:.1f} bpm) : Weight {HeartRateZone.ZONE1.weight} (Warmup / Recovery)")
    print(f"  Zone 2 ({0.60*max_hr:.1f}-{0.70*max_hr:.1f} bpm) : Weight {HeartRateZone.ZONE2.weight} (Fat Burn / Base)")
    print(f"  Zone 3 ({0.70*max_hr:.1f}-{0.80*max_hr:.1f} bpm) : Weight {HeartRateZone.ZONE3.weight} (Aerobic / Tempo)")
    print(f"  Zone 4 ({0.80*max_hr:.1f}-{0.90*max_hr:.1f} bpm) : Weight {HeartRateZone.ZONE4.weight} (Anaerobic / Threshold)")
    print(f"  Zone 5 (>= {0.90*max_hr:.1f} bpm)       : Weight {HeartRateZone.ZONE5.weight} (Max Effort)")

    # Simulate a day's HR samples:
    # 1. Morning resting / passive: 45 min at 75 bpm (< 50% maxHR)
    # 2. Workout (Running): 35 min at 155 bpm (Zone 3/4) + 10 min at 178 bpm (Zone 5)
    # 3. Walking / incidental: 30 min at 120 bpm (Zone 2)
    now = datetime(2026, 9, 26, 8, 0, 0)
    samples: list[tuple[datetime, float]] = []

    # 45 min resting
    for m in range(46):
        samples.append((now + timedelta(minutes=m), 72.0))
    t = now + timedelta(minutes=45)

    # Workout: 09:00 to 09:45
    workout_start = t + timedelta(minutes=15)
    w_t = workout_start
    # 35 min in Zone 3/4 (155 bpm)
    for m in range(35):
        samples.append((w_t + timedelta(minutes=m), 155.0))
    # 10 min in Zone 5 (178 bpm)
    for m in range(35, 46):
        samples.append((w_t + timedelta(minutes=m), 178.0))
    workout_end = w_t + timedelta(minutes=45)

    # Incidental walking later in the afternoon: 30 min at 122 bpm (Zone 2)
    incidental_start = workout_end + timedelta(hours=3)
    for m in range(31):
        samples.append((incidental_start + timedelta(minutes=m), 122.0))

    workouts = [WorkoutInterval(start=workout_start, end=workout_end, activity_name="Outdoor Run")]

    result = StrainCalculator.calculate_workout_aware(workouts, samples, max_hr)

    # Capacity history simulation (e.g. 10 days of history, mean 350)
    past_loads = [320.0, 340.0, 360.0, 310.0, 380.0, 350.0, 330.0, 370.0, 340.0, 360.0]
    user_capacity = StrainCalculator.capacity(past_loads)
    calibrating = StrainCalculator.is_calibrating(past_loads)

    score_100 = StrainCalculator.score(result.total, user_capacity)
    score_21 = StrainCalculator.score_to_whoop_scale(score_100)

    print("\n" + "-" * 65)
    print(f"  TOTAL STRAIN LOAD   : {result.total:.1f} load units")
    print(f"    - Workout Strain  : {result.workout_strain:.1f} units")
    print(f"    - Incidental Load : {result.incidental_strain:.1f} units")
    print("-" * 65)

    for detail in result.details:
        print(f"  Workout: '{detail.activity_name}' -> Strain Load: {detail.strain:.1f}")
        for z in HeartRateZone:
            mins = detail.zone_minutes.get(z, 0.0)
            if mins > 0:
                print(f"    * {z.label:30s}: {mins:4.1f} min (weight {z.weight}) -> {mins*z.weight:5.1f} load")

    print("-" * 65)
    print(f"  Personal Capacity   : {user_capacity:.1f} (Calibrating: {calibrating})")
    print(f"  Strain Score (0-100): {score_100:.1f} / 100")
    print(f"  Strain Score (0-21) : {score_21:.1f} / 21.0  (WHOOP scale for recovery)")
    print("=" * 65)
