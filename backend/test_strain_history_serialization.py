from datetime import date, datetime, timedelta, timezone

import pytest

from strain import calculate_strain
from strain_service import strain_response
from strain_analytics import strain_day, build_strain_analytics


@pytest.mark.parametrize('score,display', [(16.86, 16.8), (20.999999999999996, 20.9)])
def test_historical_json_uses_floor_without_changing_aggregate_inputs(score, display):
    day = date(2026, 10, 7)
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    end = start + timedelta(minutes=4)
    session = dict(start=start, end=end, activity_name='Synthetic run')
    raw = calculate_strain([(start, 160.), (end, 160.)], [session],
        dict(start=start, end=end), 30, [56.], 'm')
    raw.update(date=day, day_window=dict(start=start, end=end), strain=score)
    raw['workouts'][0]['strain'] = score
    model = strain_response(raw, {day: raw}, 'demo', 30)
    row = strain_day(day, [], [session], model, 0)
    prior = {**row, 'date': (day - timedelta(days=1)).isoformat()}
    result = build_strain_analytics([row, prior], model, day, day, 'W', 'strain', True, day)
    assert result['days'][0]['score'] == display
    assert result['days'][0]['activities'][0]['strain'] == display
    assert result['prior_30_day_averages']['strain'] == round(score, 1)
    assert row['score'] == model.strain == round(score, 1)
    assert row['activities'][0]['strain'] == round(score, 1)
    assert not any(k.startswith('_') for k in result['days'][0])
