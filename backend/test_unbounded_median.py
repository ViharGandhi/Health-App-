import asyncio
from datetime import date, timedelta
from test_adapter_fuzz import finite_tree
from recovery_score import robust
from health_trends import build_health_response
from main import _compute_real_recovery
import pytest


@pytest.mark.parametrize('layer', ['robust_reference', 'health', 'descriptive_recovery'])
def test_large_finite_even_medians_do_not_overflow(layer):
    day = date(2026, 10, 7)
    points = [{'date': (day - timedelta(days=i)).isoformat(), 'value': 1.79e308} for i in range(15)]
    if layer == 'robust_reference':
        result = robust([1.79e308] * 30, .05)
    elif layer == 'health':
        result = build_health_response({'hrv': points}, [], day, day, 'W', False).model_dump()
    else:
        result = asyncio.run(_compute_real_recovery(None, day, history={'hrv': points, 'rhr': []})).model_dump()
    finite_tree(result)
