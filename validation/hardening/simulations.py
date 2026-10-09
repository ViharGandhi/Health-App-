"""Compare unchanged independent formula oracles to both immutable audit baselines."""
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'final'
spec = importlib.util.spec_from_file_location('formula_audit', ROOT / 'validation/run_simulations.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe(v) for v in value]
    return value


def differences(before, after, parts=()):
    if isinstance(before, dict) and isinstance(after, dict):
        output = []
        for key in sorted(before.keys() | after.keys()):
            if key not in before or key not in after:
                present = after.get(key) if key in after else before.get(key)
                output.extend(added_leaves(present, parts + (key,), key in after))
            else:
                output.extend(differences(before[key], after[key], parts + (key,)))
        return output
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [d for i, (a, b) in enumerate(zip(before, after)) for d in differences(a, b, parts + (str(i),))]
    return [] if type(before) is type(after) and before == after else [dict(path='/' + '/'.join(parts), before=before, after=after)]


def added_leaves(value, parts, added):
    if isinstance(value, dict) and value:
        return [d for k, v in value.items() for d in added_leaves(v, parts + (k,), added)]
    if isinstance(value, list) and value:
        return [d for i, v in enumerate(value) for d in added_leaves(v, parts + (str(i),), added)]
    return [dict(path='/' + '/'.join(parts), before=None if added else value,
                 after=value if added else None, key_added=added)]


def run():
    OUT.mkdir(exist_ok=True)
    started = time.perf_counter()
    audit.run()
    assert len(audit.rows) == 1295 and all(row['passed'] for row in audit.rows)
    value = safe(dict(seed=audit.SEED, anchor_date=str(audit.DAY), cases=audit.rows,
                      findings=audit.findings, demo=audit.snapshots))
    (OUT / 'simulation-results.json').write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    for label, path in [('execution', HERE / 'baseline/simulations/simulation-results.json'),
                        ('audit', HERE / 'baseline/audit-final/simulation-results.json')]:
        baseline = json.loads(path.read_text())
        changes = differences(baseline, value)
        for change in changes:
            p = change['path']
            if p.startswith('/cases/'):
                index = int(change['path'].split('/')[2])
                change.update(family=value['cases'][index]['family'], case=value['cases'][index]['case'],
                              reason='UNEXPLAINED formula delta')
            elif '/body/' not in p:
                change['reason'] = 'UNEXPLAINED non-response delta'
            elif p.endswith('/estimator') and change.get('key_added'):
                change['reason'] = 'Estimator identity schema (a47cfcb)'
            elif any('/' + key in p for key in ('data_quality_flag', 'rejected_readings')) and change.get('key_added'):
                change['reason'] = 'Shared validity/rejection diagnostics schema (79f5eb3)'
            elif any('/' + key in p for key in ('component_coverage', 'components_available', 'defaulted_components', 'partial', 'status_reason')) and change.get('key_added'):
                change['reason'] = 'Approved component availability schema (32ee23d)'
            elif '/typical_range_reasons/' in p and change.get('key_added'):
                change['reason'] = 'Personal-range withholding diagnostics schema (97833bd)'
            elif p.endswith('/algo_version') and change['before'] == 'sleep-stage-ranges-1' and change['after'] == 'sleep-stage-ranges-3':
                change['reason'] = 'Main selection and overlong-stage cache namespace (623fc73, af85696)'
            elif p.endswith('/algo_version') and change['before'] == 'sleep-stress-5' and change['after'] == 'sleep-stress-9':
                change['reason'] = 'Provider bounds, main selection, reasons and partition cache namespace (c968fce, 623fc73, d37a4ad, 70ede57)'
            elif '/api/sleep/stress/' in p and any(p.endswith('/' + key) for key in ('anchor_verification', 'main_sleep_explicit', 'physical_duration_minutes', 'withheld_reason')) and change.get('key_added'):
                change['reason'] = 'Stress reason/anchor/selection provenance schema (d37a4ad, 623fc73)'
            elif p.endswith('/workouts/0/strain') and change['before'] == 9.2 and change['after'] == 9.1:
                change['reason'] = 'Approved JSON-only flooring of the unchanged raw workout strain (b578a51)'
            elif '/api/strain/analytics?demo=true/body/' in p and ('/days/' in p or '/previous_days/' in p) and (p.endswith('/score') or re_activity(p)) and (change['before'], change['after']) in ((13.9, 13.8), (6.4, 6.3), (3.6, 3.5), (9.2, 9.1)):
                change['reason'] = 'Approved JSON-only historical display flooring; aggregate/model inputs unchanged (4688814)'
            elif p.endswith('/computed_at'):
                change['reason'] = 'Computation-clock metadata only'
            else:
                change['reason'] = 'UNEXPLAINED response delta'
        (OUT / f'{label}-deltas.json').write_text(json.dumps(changes, indent=2), encoding='utf-8')
        assert not any(d['reason'].startswith('UNEXPLAINED') for d in changes), [d for d in changes if d['reason'].startswith('UNEXPLAINED')]
        print(json.dumps(dict(baseline=label, changed_leaves=len(changes),
            unchanged_formula_cases=sum(a == b for a, b in zip(baseline['cases'], value['cases'])),
            changed_paths=[d['path'] for d in changes[:35]])))
    if '--preview' not in sys.argv:
        audit.OUT = OUT
        shutil.copyfile(HERE / 'final-suite-complete.xml', OUT / 'test-results.xml')
        audit.write()
    (OUT / 'simulation-run-metadata.json').write_text(json.dumps(dict(checks=1295, passed=1295,
        runtime_s=time.perf_counter() - started), indent=2))


def re_activity(path):
    import re
    return bool(re.search(r'/activities/\d+/strain$', path))


if __name__ == '__main__':
    run()
