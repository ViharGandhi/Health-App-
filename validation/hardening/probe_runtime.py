"""Bounded runtime probe, with no tokens/health data, for Windows asyncio stalls."""
from pathlib import Path
import subprocess
import sys
import time

started = time.perf_counter()
result = subprocess.run([sys.executable, '-c',
    'import asyncio,faulthandler,socket; faulthandler.dump_traceback_later(3,exit=True); '
    'print("socketpair", flush=True); a,b=socket.socketpair(); print(a.family,flush=True); a.close(); b.close(); '
    'print(asyncio.run(asyncio.to_thread(lambda: 1)),flush=True)'],
    capture_output=True, text=True, timeout=8)
label = sys.argv[1]
output = f'exit_code={result.returncode}; runtime_s={time.perf_counter()-started:.3f}\n' + result.stdout + result.stderr
(Path(__file__).parent / ('runtime-' + label + '.log')).write_text(output)
print(output)
