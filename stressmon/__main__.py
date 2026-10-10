"""python -m stressmon; all analysis is local and offline."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

from .config import DEFAULT_CONFIG, load_config
from .io import load_export, alignment_probe
from .pipeline import preprocess_hr, score_export, daily_summary


def serializable(value):
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline, unvalidated Fitbit HR/HRV stress estimate')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('probe', 'score', 'plot', 'calibrate'):
        command = sub.add_parser(name)
        command.add_argument('--takeout', required=True)
        command.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
        command.add_argument('--out', type=Path)
        if name in ('score', 'plot'):
            command.add_argument('--date', required=name == 'plot')
        if name == 'calibrate':
            choice = command.add_mutually_exclusive_group()
            choice.add_argument('--anchors', action='store_true')
            choice.add_argument('--reference', type=Path)
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
        data = load_export(args.takeout, cfg)
        if args.command == 'probe':
            report, _, _ = alignment_probe(data, preprocess_hr(data, cfg), cfg)
            print(json.dumps(serializable(report), indent=2, allow_nan=False))
            return 0
        features, report = score_export(data, cfg)
        print(json.dumps(serializable(report), indent=2, allow_nan=False))
        out = args.out or Path(cfg['output']['directory'])
        out.mkdir(parents=True, exist_ok=True)
        if args.command == 'score':
            selected = features[features['date'].eq(args.date)] if args.date else features
            if selected.empty:
                raise ValueError('Requested date has no observations')
            selected.to_csv(out / 'scores_5min.csv', float_format=f'%.{cfg["output"]["float_precision"]}f')
            daily_summary(selected, cfg).to_csv(out / 'daily_summary.csv', index=False,
                                               float_format=f'%.{cfg["output"]["float_precision"]}f')
        elif args.command == 'plot':
            from .plot import plot_day
            plot_day(features, data, args.date, cfg, out / f'stress_{args.date}.png')
        else:
            from .calibration import fit_anchors, fit_reference, read_reference, write_config
            if args.reference:
                fitted, calibration = fit_reference(data, features, read_reference(args.reference, cfg), cfg)
            else:
                fitted, calibration = fit_anchors(features, cfg)
            write_config(args.config, fitted)
            calibration['parameters'] = fitted['score']
            (out / 'calibration.json').write_text(json.dumps(serializable(calibration), indent=2, allow_nan=False), encoding='utf-8')
            print(json.dumps(serializable(calibration), indent=2, allow_nan=False))
        (out / 'probe.json').write_text(json.dumps(serializable(report), indent=2, allow_nan=False), encoding='utf-8')
        print(f'Wrote results to {out.resolve()}')
        return 0
    except (ValueError, OSError, KeyError) as error:
        # Parser exceptions can quote raw field values; avoid leaking those rows.
        if isinstance(error, ValueError) and error.__class__ is not ValueError:
            message = 'Input parsing failed; check the permitted file formats and columns.'
        else:
            message = str(error)
        print(f'Error: {message}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
