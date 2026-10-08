"""Preserve audit artifacts and record an offline baseline without credentials."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
previous = OUT / 'previous'
if (OUT / 'baseline-metadata.json').exists():
    raise SystemExit('Baseline already recorded; refusing to overwrite pre-fix evidence.')
previous.mkdir(exist_ok=True)
for name in ('run_simulations.py','simulation-results.json','source-hashes.json','VALIDATION_REPORT.md'):
    shutil.copyfile(ROOT/'validation'/name, previous/name)
manifest = json.loads((previous/'source-hashes.json').read_text())
changes = []
for name, digest in manifest.items():
    path = ROOT / name
    raw = path.read_bytes() if path.exists() else b''
    if hashlib.sha256(raw).hexdigest() != digest:
        old = subprocess.run(['git','show',f'9304073:{name.replace(chr(92),chr(47))}'],cwd=ROOT,capture_output=True).stdout
        changes.append(dict(file=name,missing=not path.exists(),
                            differs_from_audit_branch_content=raw.replace(b'\r\n',b'\n')!=old.replace(b'\r\n',b'\n')))
(OUT/'source-drift.json').write_text(json.dumps(changes,indent=2))
started=time.perf_counter()
result=subprocess.run([sys.executable,'-m','pytest','backend','-q','-p','no:cacheprovider','--ignore=backend/test_stress_baseline_uniqueness.py',f'--junitxml={OUT / "baseline-tests.xml"}'],cwd=ROOT,capture_output=True,text=True)
(OUT/'baseline-tests.log').write_text(result.stdout+result.stderr)
metadata=dict(test_exit=result.returncode,test_runtime_s=time.perf_counter()-started)
sys.path[:0]=[str(ROOT/'validation'),str(ROOT/'backend'),str(ROOT)]
import run_simulations as audit
audit.OUT=OUT/'baseline'
audit.OUT.mkdir(exist_ok=True)
shutil.copyfile(OUT/'baseline-tests.xml',audit.OUT/'test-results.xml')
started=time.perf_counter()
audit.run();audit.write()
metadata.update(simulation_runtime_s=time.perf_counter()-started,checks=len(audit.rows),failed=sum(not r['passed'] for r in audit.rows))
(OUT/'baseline-metadata.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps(metadata))
sys.exit(result.returncode or int(metadata['failed']>0))
