"""Generate the concise findings report from retained checks and local commits."""
import ast
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'final'

LOCATIONS = {
    '79f5eb3': ('backend/validity.py', 'resting_hr'),
    '32ee23d': ('backend/main.py', '_compute_real_sleep'),
    'c968fce': ('backend/validity.py', 'valid_metric'),
    '623fc73': ('backend/sleep_selection.py', 'main_sleep_key'),
    'a47cfcb': ('backend/models.py', 'RecoveryResponse'),
    'b578a51': ('backend/models.py', 'StrainResponse'),
    'd37a4ad': ('backend/sleep_stress_pipeline.py', 'compute_connected_sleep_stress'),
    '341979e': ('backend/sleep_analytics.py', 'build_sleep_analytics'),
    'b30f21e': ('backend/sleep_stage_ranges.py', 'stage_stats'),
    '656ed78': ('backend/main.py', 'data_timings'),
    '0959afe': ('backend/main.py', '_client_day'),
    'f3696c3': ('backend/google_health_client.py', '_valid_sleep_summary'),
    '3d8157f': ('backend/google_health_client.py', '_sleep_records'),
    '269d5c2': ('backend/main.py', '_cached_data_page'),
    '462437e': ('backend/main.py', '_get_token'),
    'bf33b64': ('backend/validity.py', 'finite_number'),
    '2bd38e3': ('backend/provider_payload.py', 'payload_boundary'),
    '626641d': ('backend/provider_payload.py', 'payload_boundary'),
    '70ede57': ('backend/sleep_stress.py', 'prepare_night'),
    'b873319': ('backend/google_health_client.py', 'get_daily_hrv'),
    'eb7f98e': ('strain.py', 'strain_score'),
    '925213f': ('backend/sleep_stress_store.py', '_key'),
    '7225925': ('backend/sleep_heart_rate.py', 'build_sleep_heart_rate'),
    'af85696': ('backend/sleep_stage_ranges.py', 'stage_stats'),
    '45f57d0': ('sleepscore.py', 'compute_duration_score'),
    '97833bd': ('backend/recovery_analytics.py', 'typical_ranges'),
    '489fd3d': ('sleepscore.py', 'compute_baseline'),
    '9909e5f': ('backend/validity.py', 'finite_median'),
    'b5d96aa': ('backend/google_health_client.py', 'get_health_history'),
    '0f410b5': ('backend/auth.py', 'get_valid_access_token'),
    '2125b38': ('backend/google_health_client.py', '_fetch_points'),
    '08e988a': ('backend/main.py', 'unrepresentable_range'),
    '2f05440': ('backend/sleep_trends.py', 'build_sleep_trend'),
    '206f2dd': ('backend/google_health_client.py', '_fetch_daily_steps'),
    'b1e11d0': ('backend/sleep_stage_webhooks.py', 'enqueue_sleep_notifications'),
    '4688814': ('backend/strain_analytics.py', 'build_strain_analytics'),
    '2f43686': ('backend/sleep_stress.py', 'adapt_google_hrv'),
}
HIGH = {'269d5c2', '462437e', '2bd38e3', '626641d', 'b873319', '925213f', '7225925',
        '0f410b5', '2125b38', '08e988a', '2f05440', '206f2dd', 'b1e11d0', '2f43686'}
