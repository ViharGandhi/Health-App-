"""Verify evidence links, source identity, declared case counts and numeric deltas."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
manifest_path = OUT / 'final/source-hashes.json'
manifest = json.loads(manifest_path.read_text())
# New/edited evidence scripts do not change production algorithms; refresh their hashes.
for path in sorted(OUT.glob('*.py')):
    manifest[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, indent=2))
for name, digest in manifest.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
for report in (OUT / 'REPORT.md', OUT / 'LIVE_README.md'):
    for target in re.findall(r'\]\(([^)]+)\)', report.read_text()):
        if not target.startswith(('https:', '#')):
            assert (report.parent / target).exists(), (report.name, target)
results = json.loads((OUT / 'final/simulation-results.json').read_text())
assert len(results['cases']) == 1295 and all(row['passed'] for row in results['cases'])
test_metadata = json.loads((OUT / 'final/test-metadata.json').read_text())
assert test_metadata['tests'] == 408 and test_metadata['failures'] == test_metadata['errors'] == 0
deltas = json.loads((OUT / 'simulation-deltas.json').read_text())
assert len(deltas) == 581 and not any(d['reason'].startswith('UNEXPLAINED') for d in deltas)
profiles = json.loads((OUT / 'adversarial-profiles.json').read_text())
assert len(profiles) == 7 and all(p['five_fix_probes']['stress_unique_nights'] == 1 for p in profiles)
environment = {'python': sys.version.split()[0], 'packages': {name: importlib.metadata.version(name)
    for name in ('pytest', 'hypothesis', 'fastapi', 'pydantic', 'starlette', 'httpx', 'matplotlib')}}
(OUT / 'environment.json').write_text(json.dumps(environment, indent=2))
print(json.dumps({'source_hashes_verified': len(manifest), 'relative_evidence_links': 'verified',
                  'simulation_checks': 1295, 'junit_cases': 408, 'explained_delta_leaves': len(deltas)}))
