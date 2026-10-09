"""Read-only verification of the current hardening evidence and source identity."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'final'
HARDENING = ROOT / 'validation/hardening'


def main():
    manifest = json.loads((OUT / 'source-hashes.json').read_text())
    for name, digest in manifest.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    for report in (OUT / 'VALIDATION_REPORT.md', OUT / 'FORMULAS_AND_RESULTS.md',
                   OUT / 'constants-inventory.md', HARDENING / 'REPORT.md', HARDENING / 'DECISIONS.md',
                   OUT.parent / 'REPORT.md', OUT.parent / 'LIVE_README.md'):
        for target in re.findall(r'\]\(([^)]+)\)', report.read_text(encoding='utf-8')):
            if not target.startswith(('https:', '#')):
                assert (report.parent / target.split('#')[0]).exists(), (report.name, target)
    results = json.loads((OUT / 'simulation-results.json').read_text())
    assert len(results['cases']) == 1295 and all(row['passed'] for row in results['cases'])
    metadata = json.loads((OUT / 'test-metadata.json').read_text())
    suites = ET.parse(OUT / 'test-results.xml').getroot().findall('testsuite')
    for key in ('tests', 'failures', 'errors', 'skipped'):
        assert sum(int(s.attrib.get(key, 0)) for s in suites) == metadata[key], key
    assert metadata['exit_code'] == metadata['failures'] == metadata['errors'] == metadata['skipped'] == 0
    assert not re.search(r'\b\d+ warnings?\b|warnings summary', (OUT / 'tests.log').read_text(), re.I)
    changes = json.loads((OUT / 'audit-deltas.json').read_text())
    assert not any(d['reason'].startswith('UNEXPLAINED') for d in changes)
    assert not any(d['path'].startswith('/cases/') for d in changes)
    profiles = json.loads((OUT / 'adversarial-profiles.json').read_text())
    assert len(profiles) == len({p['profile'] for p in profiles}) == 9
    for profile in profiles:
        assert profile['five_fix_probes']['stress_unique_nights'] == 1
        assert profile['hardening_probes']['missing_anchor_withheld_reason'] == 'hrv_anchor_unconfigured'
    replay = json.loads((OUT / 'demo-replay.json').read_text())
    assert len(replay['routes']) == 19 and all(r['status'] == 200 for r in replay['routes'].values())
    coverage = json.loads((OUT / 'fuzz-coverage.json').read_text())
    assert all(r['passing_examples'] >= 200 and r['failing_examples'] == 0 for r in coverage['batches'])
    assert json.loads((HARDENING / 'baseline/source-drift.json').read_text()) == []
    print(json.dumps(dict(source_hashes_verified=len(manifest), relative_evidence_links='verified',
        simulation_checks=1295, junit_cases=metadata['tests'], explained_delta_leaves=len(changes),
        profiles=9, property_batches=len(coverage['batches']), passing_property_examples=coverage['passing_examples'],
        verification_writes='none')))


if __name__ == '__main__':
    main()