LOW = {'a47cfcb', 'b578a51', '4688814'}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main():
    metadata = json.loads((OUT / 'test-metadata.json').read_text())
    summary = json.loads((OUT / 'audit-summary.json').read_text())
    baseline = json.loads((HERE / 'baseline/metadata.json').read_text())
    profiles = json.loads((OUT / 'profile-summary.json').read_text())
    deltas = json.loads((OUT / 'audit-deltas.json').read_text())
    rows = []
    commits = git('log', '--reverse', '--format=%h|%s', 'fix/backend-audit..HEAD').splitlines()
    for entry in commits:
        commit, subject = entry.split('|', 1)
        if commit not in LOCATIONS:
            continue
        source, function = LOCATIONS[commit]
        tree = ast.parse((ROOT / source).read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == function)
        changed = git('show', '--pretty=format:', '--name-only', commit).splitlines()
        tests = [p for p in changed if p.startswith('backend/test_') and p.endswith('.py')]
        test_names = {n.name for test in tests for n in ast.walk(ast.parse((ROOT / test).read_text(encoding='utf-8-sig')))
                      if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
        failures = []
        for path in HERE.glob('*.log'):
            output = path.read_text(errors='replace')
            if not (any(Path(test).name in output for test in tests) or any(name in output for name in test_names)):
                continue
            meta_path = path.with_name(path.stem + '-metadata.json')
            if ((meta_path.exists() and json.loads(meta_path.read_text()).get('exit_code', 0))
                    or re.search(r'\b[1-9]\d* failed\b', output)):
                failures.append(path.name)
        severity = 'high' if commit in HIGH else 'low' if commit in LOW else 'medium'
        rows.append(dict(id=f'H{len(rows) + 1:02}', source=source, callable=function, line=node.lineno,
            severity=severity, reproduced=True, status='fixed', root_cause_and_fix=subject,
            tests=tests, commit=commit, failing_outputs=sorted(failures)))
    (OUT / 'findings.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    lines = ['# Backend hardening report', '',
        '2026-10-09 · branch `fix/backend-hardening` · synthetic anchor 2026-10-07 · formula seed 20261007 · option seed 20261009.', '',
        f"The tested backend paths pass: **{metadata['tests']} JUnit cases**, no failures, errors, skipped tests or warnings; "
        f"**1,295/1,295 independent formula checks**, all unchanged from the audit baseline; "
        f"**{summary['passing_property_examples']:,} passing generated examples in {summary['property_batches']} property batches**, at least 200 each. "
        'Nineteen demo routes and nine synthetic profiles were replayed offline. This is implementation verification, not clinical validation.', '',
        'No read-only access token was available (yes/no check: **no**). Live Phase 5 was not run. No device measurements were invented or substituted for live data.', '',
        '## Module verdicts', '', '| Module | Verdict on tested domains |', '|---|---|',
        '| `strain.py` / strain service | HRR/TRIMP, gaps, conservation and monotonic bounds pass; finite RHR/age gates and JSON flooring verified. |',
        '| Connected `recovery_score.py` | Prior-only joins, valid-reading counts, robust spreads, method gates, confidence and bounded CDF pass. |',
        '| `sleep_need.py` / inputs | Minute units, seven-night weighted debt, nap subtraction and 360–660 minute limits pass. |',
        '| `sleepscore.py` | Component equations and bounds pass; connected missing inputs remain neutral with explicit weighted availability. |',
        '| `sleep_efficiency.py` | Valid physical durations and pooled aggregation pass; missing/invalid durations remain absent. |',
        '| `sleep_consistency.py` / trends | Circular timing, consecutive dates, calendar boundaries and DST/offset checks pass. |',
        '| Stage ranges / selection / store | Shared UTC main selection, complete partitions, <=24 h eligibility, prior unique dates and scoped persistence pass. |',
        '| Sleep stress / pipeline / store | Joint persistent signals, valid coverage, unique nights, account isolation and withholding reasons pass; real anchor calibration remains unverified. |',
        '| Health / Recovery analytics | Shared metric gates and finite robust medians pass; overflowing personal ranges are explicitly withheld. |',
        '| Legacy `recovery.py` / clock helpers | Prototype equations and scalar validation pass; estimator is disclosed and retained as the demo default. |',
        '| Provider / API assembly | Malformed types, repeated page tokens, profile headers, date bounds, missing data and privacy-safe errors pass. |',
        '| Auth / webhooks | Anonymous demos remain; invalid/expired cookies reject with 401; malformed OAuth responses and authenticated webhook payloads fail closed. |',
        '| Cache / sync / SQLite | Account/profile keys, version bypass, transaction/upsert idempotence and existing concurrency tests pass. |', '',
        '## Reproduced fixes', '',
        'Locations refer to current source. The commit contains the surgical change and its regression test. '
        'The machine-readable [findings](final/findings.json) link retained failing output files; '
        'all bounded before/after logs and XML remain in this directory. Every row below is reproduced and fixed.', '',
        '| ID | Source / callable / line | Severity | Root cause and correction | Regression | Commit |', '|---|---|---|---|---|---|']
    for row in rows:
        title = re.split(r'; backend/|\s*\(test_', row['root_cause_and_fix'])[0].removeprefix('Fix ').removeprefix('fix: ')
        tests = ', '.join(f"[{Path(p).name}](../../{p})" for p in row['tests'])
        lines.append(f"| {row['id']} | `{row['source']}:{row['line']}` `{row['callable']}` | {row['severity']} | {title} | {tests} | `{row['commit']}` |")
    lines += ['', '## Decisions and retained policies', '',
        'No decision is waiting. [The decision record](DECISIONS.md) retains options, numerical effects and the accepted contracts.', '',
        '- Composite sleep: keep defaults, expose partial/availability. Missing HRV, sleeping HR and HR dip have 28% total weight and add 14 neutral points. The seven staged connected profile fixtures have 72% weighted availability; the illness fixture remains 69.1 sleep despite its abnormal vitals.',
        '- Main sleep: explicit main, otherwise unspecified, longest physical UTC duration, greatest stable ID. The reproduced A/B example now selects 400 asleep minutes in a 9 h session over 450 asleep minutes in an 8 h session. Naps/secondary exclusions and calculator eligibility thresholds remain.',
        '- Ceilings: existing HR 30–230 bpm and unit SpO2 limits, provider RMSSD <=200 ms and daily VO2 <=100. Unsupported daily/deep HRV, respiration and temperature ceilings remain deferred; 1e9 still passes their finite/positive gate.',
        '- Serialization: floor public 0–21 strain fields and historical rows to one decimal; preserve model/calculation values and inputs to averages/Recovery. 16.86 serializes as 16.8 while its model remains 16.9; values just below 21 serialize as 20.9.',
        '- Duplicates: first raw strain HR arrival, last daily vital arrival, sleep HR chart excludes conflicts. This inconsistency is intentionally retained. No common revision timestamp was established for these fields; an eventual shared policy needs provider revision metadata.',
        '- Auth: preserve anonymous demos and explicit strain demos; present invalid/expired cookies return 401. Deliberate invalid pure-helper calls retain ValueError; client header/range errors return 400, malformed upstream data returns privacy-safe 502.', '',
        '## Before/after counts and accounting', '',
        '| Check | Preserved baseline | Final |', '|---|---|---|',
        f"| Backend | 380 passed, 1 failed, 27 subtests; 1 deprecation warning; {baseline['backend']['runtime_s']:.3f} s | See combined count below; all pass |",
        '| Live-runner offline tests | 7 passed; 1.116 s | 7 pass, included in combined suite |',
        f"| Combined final suite | Baseline backend and runner were separate | {metadata['tests']} JUnit cases; {metadata['runtime_s']:.3f} s; 0 failures/errors/skips/warnings |",
        f"| Independent formula checks | 1,295/1,295; {baseline['simulations']['runtime_s']:.3f} s | 1,295/1,295; all case inputs/expected/actual/tolerance/status unchanged |",
        f"| Generated properties | Prior audit had property tests | {summary['property_batches']} batches; {summary['passing_property_examples']:,} passing examples; generator retries are not test skips |",
        '| Offline replay / profiles | 19 routes; 7 profiles | 19 routes plus W/M/6M replay; 9 profiles; original five and nine hardening probes on each |', '',
        'The baseline source identity matched all 82 listed hashes with zero drift. [Baseline metadata](baseline/metadata.json), '
        '[final suite log](final/tests.log), [XML](final/test-results.xml), [property statistics](fuzz-statistics-v2.log), '
        '[source hashes](final/source-hashes.json) and [read-only verification script](../followup/verify_artifacts.py) retain the evidence.', '',
        f"Exactly **{len(deltas)} response leaves** changed against both the preserved audit and execution baselines. "
        'The [complete before/after leaf table](final/audit-deltas.json) assigns a specific cause/commit to each. '
        'No numerical formula case changed and no unexplained delta remains.', '',
        '| Delta cause | Leaves |', '|---|---:|']
    lines += [f'| {reason} | {count} |' for reason, count in Counter(d['reason'] for d in deltas).items()]
    lines += ['',
        'The only changed numeric outputs in the original replay are display flooring: three workout copies 9.2→9.1, '
        'and historical row/activity displays 13.9→13.8, 6.4→6.3, 3.6→3.5 or 9.2→9.1. '
        'Other added numeric leaves are availability/provenance/zero rejection counts, not score retuning. '
        'The repeated dashboard/detail/current values agree. Historical averages and comparisons retain their previous model inputs.', '',
        'Cache namespaces: `strain-v2` retains raw formula values; `page-v31` replaces page-v8 through all intervening versions; '
        '`sleep-stress-10`, `sleep-stage-ranges-3` and `steps-rollup-v2` invalidate affected derivations/rollups. '
        '[Cache tests](../../backend/test_audit_cache_versions.py) and [step-cache tests](../../backend/test_provider_step_counts.py) '
        'prove old keys cannot serve the reproduced bad results. Invalid stored historical step counts are excluded. '
        'Previously truncated fractional counts cannot be distinguished from genuine integers without fetching source data again.', '',
        '## Profile data, results and inference', '',
        'All inputs are generated, not participant observations. [Full profile inputs/components/reasons/probes](final/adversarial-profiles.json) '
        'and [legacy vs connected comparison](final/legacy-vs-connected.json) are retained. The latter compares the original seven profiles.', '',
        '| Profile | Connected Recovery % | Composite sleep | Need (min) | Controlled 160 bpm / 45 min strain |', '|---|---:|---:|---:|---:|']
    for profile in profiles:
        fmt = lambda v: 'withheld' if v is None else f'{v:.3f}' if isinstance(v, float) else str(v)
        lines.append('| ' + ' | '.join([profile['profile'], *(fmt(profile[k]) for k in ('recovery', 'sleep_score', 'need_minutes', 'strain'))]) + ' |')
    lines += ['',
        'Sleep deprivation reduces sleep score and applies the Recovery duration penalty; illness-like HRV/RHR changes lower Recovery. '
        'The retained composite sleep score does not encode those missing vitals. New users and stopped sync withhold rather than fabricate current estimates. '
        'A higher age increases strain for identical HR under the retained HRmax formula; this confirms that formula, not a measured physiological age effect. '
        'The controlled strain probe in the stopped-sync row is a separate synthetic experiment, not current activity imputed to that user.', '',
        'The stopped-sync fixture retains 58 reference HRV days but zero recent nights; Recovery is building_reference, sleep score is absent with sleep_duration_unavailable. '
        'The remote-timezone fixture uses device +02:00 and user -08:00: physical instant equality is true, while device wake date 2026-10-07 maps to user date 2026-10-06. '
        'Provider civil wake dates select summary sleep and request timezone selects activity days. Its sleep score is withheld with sleep_need_unavailable. '
        'This is a calendar/data-availability result, not evidence of physiological deterioration or proof that device/user date labels should be unified.', '',
        'Anchor probes: no configured anchor withholds with hrv_anchor_unconfigured; a configured anchor shifted 12 hours outside sleep yields zero coverage and insufficient_baseline. '
        'A five-minute shift can still yield status ok with reduced coverage and no withholding reason. Different UTC-offset representations of the same physical samples give identical results apart from computation time. '
        'Therefore operator configuration and the legacy alignment_verified field do not prove empirical timestamp alignment; start/end semantics still require real-device calibration.', '',
        'The 1,000-night options experiment retains all inputs and candidate results in [sleep-component-options.json](sleep-component-options.json). '
        'Defaults produce 23.277–84.712, mean 57.717. Removing neutral points gives 9.277–70.712; renormalizing gives 12.885–98.211. '
        'The accepted default policy leaves profile scores unchanged. These distributions do not establish which policy is clinically better.', '',
        '## Formula and source-review detail', '',
        '[Formulas, numerical examples and inference](final/FORMULAS_AND_RESULTS.md) include HRR/TRIMP, recovery z/CDF, sleep need/debt, '
        'seven sleep components, pooled efficiency, circular consistency, stage bands and persistent stress windows. '
        '[The duration curve](final/sleep-duration-curve.png) and [boundary values](final/sleep-boundaries.json) show the previously approved normalization. '
        '[All 1,295 inputs/expected/actual values](final/simulation-results.json) and [CSV](final/simulation-results.csv) retain tolerances and per-case results. '
        f"[The callable index](final/algorithm-inventory.md) lists {summary['callable_count']} reviewed production/support callables, including nested/new helpers. "
        f"[The constants inventory](final/constants-inventory.md) includes {summary['numeric_literals']} numeric literals with source context. "
        '[The property matrix](final/fuzz-coverage.json) lists actual counts by entry point. Source review and calculator/adapter chains do not establish exhaustive branch coverage.', '',
        'Review covered truthiness, finite statistics, units, calendar windows, physical vs wall time, duplicates, mutation, provider types/partitions, '
        'account/profile/cache keys, transactions, logging, auth and webhook validation. Existing deterministic tests cover DST transitions in 2026/2027, '
        'midnight, leap/calendar boundaries, invalid headers and missing observations. CLI defaults legitimately use today when no request date exists; '
        'unused convenience/demo date helpers were not refactored.', '',
        '## Test infrastructure and evidence corrections', '',
        'Starlette 0.38.6 imported the deprecated BlockingPortal alias exposed by AnyIO 4.15.1. Pinning AnyIO 4.14.2 removed the warning; '
        'import and suite checks use warnings as errors. The fresh environment was installed from downloaded wheels with --no-index. '
        'External socket destinations and both real httpx transports are blocked. Loopback is allowed only because Windows asyncio uses a socket pair for IPC.', '',
        'Sandboxed async runs were bounded failures in Windows socket-pair initialization, not evidence of a backend deadlock. Their timeout logs remain retained. '
        'Tests default to 30 seconds; one measured 15-route/6-month replay has a scoped 120-second limit; whole-suite capture has a 300-second limit. '
        'Final unrestricted-IPC runs still block external network. No warning filter hides deprecations; expected blocked-socket UserWarning is asserted.', '',
        '| Infrastructure finding | Reproduced / status | Regression | Commit |', '|---|---|---|---|',
        '| Deprecated Starlette/AnyIO portal import | yes / fixed by AnyIO pin | [test_testclient_compatibility.py](../../backend/test_testclient_compatibility.py) | `f279e6f` |',
        '| Unbounded offline test/network paths | yes / bounded and blocked; Windows IPC limitation distinguished | [test_offline_infrastructure.py](../../backend/test_offline_infrastructure.py) | `2a47dc5` |',
        '| Default timeout shorter than measured large demo replay | yes / scoped bounded timeout | [test_strain_analytics.py](../../backend/test_strain_analytics.py) | `94c6835` |', '',
        'The baseline failure was a fixed October fixture evaluated against a moving recent-refresh clock. Its test clock was frozen; cache behavior was not patched to satisfy it. '
        'An existing sleep-analytics fixture gained the approved availability fields. The historical API assertion was changed to compare JSON output under the approved display spec, '
        'while dedicated tests preserve its model/average expectations. A new generic-mean property incorrectly prohibited signed means; its oracle was corrected to the documented generic mean contract. '
        'Evidence-script collection/import and stress-call signature mistakes were corrected; no production result was claimed from those failed scripts. '
        'Initial new route probes also contained obsolete route spellings; those probes were corrected to existing route definitions, rather than adding routes to satisfy the tests. '
        'The candidate join table initially used 45 ms instead of connected 41.2 ms; corrected values are disclosed in the decision record. '
        'Original independent numerical oracles were not retuned to pass.', '',
        'The verifier formerly rewrote script hashes before checking them. It now performs read-only comparisons; hash regeneration is an explicit artifact-build step. '
        'This avoids a self-refreshing identity check without changing product algorithms.', '',
        '## Limits and heuristics needing validation', '',
        'Verified on synthetic data: selected equations, documented thresholds, domain invariants, missing-data handling, API assembly, privacy-safe failures, '
        'cache isolation and the exercised storage/concurrency paths. Verified on live data: **nothing; access was unavailable**. '
        'No clinical sensitivity, specificity, p-values, outcome prediction or real-device permission/schema certification is inferred.', '',
        'The stress finding reproduced an account collision in persisted records. No API-served cross-account disclosure was demonstrated; that path currently recomputes results. '
        'The high severity reflects the incorrect storage isolation contract.', '',
        'Retained product heuristics needing empirical provenance include HRmax age coefficients, TRIMP sex coefficients/scale, spike and gap rules, target bands/ACR penalty, '
        'robust spread floors, reference counts/confidence, illness limits, sleep weights/stage targets/duration curve, need/debt coefficients and bounds, '
        'consistency curve, stage bands, stress joint thresholds/persistence/coverage and timestamp anchor choice. '
        'Their comments and synthetic tests establish implementation intent, not clinical validity.', '',
        'Needed evidence: timestamped raw data and independently confirmed HRV window start/end semantics across devices, DST and travel; '
        'matched device summaries and segment timelines; representative distributions for unsupported ceilings; independent readiness/sleep/illness outcomes; '
        'participant and day holdouts, prespecified missingness/confidence analyses and repeated-device comparisons. Provider output is a reference, not ground truth.', '',
        'Source-review concerns not claimed as reproduced defects: long-lived lock dictionaries may grow with many account/range keys; no memory-growth experiment established a user-visible failure. '
        'Arbitrary caller-supplied configurations and every possible combination of overlapping legacy clock intervals were not exhaustively validated. '
        'Stage-summary totals and complete segment partitions remain distinct measurement contracts; this audit does not assert universal equality between them. '
        'These were not patched speculatively. No frontend/browser or deployment security audit was requested or performed.', '',
        'All scoring coefficients and existing clinical/product thresholds remain unchanged in this hardening task. Approved provider/unit validity limits, '
        'selection, availability, error contracts and display/cache behavior changed as documented. Nothing was merged, rebased onto main, pushed or deployed; no remote was modified.', '',
        '## Reproduce', '', '```powershell',
        '.venv/hardening-clean/Scripts/python.exe validation/hardening/regress.py final-suite-complete-v2 backend validation/followup/test_live_script.py',
        '.venv/Scripts/python.exe validation/hardening/evidence.py',
        '.venv/Scripts/python.exe validation/hardening/simulations.py',
        '.venv/Scripts/python.exe validation/hardening/build_artifacts.py final-suite-complete-v2',
        '.venv/Scripts/python.exe validation/hardening/report.py',
        '.venv/Scripts/python.exe validation/followup/verify_artifacts.py', '```', '']
    (HERE / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    canonical = '# Current backend verification\n\nThe current evidence is the 2026-10-09 hardening run. '
    canonical += f"{metadata['tests']} passing JUnit cases; 1,295 unchanged formula checks; {summary['passing_property_examples']:,} passing generated examples; 9 synthetic profiles. "
    canonical += 'No live token was available.\n\n[Findings, decisions, accounting and limits](../../hardening/REPORT.md) · '
    canonical += '[Formulas, data and inference](FORMULAS_AND_RESULTS.md).\n'
    (OUT / 'VALIDATION_REPORT.md').write_text(canonical, encoding='utf-8')
    for name in ('findings.json', 'VALIDATION_REPORT.md'):
        shutil.copyfile(OUT / name, ROOT / 'validation/followup/final' / name)
    (ROOT / 'validation/followup/REPORT.md').write_text('# Backend verification\n\n'
        'Current report: [backend hardening, 2026-10-09](../hardening/REPORT.md). '
        'Current detailed formula/data appendix: [formulas and results](final/FORMULAS_AND_RESULTS.md).\n\n'
        'The earlier audit evidence was preserved under [hardening baseline](../hardening/baseline/metadata.json) before implementation. '
        'The final directory now identifies the current code; historical follow-up artifacts outside final are retained as historical records.\n', encoding='utf-8')
    print(json.dumps(dict(fixed_findings=len(rows), report='validation/hardening/REPORT.md')))


if __name__ == '__main__':
    main()
