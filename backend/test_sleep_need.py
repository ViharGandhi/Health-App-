"""Numerical contracts for the user-specified sleep-need formula."""

from dataclasses import FrozenInstanceError
import math
import unittest

from sleep_need import SleepNeedNight, calculate_sleep_need, format_sleep_minutes, sleep_debt, strain_sleep_add


class SleepNeedTests(unittest.TestCase):
    def test_zero_and_max_strain_percent(self):
        self.assertEqual(calculate_sleep_need(0).strain_add_min, 0)
        self.assertEqual(calculate_sleep_need(100).strain_add_min, 26)

    def test_cutoff(self):
        self.assertEqual(strain_sleep_add(5), 0)
        self.assertGreater(strain_sleep_add(10), 1)

    def test_strain_clamps(self):
        self.assertEqual(calculate_sleep_need(-50).strain_add_min, 0)
        self.assertEqual(calculate_sleep_need(150).strain_add_min, 26)

    def test_default(self):
        result = calculate_sleep_need(0)
        self.assertEqual(result.total_need_min, 450)
        self.assertEqual(result.baseline_min, 450)
        self.assertEqual(format_sleep_minutes(result.total_need_min), '7h 30m')

    def test_weighted_shortfalls_and_surpluses(self):
        debt = sleep_debt([SleepNeedNight(350, 0), SleepNeedNight(500, 0)])
        self.assertAlmostEqual(debt, (100 - 0.85 * 50) / 1.85)
        self.assertLess(debt, sleep_debt([SleepNeedNight(350, 0)]))

    def test_debt_bounds(self):
        self.assertEqual(sleep_debt([SleepNeedNight(1000, 100)]), 0)
        self.assertEqual(sleep_debt([SleepNeedNight(0, 0)]), 240)

    def test_missing_slots_keep_their_original_weights(self):
        history = [SleepNeedNight(350, 0), None, SleepNeedNight(500, 0)]
        self.assertAlmostEqual(sleep_debt(history), (100 - 0.7 * 50) / 1.7)
        self.assertEqual(sleep_debt([None, SleepNeedNight(None, 0), SleepNeedNight(0, None)]), 0)

    def test_no_history(self):
        self.assertEqual(sleep_debt([]), 0)
        self.assertEqual(calculate_sleep_need(50).sleep_debt_min, 0)

    def test_seven_night_limit(self):
        history = [SleepNeedNight(450, 0)] * 7 + [SleepNeedNight(0, 100)]
        self.assertEqual(sleep_debt(history), 0)

    def test_repayment(self):
        result = calculate_sleep_need(0, [SleepNeedNight(350, 0)])
        self.assertEqual(result.sleep_debt_min, 100)
        self.assertAlmostEqual(result.debt_add_min, 34)
        self.assertEqual(result.total_need_min, 484)

    def test_debt_does_not_use_debt_adjusted_need(self):
        history = [SleepNeedNight(450 + strain_sleep_add(21), 100)] * 7
        result = calculate_sleep_need(100, history)
        self.assertEqual(result.sleep_debt_min, 0)
        self.assertEqual(result.total_need_min, 476)

    def test_nap_credit_and_floor(self):
        self.assertEqual(calculate_sleep_need(0, nap_min_today=30).total_need_min, 420)
        result = calculate_sleep_need(100, nap_min_today=500)
        self.assertEqual(result.nap_credit_min, 500)
        self.assertEqual(result.total_need_min, 360)

    def test_ceiling_and_baseline_override(self):
        result = calculate_sleep_need(100, [SleepNeedNight(0, 100)], baseline_need_min=650)
        self.assertEqual(result.baseline_min, 650)
        self.assertEqual(result.total_need_min, 660)

    def test_no_internal_rounding(self):
        result = calculate_sleep_need(75, [SleepNeedNight(380.123, 83.45)])
        self.assertNotEqual(result.strain_add_min, round(result.strain_add_min))
        self.assertNotEqual(result.total_need_min, round(result.total_need_min))
        self.assertIsInstance(result.total_need_min, float)

    def test_formatting_carries_minutes(self):
        self.assertEqual(format_sleep_minutes(479.9), '8h 0m')
        self.assertEqual(format_sleep_minutes(0), '0h 0m')

    def test_inputs_are_not_mutated(self):
        history = [SleepNeedNight(370.5, 50), None]
        original = history.copy()
        first = calculate_sleep_need(40, history)
        self.assertEqual(history, original)
        self.assertEqual(first, calculate_sleep_need(40, history))
        with self.assertRaises(FrozenInstanceError):
            first.total_need_min = 0

    def test_invalid_readings_are_not_silently_used(self):
        for value in [math.nan, math.inf]:
            with self.assertRaises(ValueError):
                calculate_sleep_need(value)
        with self.assertRaises(ValueError):
            calculate_sleep_need(0, nap_min_today=-1)
