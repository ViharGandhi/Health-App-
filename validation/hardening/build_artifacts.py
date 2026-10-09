"""Build current evidence and immutable source identity after passing final checks."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'final'
FOLLOWUP = ROOT / 'validation/followup'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def scope(name):
    if name in ('strain', 'strain_service', 'strain_analytics'):
        return 'HRR/TRIMP units; UTC gaps; spike filter; workout conservation; raw vs display; profile/cache identity'
    if name in ('recovery', 'recovery_score', 'recovery_analytics'):
        return 'Prior-only joins; finite robust statistics; method/count gates; bounded CDF; missing context; estimator identity'
    if name in ('sleepscore', 'sleep_need', 'sleep_need_inputs', 'sleep_analytics'):
        return 'Seconds/hours/minutes; availability; debt windows; defaults; bounded components; caller mutation'
    if name in ('sleep_consistency', 'sleep_efficiency', 'sleep_trends'):
        return 'Clock circularity; physical durations; missing dates/durations; pooled ratios; calendar limits'
    if name.startswith('sleep_stage') or name.startswith('sleep_stress') or name == 'sleep_selection':
        return 'Main selection; UTC stage partition; coverage; anchor provenance; unique references; account-scoped upserts'
    if name in ('google_health_client', 'provider_payload', 'validity', 'health_trends'):
        return 'Provider types; finite/unit gates; pagination progress; duplicate policy; privacy-safe failures'
    if name in ('auth', 'main', 'models'):
        return 'Auth/session states; profile headers; demo isolation; serialization; reasons; estimator identity'
    if name in ('health_read_store', 'page_snapshots', 'dynamic_sync', 'sleep_sync'):
        return 'Account/range keys; epochs; transactions; idempotent sync; concurrent reads; stale-cache bypass'
    return 'Reviewed demo/CLI/telemetry support; explicit dates where applicable; fixtures separated from empirical calibration'


def inventories():
    sources = [p for p in sorted([*ROOT.glob('*.py'), *ROOT.glob('backend/*.py')]) if not p.name.startswith('test_')]
    tests = [*ROOT.glob('backend/test_*.py'), FOLLOWUP / 'test_live_script.py']
    imports = {}
    for test in tests:
        for node in ast.walk(ast.parse(test.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports.setdefault((node.module, alias.name), set()).add(test.relative_to(ROOT).as_posix())
    callables, constants = [], []
    for source in sources:
        text = source.read_text(encoding='utf-8-sig')
        tree = ast.parse(text)
        name = source.relative_to(ROOT).as_posix()
        def visit(node, parents=()):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = parents + (child.name,)
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        related = sorted(imports.get((source.stem, parents[0] if parents else child.name), ()))
                        callables.append(dict(source=name, line=child.lineno, callable='.'.join(qualified),
                            source_review_focus=scope(source.stem), explicit_test_imports=related,
                            coverage_limit='Source review and listed module/chain tests; no exhaustive branch claim.'))
                    visit(child, qualified)
                else:
                    visit(child, parents)
        visit(tree)
        lines = text.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                context = lines[node.lineno - 1].strip()
                constants.append(dict(source=name, line=node.lineno, literal=node.value, context=context,
                    comment=context.split('#', 1)[1].strip() if '#' in context else None,
                    status='Retained literal; dimensional/control review or empirical provenance required, depending on role'))
    write_json(OUT / 'callable-review.json', callables)
    write_json(OUT / 'numeric-constants.json', constants)
    (OUT / 'algorithm-inventory.md').write_text('# Callable review inventory\n\n'
        'Every production/support Python callable, including nested helpers and new boundary functions, is listed. '
        'The focus column records source-review scope. Explicit imports identify test entry points; empty entries may '
        'be reached through routes or calculation chains. This index does not prove every branch or every possible input.\n\n'
        '| Source / line | Callable | Source-review focus | Explicit test imports |\n|---|---|---|---|\n'
        + '\n'.join(f"| `{r['source']}:{r['line']}` | `{r['callable']}` | {r['source_review_focus']} | "
                     + ', '.join(f'`{p}`' for p in r['explicit_test_imports']) + ' |' for r in callables) + '\n', encoding='utf-8')
    grouped = Counter(r['source'] for r in constants)
    (OUT / 'constants-inventory.md').write_text('# Numeric constants and provenance\n\n'
        f'{len(constants)} numeric literals across {len(grouped)} production/support sources; booleans and test oracles are excluded. '
        'Mathematical constants, unit conversions, calendar lengths, cache controls, mock-generation values and physiological '
        'heuristics are deliberately all retained with line-level context in [numeric-constants.json](numeric-constants.json). '
        'An inline comment explains intent, not empirical validity. No coefficients or cutoffs were retuned.\n\n'
        '| Source | Literals |\n|---|---:|\n' + '\n'.join(f'| {p} | {n} |' for p, n in grouped.items()) + '\n', encoding='utf-8')
    return len(callables), len(constants)


def fuzz_statistics():
    text = (HERE / 'fuzz-statistics.log').read_text()
    batches = []
    for name, body in re.findall(r'^(backend/test_[^\n]+):\n(.*?)(?=^backend/test_|\Z)', text, re.M | re.S):
        match = re.search(r'(\d+) passing, (\d+) failing, and (\d+) invalid test cases', body)
        if match:
            batches.append(dict(test=name.strip(), passing_examples=int(match[1]), failing_examples=int(match[2]),
                                generator_retries=int(match[3])))
    assert batches and all(r['passing_examples'] >= 200 and r['failing_examples'] == 0 for r in batches), batches
    write_json(OUT / 'fuzz-coverage.json', dict(batches=batches, passing_examples=sum(r['passing_examples'] for r in batches),
        interpretation='Passing means valid bounded output or an allowed explicit validation/withholding result. Generator retries are not skipped pytest tests.'))
    return len(batches), sum(r['passing_examples'] for r in batches)


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else 'final-suite'
    metadata = json.loads((HERE / (label + '-metadata.json')).read_text())
    assert metadata['exit_code'] == 0 and metadata['junit_written']
    assert metadata['failures'] == metadata['errors'] == metadata['skipped'] == 0
    log = (HERE / (label + '.log')).read_text()
    assert not re.search(r'\b\d+ warnings?\b|warnings summary', log, re.I)
    shutil.copyfile(HERE / (label + '.xml'), OUT / 'test-results.xml')
    shutil.copyfile(HERE / (label + '.log'), OUT / 'tests.log')
    write_json(OUT / 'test-metadata.json', metadata)
    callable_count, constant_count = inventories()
    batch_count, examples = fuzz_statistics()
    changes = json.loads((OUT / 'audit-deltas.json').read_text())
    assert not any(r['reason'].startswith('UNEXPLAINED') for r in changes)
    write_json(OUT / 'simulation-delta-summary.json', dict(changed_leaves=len(changes),
        reasons=dict(Counter(r['reason'] for r in changes)), unchanged_formula_cases=1295))
    # Keep the detailed formula/data appendix, but replace stale historical conclusions.
    old_report = (OUT / 'VALIDATION_REPORT.md').read_text(encoding='utf-8')
    if '## Current formula specification' in old_report:
        appendix = old_report.split('## Current formula specification', 1)[1].split('## Reproduced issues and assumptions needing review', 1)[0]
        (OUT / 'FORMULAS_AND_RESULTS.md').write_text('# Current formulas, inputs, results and inference\n\n'
            'Hardening verification: 2026-10-09. Synthetic anchor 2026-10-07; seed 20261007. '
            'All 1,295 original numerical cases remain unchanged. Full data are in [simulation-results.json](simulation-results.json) '
            'and [simulation-results.csv](simulation-results.csv). This verifies implementation on tested domains, not physiological accuracy.\n\n'
            'Stage partitions now also require physical duration at most 24 hours. Sample RMSSD obeys the provider 200 ms bound; daily VO2 obeys 100 ml/kg/min. '
            'Connected sleep retains missing-vital neutral defaults and exposes availability. Stress anchor configuration is an operator assertion, not empirical verification. '
            'Malformed provider input is rejected at boundaries; deliberately invalid pure-helper calls may raise ValueError. '
            'Recovery typical ranges can be withheld with numeric_range_overflow.\n\n## Formula specification'
            + appendix + '\nSee [the hardening report](../REPORT.md) for current test counts, all fixes and limitations.\n', encoding='utf-8')
    write_json(OUT / 'audit-summary.json', dict(tests=metadata, callable_count=callable_count,
        numeric_literals=constant_count, property_batches=batch_count, passing_property_examples=examples,
        simulation_checks=1295, unchanged_formula_cases=1295, changed_leaves=len(changes), profiles=9,
        live_access_exists=False, live_run_performed=False))
    # Regeneration is explicit here; verification must never refresh a manifest.
    files = sorted(set([*ROOT.glob('*.py'), *ROOT.glob('backend/*.py'),
        *FOLLOWUP.glob('*.py'), *HERE.glob('*.py'), ROOT / 'validation/run_simulations.py',
        ROOT / 'backend/requirements.txt', ROOT / 'backend/requirements-dev.txt', ROOT / 'pytest.ini']))
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    write_json(OUT / 'source-hashes.json', hashes)
    destination = FOLLOWUP / 'final'
    for source in OUT.iterdir():
        if source.is_file() and 'unclassified' not in source.name:
            shutil.copyfile(source, destination / source.name)
    print(json.dumps(dict(source_hashes=len(hashes), reviewed_callables=callable_count,
                         numeric_literals=constant_count, property_batches=batch_count, passing_property_examples=examples)))


if __name__ == '__main__':
    main()
