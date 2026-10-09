"""The pinned async stack must import TestClient without deprecated aliases."""
from pathlib import Path
import subprocess
import sys


def test_testclient_import_with_warnings_as_errors():
    result = subprocess.run([sys.executable, '-W', 'error::DeprecationWarning', '-c',
        'import starlette.testclient'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
