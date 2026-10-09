from sleepscore import SleepCalculator


def test_duration_large_slope_remains_numerically_stable():
    assert 0 <= SleepCalculator.compute_duration_score(.01, 7.5, 1000., .75) <= 100
