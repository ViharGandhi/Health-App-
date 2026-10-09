import math

import pytest

import recovery
import sleepscore


@pytest.mark.parametrize('module', [recovery, sleepscore])
def test_nonfinite_history_cannot_contaminate_legacy_hrv_statistics(module):
    clean = [38., 40., 42., 44., 39., 41., 43.]
    assert module.log_hrv_stats(clean + [float('inf'), float('nan'), -1., 0.]) == module.log_hrv_stats(clean)


@pytest.mark.parametrize('module', [recovery, sleepscore])
@pytest.mark.parametrize('today', [float('nan'), float('inf')])
def test_nonfinite_current_hrv_has_no_legacy_z(module, today):
    assert module.hrv_z_score(today, [38., 40., 42., 44., 39., 41., 43.]) is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), 0., -1.])
def test_invalid_legacy_current_vitals_follow_existing_missing_value_fallback(value):
    result = recovery.RecoveryCalculator.calculate(recovery.RecoveryInput(
        today_hrv=value, hrv_baseline=40., today_rhr=value, rhr_baseline=55.,
        hrv_history=[38., 40., 42., 44., 39., 41., 43.]))
    assert result['hrv_component'] == 50.
    assert result['rhr_component'] == 50.
