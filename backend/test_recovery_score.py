import math
import unittest
from datetime import date, timedelta

from recovery_score import calculate_recovery, recovery_from_history, robust


DAY = date(2026, 10, 4)


def reference_history(count=60, recent=7):
    return {
        "hrv": [{"date": (DAY - timedelta(days=8 + i)).isoformat(), "value": 40.0} for i in range(count)]
               + [{"date": (DAY - timedelta(days=i)).isoformat(), "value": 40.0} for i in range(recent)],
        "rhr": [{"date": (DAY - timedelta(days=i)).isoformat(), "value": 55.0, "method": "WITH_SLEEP"}
                for i in [*range(8, 68), 0]],
    }


class RecoveryScoreTests(unittest.TestCase):
    def score(self, **changes):
        inputs = dict(baseline_hrv=[40.0] * 60, recent_hrv=[40.0] * 7,
                      today_hrv=40.0, baseline_rhr=[55.0] * 60,
                      today_rhr=55.0, sleep_min=450.0, need_min=450.0)
        inputs.update(changes)
        return calculate_recovery(**inputs)

    def test_insufficient_baseline_or_recent_has_no_score_or_zone(self):
        for changes in ({"baseline_hrv": [40.0] * 20}, {"recent_hrv": [40.0] * 3}):
            result = self.score(**changes)
            self.assertEqual(result.status, "building_reference")
            self.assertIsNone(result.z)
            self.assertIsNone(result.percent)
            self.assertIsNone(result.zone)
            self.assertIsNone(result.confidence)

    def test_baseline_medians_with_full_sleep_are_neutral(self):
        result = self.score()
        self.assertEqual(result.z, 0)
        self.assertEqual(result.percent, 50)
        self.assertEqual(result.zone, "normal")
        self.assertEqual(result.confidence, "high")
        self.assertTrue(result.estimated)

    def test_higher_hrv_raises_and_higher_rhr_lowers(self):
        self.assertGreater(self.score(today_hrv=50).percent, self.score().percent)
        self.assertLess(self.score(today_rhr=58).percent, self.score().percent)

    def test_flat_reference_uses_configured_floors(self):
        self.assertEqual(robust([math.log(40)] * 60, .05), (math.log(40), .05))
        self.assertEqual(robust([55] * 60, 1), (55, 1))
        self.assertTrue(math.isfinite(self.score(today_hrv=41, today_rhr=56).z))

    def test_extreme_outlier_does_not_move_robust_reference(self):
        reference = [math.log(value) for value in [38, 39, 40, 41, 42] * 12]
        changed = [*reference[:-1], math.log(10000)]
        mu, sigma = robust(reference, .05)
        changed_mu, changed_sigma = robust(changed, .05)
        self.assertAlmostEqual(mu, changed_mu)
        self.assertAlmostEqual(sigma, changed_sigma)

    def test_sleep_thresholds_and_no_extra_sleep_bonus(self):
        for ratio in (.85, 1, 1.2):
            self.assertAlmostEqual(self.score(sleep_min=450 * ratio).components["sleep_adj"], 0)
        for minutes in (270, 240):
            self.assertAlmostEqual(self.score(sleep_min=minutes).components["sleep_adj"], -.5)
        self.assertAlmostEqual(self.score(sleep_min=450 * .725).components["sleep_adj"], -.25)

    def test_missing_sleep_or_need_has_no_penalty_or_high_confidence(self):
        for changes in ({"sleep_min": None}, {"need_min": None}, {"need_min": 0}):
            result = self.score(**changes)
            self.assertEqual(result.components["sleep_adj"], 0)
            self.assertIsNone(result.sleep_context["performance"])
            self.assertEqual(result.confidence, "medium")

    def test_missing_or_insufficient_rhr_uses_hrv_only(self):
        for changes in ({"today_rhr": None}, {"baseline_rhr": [55] * 20}):
            result = self.score(today_hrv=45, **changes)
            self.assertIsNone(result.components["z_rhr"])
            self.assertAlmostEqual(result.z, result.components["z_hrv"], places=2)
            self.assertEqual(result.confidence, "medium")

    def test_missing_today_hrv_uses_recent_mean(self):
        result = self.score(today_hrv=None, recent_hrv=[45] * 6, today_rhr=None)
        self.assertAlmostEqual(result.components["z_hrv"], (math.log(45) - math.log(40)) / .05)

    def test_illness_caps_z_including_positive_signal(self):
        result = self.score(today_hrv=80, illness_flag=True)
        self.assertEqual(result.z, -.5)
        self.assertEqual(result.percent, 31)
        # The specification makes exactly -0.5 part of the normal band.
        self.assertEqual(result.zone, "normal")

    def test_extremes_are_clamped(self):
        for hrv, expected in ((10000, 3), (.00001, -3)):
            self.assertEqual(self.score(today_hrv=hrv, today_rhr=None).z, expected)

    def test_confidence_thresholds_and_low_percent_withheld(self):
        for baseline, recent, confidence in ((21, 4, "low"), (27, 7, "low"),
                                              (28, 5, "medium"), (44, 7, "medium"), (45, 6, "high")):
            result = self.score(baseline_hrv=[40] * baseline, recent_hrv=[40] * recent)
            self.assertEqual(result.confidence, confidence)
            self.assertEqual(result.percent, None if confidence == "low" else 50)
            self.assertEqual(result.zone, "normal")

    def test_short_sleep_is_discarded_but_180_minutes_is_valid(self):
        for minutes in (0, 120, 179.99):
            result = self.score(sleep_min=minutes)
            self.assertIsNone(result.sleep_context["sleep_min"])
            self.assertEqual(result.components["sleep_adj"], 0)
            self.assertNotEqual(result.confidence, "high")
        self.assertEqual(self.score(sleep_min=180).components["sleep_adj"], -.5)

    def test_nonpositive_missing_and_nonfinite_readings_are_discarded(self):
        invalid = [0, -1, None, float("nan"), float("inf")]
        result = self.score(baseline_hrv=[40] * 21 + invalid, recent_hrv=[40] * 4 + invalid,
                            today_hrv=0, baseline_rhr=[55] * 20 + invalid, today_rhr=-1)
        self.assertEqual(result.baseline_days, 21)
        self.assertEqual(result.recent_nights, 4)
        self.assertEqual(result.rhr_baseline_days, 20)
        self.assertIsNone(result.components["z_rhr"])
        self.assertEqual(result.z, 0)

    def test_windows_exclude_recent_and_old_days_and_deduplicate_dates(self):
        history = reference_history()
        history["hrv"] += [{"date": (DAY - timedelta(days=i)).isoformat(), "value": 4000}
                           for i in (68, -1)]
        history["hrv"].append(history["hrv"][0].copy())
        result = recovery_from_history(history, DAY, 450, 450)
        self.assertEqual(result.baseline_days, 60)
        self.assertEqual(result.recent_nights, 6)
        self.assertEqual(result.percent, 50)

    def test_same_method_rhr_filter_and_unknown_method_fallback(self):
        for method in ("ONLY_WITH_AWAKE_DATA", None, "CALCULATION_METHOD_UNSPECIFIED"):
            history = reference_history()
            history["rhr"][-1]["method"] = method
            result = recovery_from_history(history, DAY, 450, 450)
            self.assertEqual(result.rhr_baseline_days, 0)
            self.assertIsNone(result.components["z_rhr"])

    def test_illness_uses_own_robust_reference_and_requires_spread(self):
        for metric in ("respiratory_rate", "skin_temperature"):
            history = reference_history()
            history[metric] = [{"date": (DAY - timedelta(days=8 + i)).isoformat(),
                                "value": 16 + (i % 3 - 1) * .2} for i in range(60)]
            history[metric].append({"date": DAY.isoformat(), "value": 20})
            result = recovery_from_history(history, DAY)
            self.assertTrue(result.illness_flag)
            self.assertEqual(result.z, -.5)
            history[metric] = history[metric][:20] + history[metric][-1:]
            self.assertFalse(recovery_from_history(history, DAY).illness_flag)
            history[metric] = [{"date": (DAY - timedelta(days=8 + i)).isoformat(), "value": 16}
                               for i in range(60)] + history[metric][-1:]
            self.assertFalse(recovery_from_history(history, DAY).illness_flag)

    def test_zone_uses_unrounded_z(self):
        result = self.score(today_rhr=53.749, today_hrv=40)
        self.assertEqual(result.z, .5)
        self.assertEqual(result.zone, "above_normal")


if __name__ == "__main__":
    unittest.main()
