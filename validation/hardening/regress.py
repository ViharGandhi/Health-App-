"""Capture a bounded offline pytest run and retain all failures/warnings."""
from pathlib import Path
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
name = sys.argv[1]
targets = sys.argv[2:] or ['backend']
started = time.perf_counter()
result = subprocess.run([sys.executable, '-m', 'pytest', *targets, '-q', '--tb=short',
    '--junitxml=' + str(OUT / (name + '.xml'))], cwd=ROOT, capture_output=True, text=True, timeout=300)
(OUT / (name + '.log')).write_text(result.stdout + result.stderr)
report = OUT / (name + '.xml')
suites = ET.parse(report).getroot().findall('testsuite') if report.exists() else []
metadata = {'runtime_s': time.perf_counter() - started, 'exit_code': result.returncode,
    'junit_written': bool(suites),
    **{key: sum(int(s.attrib.get(key, 0)) for s in suites) if suites else None for key in ('tests', 'failures', 'errors', 'skipped')}}
(OUT / (name + '-metadata.json')).write_text(json.dumps(metadata, indent=2))
print(result.stdout[-3500:])
print(json.dumps(metadata))
sys.exit(result.returncode)
