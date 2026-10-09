"""JSON display precision must not feed back into calculations."""
from datetime import date, datetime, timedelta, timezone
import json

from fastapi.encoders import jsonable_encoder
import pytest

from strain import calculate_strain
from strain_service import strain_response


@pytest.mark.parametrize('score,display', [(16.86, 16.8), (20.999999999999996, 20.9), (0., 0.), (10., 10.)])
def test_floor_json_only_preserves_model_and_python_dump(score, display):
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    end = start + timedelta(minutes=4)
    current = calculate_strain([(start, 160), (end, 160)],
        [{'start': start, 'end': end, 'activity_name': 'Synthetic run'}],
        {'start': start, 'end': end}, 30, [56.] * 7, 'm')
    current.update(date=date(2026, 10, 7), day_window={'start': start, 'end': end}, strain=score)
    current['workouts'][0]['strain'] = score
    result = strain_response(current, {current['date']: current}, 'demo', 30)
    assert result.strain == result.score_21 == round(score, 1)
    assert result.workouts[0].strain == round(score, 1)
    assert result.model_dump()['strain'] == round(score, 1)
    for encoded in (result.model_dump(mode='json'), json.loads(result.model_dump_json()), jsonable_encoder(result)):
        assert encoded['strain'] == encoded['score_21'] == display
        assert encoded['workouts'][0]['strain'] == display
    assert current['strain'] == current['workouts'][0]['strain'] == score


def test_zero_load_without_workouts_serializes_zero():
    start = datetime(2026, 10, 7, tzinfo=timezone.utc)
    current = calculate_strain([], [], {'start': start, 'end': start + timedelta(hours=1)},
                               30, [56.], 'm')
    current.update(date=date(2026, 10, 7), day_window={'start': start, 'end': start + timedelta(hours=1)})
    result = strain_response(current, {current['date']: current}, 'demo', 30)
    assert jsonable_encoder(result)['strain'] == 0.
