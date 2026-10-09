from datetime import date, timedelta

import pytest

from recovery_analytics import typical_ranges
from test_adapter_fuzz import finite_tree


DAY = date(2026, 10, 7)


@pytest.mark.parametrize('metric,values', [
    ('hrv', [1e-300] * 10 + [1e200] + [1e308] * 10),
    ('respiratory_rate', [1e-300] * 10 + [9e307] + [1.79e308] * 10),
])
def test_extreme_finite_references_never_produce_infinite_ranges(metric, values):
    history = {metric: [{'date': (DAY - timedelta(days=i + 8)).isoformat(), 'value': v}
                       for i, v in enumerate(values)]}
    reasons = {}
    result = typical_ranges(history, DAY, diagnostics=reasons)
    finite_tree(result)
    assert result[metric] is None
    assert reasons[metric] == 'numeric_range_overflow'
