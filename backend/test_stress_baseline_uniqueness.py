from dataclasses import replace
from datetime import timedelta

from sleep_stress import build_baseline
from test_sleep_stress import DAY, make_night, baseline_history


def test_repeated_single_night_cannot_complete_baseline():
    current = make_night(DAY, [(20, 80, 5)] * 4)
    prior = baseline_history()[0]
    bands, count, _ = build_baseline(current, [prior] * 7)
    assert count == 1
    assert bands == {}


def test_longest_main_sleep_per_date_wins_independent_of_order():
    current = make_night(DAY, [(20, 80, 5)] * 4)
    prior = baseline_history()
    longer = replace(prior[0], night=replace(prior[0].night, sleep_id='longer',
                                           start_utc=prior[0].night.start_utc - timedelta(hours=1)))
    longer = replace(longer, windows=tuple(replace(w, hr=75) for w in longer.windows))
    expected = build_baseline(current, [longer, *prior[1:]])
    assert expected[1] == 7
    assert build_baseline(current, [*prior, longer]) == expected
    assert build_baseline(current, [longer, *reversed(prior)]) == expected


def test_nap_marked_main_cannot_count_as_reference_night():
    current = make_night(DAY, [(20, 80, 5)] * 4)
    prior = baseline_history()
    nap = replace(prior[0], night=replace(prior[0].night, sleep_id='nap', nap=True,
                                        night_date=DAY - timedelta(days=8)))
    assert build_baseline(current, [*prior, nap])[1] == 7
    assert build_baseline(current, [nap] * 7)[1] == 0
