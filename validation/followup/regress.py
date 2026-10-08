"""Capture full-suite results without printing mocked or personal API payloads."""
from pathlib import Path
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'final'
OUT.mkdir(exist_ok=True)
started = time.perf_counter()
result = subprocess.run([sys.executable, '-m', 'pytest', 'backend', '-q', '-p', 'no:cacheprovider',
    '--junitxml=' + str(OUT / 'test-results.xml')], cwd=ROOT, capture_output=True, text=True)
(OUT / 'tests.log').write_text(result.stdout + result.stderr)
suites = ET.parse(OUT / 'test-results.xml').getroot().findall('testsuite')
metadata = {'runtime_s': time.perf_counter() - started, 'exit_code': result.returncode,
            **{key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}}
(OUT / 'test-metadata.json').write_text(json.dumps(metadata, indent=2))
print(result.stdout[-2400:])
print(json.dumps(metadata))
sys.exit(result.returncode)
