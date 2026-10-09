"""Exercise public calculation chains on 200 deterministic typed fixtures each."""
from datetime import date, datetime, timedelta, timezone
from dataclasses import replace

import pytest
from hypothesis import given, settings, strategies as st

from test_adapter_fuzz import finite_tree
from strain import calculate_strain, strain_analytics, day_window
from sleepscore import SleepData, SleepCalculator, AyurvedicSleepCalculator, SleepConsistencyCalculator as LegacyConsistency
from recovery import RecoveryCalculator, RecoveryInput, hrv_z_score, log_hrv_stats
from recovery_score import calculate_recovery, recovery_from_history
from sleep_need import SleepNeedNight, calculate_sleep_need, strain_sleep_add, sleep_debt, format_sleep_minutes
from sleep_efficiency import SleepEfficiencyCalculator
from sleep_stage_ranges import SleepNight, StageSegment, stage_stats, personal_ranges, score_stages, stats_to_dict, stats_from_dict
from sleep_stress import prepare_night, score_night, build_baseline, summarize_nights
from sleep_analytics import sleep_observations, build_sleep_analytics, timing_records, demo_sleep_need_inputs
from sleep_trends import build_sleep_trend, build_consistency_scores
from health_trends import build_health_response, build_heart_rate_response
from recovery_analytics import build_recovery_analytics, typical_ranges
from mock_sleep_stage_ranges import mock_stage_points
from validation.run_simulations import stress_night


BASE = datetime(2026, 10, 7, 7, tzinfo=timezone.utc)
DAY = BASE.date()
real = lambda lo, hi: st.floats(lo, hi, allow_nan=False, allow_infinity=False)


@pytest.mark.parametrize('chain', ['strain', 'composite_legacy', 'sleep_need', 'recovery', 'stage_ranges',
                                  'sleep_stress', 'sleep_trends', 'health_analytics', 'legacy_clock'])
