"""Compare illness-flag rules: false alarms on normal days vs. detection of mild and clear fevers.

Uses the same robust reference as production (median and 1.4826 x MAD over D-67..D-8).
"""
import random
import sys
from pathlib import Path
from statistics import median

sys.path[:0] = [str(Path(__file__).parent)]
import recovery_check as rc  # noqa: E402

RULES = {
    'current: either > 2 SD': lambda t, r: t > 2 or r > 2,
    'either > 2.5 SD': lambda t, r: t > 2.5 or r > 2.5,
    'either > 3 SD': lambda t, r: t > 3 or r > 3,
    'both > 1.5 SD': lambda t, r: t > 1.5 and r > 1.5,
    'both > 1 SD and one > 2': lambda t, r: t > 1 and r > 1 and max(t, r) > 2,
    'sum > 3.5': lambda t, r: t + r > 3.5,
    'temp > 2.5 or (temp > 1.5 and rr > 1.5)': lambda t, r: t > 2.5 or t > 1.5 and r > 1.5,
}


def zscores(history, reference_days):
    out = []
    for metric in ('skin_temperature', 'respiratory_rate'):
        values = [p['value'] for p in history[metric]]
        today, reference = values[-1], values[-(reference_days + 8):-8]
        center = median(reference)
        spread = 1.4826 * median(abs(v - center) for v in reference)
        out.append((today - center) / spread if spread else 0.)
    return out


def main():
    rng = random.Random(11)
    scenarios = {'normal day': {}, 'mild fever': {0: {'temp': .5, 'rr': 1.0}}, 'clear fever': {0: {'temp': 1.0, 'rr': 2.0}},
                 'fever, breathing unchanged': {0: {'temp': .8}}}
    for days in (60, 14):
        print(f'\nreference {days} days')
        rates = {name: {} for name in RULES}
        for scenario, effects in scenarios.items():
            pairs = [zscores(rc.person(rng, days=days + 8, effects=effects), days) for _ in range(4000)]
            for name, rule in RULES.items():
                rates[name][scenario] = sum(rule(t, r) for t, r in pairs) / len(pairs)
        for name, row in rates.items():
            print(f'{name:42s}', '  '.join(f'{k}: {v:5.1%}' for k, v in row.items()))


if __name__ == '__main__':
    main()
