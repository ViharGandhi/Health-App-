"""Preserve the audit state and rerun its checks without overwriting evidence."""
from pathlib import Path
import hashlib
import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'baseline'
if OUT.exists() and '--resume' not in sys.argv:
    raise SystemExit('Baseline already exists; refusing to overwrite')
OUT.mkdir(parents=True, exist_ok=True)
if not (OUT / 'audit-final').exists():
    shutil.copytree(ROOT / 'validation/followup/final', OUT / 'audit-final')
manifest = json.loads((OUT / 'audit-final/source-hashes.json').read_text())
changed = [name for name, digest in manifest.items()
           if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
if changed:
    raise SystemExit('Baseline sources changed; refusing to overwrite preserved evidence')
(OUT / 'source-drift.json').write_text(json.dumps(changed, indent=2))
results = {}
for name, target in [('backend', 'backend'), ('live-runner', 'validation/followup/test_live_script.py')]:
    if (OUT / (name + '.xml')).exists():
        import xml.etree.ElementTree as ET
        suites = ET.parse(OUT / (name + '.xml')).getroot().findall('testsuite')
        results[name] = {'exit_code': int(any(int(s.attrib[k]) for s in suites for k in ('failures', 'errors'))),
            'runtime_s': sum(float(s.attrib['time']) for s in suites)}
        continue
    started = time.perf_counter()
    result = subprocess.run([sys.executable, '-m', 'pytest', target, '-q', '-p', 'no:cacheprovider',
        '--junitxml=' + str(OUT / (name + '.xml'))], cwd=ROOT, capture_output=True, text=True, timeout=240)
    (OUT / (name + '.log')).write_text(result.stdout + result.stderr)
    results[name] = {'exit_code': result.returncode, 'runtime_s': time.perf_counter() - started}
    print(name, result.stdout[-1600:], flush=True)
spec = importlib.util.spec_from_file_location('audit', ROOT / 'validation/run_simulations.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
started = time.perf_counter()
audit.run()
audit.OUT = OUT / 'simulations'
audit.OUT.mkdir(exist_ok=True)
shutil.copyfile(OUT / 'backend.xml', audit.OUT / 'test-results.xml')
audit.write()
results['simulations'] = {'checks': len(audit.rows), 'passed': sum(r['passed'] for r in audit.rows),
    'runtime_s': time.perf_counter() - started}
spec = importlib.util.spec_from_file_location('evidence', ROOT / 'validation/followup/evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
evidence.OUT = OUT
evidence.curve()
evidence.replay()
asyncio.run(evidence.profiles())
evidence.constants()
results['source_hash_differences'] = changed
(OUT / 'metadata.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results), flush=True)
if any(r.get('exit_code', 0) for r in results.values() if isinstance(r, dict)):
    raise SystemExit(1)