@settings(max_examples=200, derandomize=True, deadline=None, database=None)
@given(real(1, 200), real(35, 130), st.integers(180, 660), st.integers(18, 100))
def test_typed_calculation_chains_are_finite_bounded_and_repeatable(chain, hrv, hr, minutes, age):
    if chain == 'strain':
        samples = [(BASE + timedelta(minutes=i), hr) for i in range(46)]
        window = day_window(DAY, BASE + timedelta(hours=15), [], timezone.utc)
        result = calculate_strain(samples, [], window, age, [55.], 'm')
        assert 0 <= result['strain'] < 21 and 0 <= result['coverage'] <= 1
        assert result == calculate_strain(list(reversed(samples)), [], window, age, [55.], 'm')
        finite_tree(strain_analytics([{**result, 'date': DAY}], DAY, result['strain'], 50))
    elif chain == 'composite_legacy':
        sleep = SleepData(minutes * 60., minutes * 12., minutes * 12., minutes * 36.,
                          1200., minutes * 60. + 1200., None, None, 1)
        score = SleepCalculator.calculate_score(sleep, 7.5, hrv, hr, 75, 40, 60, age)
        assert 0 <= score <= 100
        assert score == SleepCalculator.calculate_score(sleep, 7.5, hrv, hr, 75, 40, 60, age)
        finite_tree([SleepCalculator.compute_sleep_efficiency_score(sleep), SleepCalculator.compute_restfulness_score(sleep),
                     SleepCalculator.calculate_sleep_need(7.5, [(7.5, minutes / 60)], 15),
                     SleepCalculator.compute_sleep_debt([(7.5, minutes / 60)])])
        result = RecoveryCalculator.calculate(RecoveryInput(hrv, 40, hr, 60, score, 15, hrv_history=[40.] * 7))
        assert 0 <= result['score'] <= 100
        finite_tree([result, hrv_z_score(hrv, [40.] * 7), log_hrv_stats([hrv] * 7)])
    elif chain == 'sleep_need':
        history = [SleepNeedNight(minutes, 50.)] * 7
        result = calculate_sleep_need(50., history, minutes / 10)
        assert 360 <= result.total_need_min <= 660
        assert result == calculate_sleep_need(50., history, minutes / 10)
        finite_tree([result, strain_sleep_add(10.5), sleep_debt(history)])
        assert isinstance(format_sleep_minutes(result.total_need_min), str)
    elif chain == 'recovery':
        result = calculate_recovery([40.] * 60, [40.] * 7, hrv, [55.] * 60, hr, minutes, 450.)
        assert result.percent is None or 0 <= result.percent <= 100
        history = {'hrv': [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': hrv} for i in range(68)]}
        finite_tree([result, recovery_from_history(history, DAY, minutes, 450, age)])
    elif chain == 'stage_ranges':
        end = BASE + timedelta(minutes=minutes + 30)
        night = SleepNight('synthetic', DAY, BASE, end, 'STAGES', 'SUCCEEDED', True,
                           (StageSegment(BASE, BASE + timedelta(minutes=30), 'awake'),
                            StageSegment(BASE + timedelta(minutes=30), end, 'light')))
        stats, status = stage_stats(night)
        assert status == 'ok'
        history = [replace(stats, sleep_id=f'prior-{i}', night_date=DAY - timedelta(days=i)) for i in range(1, 8)]
        assert sum(stats.pct[s] for s in ('awake', 'light', 'deep', 'rem')) == pytest.approx(100)
        assert stats_from_dict(stats_to_dict(stats)) == stats
        finite_tree([personal_ranges(stats, history), score_stages(stats, history)])
        result = stats
    elif chain == 'sleep_stress':
        current = stress_night(DAY, [(hrv, hr, 5.)] * 72)
        prior = [stress_night(DAY - timedelta(days=i), [(40., 60., 5.)] * 72) for i in range(1, 8)]
        result = score_night(current, prior, computed_at=BASE)
        assert 0 <= result['stress_pct'] <= 100 and 0 <= result['coverage'] <= 1
        assert result == score_night(current, prior, computed_at=BASE)
        finite_tree([build_baseline(current, prior), prepare_night(current.night, [], []), summarize_nights([result])])
    elif chain == 'sleep_trends':
        observations = sleep_observations(mock_stage_points(DAY, 10), DAY, is_mock=True)
        records = timing_records(observations)
        result = build_sleep_analytics(observations, DAY, 'W', True)
        finite_tree([build_sleep_trend(records, DAY - timedelta(days=6), DAY, 'W', 'efficiency', True),
                     build_sleep_trend(records, DAY - timedelta(days=6), DAY, 'W', 'consistency', True),
                     build_consistency_scores(records, DAY, 'W', True), demo_sleep_need_inputs(observations, DAY).for_tonight(DAY)])
    elif chain == 'health_analytics':
        history = {metric: [{'date': (DAY - timedelta(days=i)).isoformat(), 'value': value, 'method': 'WITH_SLEEP'}
                           for i in range(68)] for metric, value in [('hrv', hrv), ('rhr', hr)]}
        result = build_health_response(history, [(BASE, hr)], DAY - timedelta(days=6), DAY, 'W', False, age).model_dump()
        finite_tree([build_heart_rate_response([(BASE, hr)], DAY, False).model_dump(), typical_ranges(history, DAY, age),
                     build_recovery_analytics(history, [], DAY, 'W', {'score': 50}, is_mock=False, age=age)])
    else:
        start = BASE.replace(tzinfo=None) - timedelta(hours=10)
        end = start + timedelta(minutes=minutes)
        windows = AyurvedicSleepCalculator.build_windows(start.date())
        result = AyurvedicSleepCalculator.calculate([(start, end)], start.date())
        assert 0 <= result <= 10
        finite_tree([AyurvedicSleepCalculator.breakdown(start, end, start.date()),
                     AyurvedicSleepCalculator.raw_points(start, end, windows),
                     LegacyConsistency.calculate([start] * 7, [end] * 7)])
    finite_tree(result)
