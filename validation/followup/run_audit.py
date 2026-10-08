"""Re-run deterministic formula checks and export every before/after change."""
from collections import Counter
from pathlib import Path
import importlib.util
import json
import math
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('formula_audit', ROOT / 'validation/run_simulations.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
started = time.perf_counter()
audit.run()
failures = [dict(family=r['family'], case=r['case'], expected=r['expected'], actual=r['actual'])
            for r in audit.rows if not r['passed']]
if '--pre-spec' in sys.argv:
    (OUT / 'previous-spec-on-fixed-code.json').write_text(json.dumps({'checks': len(audit.rows),
        'failures': failures}, indent=2))
    print(json.dumps({'checks': len(audit.rows), 'old_spec_failures': len(failures)}))
    sys.exit(0)
audit.OUT = OUT / 'final'
audit.write()
manifest_path = audit.OUT / 'source-hashes.json'
manifest = json.loads(manifest_path.read_text())
import hashlib
for path in sorted(OUT.glob('*.py')):
    manifest[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, indent=2))
old = json.loads((OUT / 'baseline/simulation-results.json').read_text())
new = json.loads((audit.OUT / 'simulation-results.json').read_text())


def differences(before, after, path=''):
    if type(before) != type(after):
        return [{'path': path, 'before': before, 'after': after}]
    if isinstance(before, dict):
        results = []
        for key in sorted(before.keys() | after.keys()):
            if key not in before or key not in after:
                results.append({'path': path + '/' + key, 'before': before.get(key), 'after': after.get(key), 'key_changed': True})
            else:
                results.extend(differences(before[key], after[key], path + '/' + key))
        return results
    if isinstance(before, list):
        if len(before) != len(after):
            return [{'path': path, 'before': before, 'after': after, 'length_changed': True}]
        return [delta for i, (a, b) in enumerate(zip(before, after)) for delta in differences(a, b, f'{path}/{i}')]
    return [] if before == after else [{'path': path, 'before': before, 'after': after}]


changes = differences(old, new)
for item in changes:
    path = item['path']
    if path.startswith('/cases/'):
        row = new['cases'][int(path.split('/')[2])]
        item['family'], item['case'] = row['family'], row['case']
        item['reason'] = ('Approved duration normalization' if row['family'] == 'sleep score'
                          else 'Approved prior-seven-date Recovery window' if row['family'] == 'date joins'
                          else 'UNEXPLAINED formula delta')
    elif path.startswith('/findings/'):
        item['reason'] = 'Corrected regression probe and updated finding interpretation'
    elif '/computed_at' in path:
        item['reason'] = 'Demo computation clock metadata'
    elif path.startswith('/demo/api_demo/'):
        item['reason'] = ('Stress algorithm cache version' if '/algo_version' in path
                          else 'RHR rejection diagnostics' if '/rhr_rejected_count' in path
                          else 'Approved prior-date Recovery weighting' if '/api/recovery' in path
                          else 'Selected date/profile alignment and approved duration normalization')
    else:
        item['reason'] = 'UNEXPLAINED delta'
(OUT / 'simulation-deltas.json').write_text(json.dumps(changes, indent=2))
metadata = {'checks': len(audit.rows), 'passed': sum(r['passed'] for r in audit.rows),
            'failed': failures, 'runtime_s': time.perf_counter() - started,
            'delta_leaves': len(changes), 'delta_reasons': dict(Counter(d['reason'] for d in changes)),
            'unchanged_cases': sum(a == b for a, b in zip(old['cases'], new['cases']))}
(OUT / 'final-simulation-metadata.json').write_text(json.dumps(metadata, indent=2))
print(json.dumps(metadata))
sys.exit(int(bool(failures) or any(d['reason'].startswith('UNEXPLAINED') for d in changes)))
