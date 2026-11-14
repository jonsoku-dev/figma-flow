#!/usr/bin/env python3
"""Fresh native-read baseline through the registered plugin's discover read.

Each sample is one `figma_control.py run --operation read` on a prepared discover
task. Tasks prepared with `graph_sync.py discover --read-measure timing` add the
plugin reader clock; `--read-measure getter-counts` is a single diagnostic run that
never enters the reported statistics. The runner never retries a sample.
"""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHEMA = 'figma-flow-native-read-benchmark-sample-v1'
REPORT_SCHEMA = 'figma-flow-native-read-benchmark-report-v1'
PUBLIC_SCHEMA = 'figma-flow-native-read-benchmark-public-v1'
WORKLOADS = {'discovery-full-default': None, 'discovery-full-timed': 'timing', 'discovery-full-diagnostic': 'getter-counts'}
VOLATILE = ('observed_at', 'read_measurement')
TIMEOUT_STATES = {'expired', 'uncertain', 'runner-timeout'}
MINIMUM_SAMPLES = 5
SUMMARY_UNMEASURED = {'measured': False, 'reason': 'control discover admits only read; the panel native-summary action is not driven by this runner'}
MAX_READBACK_FILE = 64 * 1024 * 1024
PINNED_SOURCES = ('figma-bridge/native_semantic_read.js', 'figma-bridge/native_read_measurement.js',
                  'tools/graph_sync.py', 'tools/figma_control.py', 'tools/native_read_benchmark.py')


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def valid_counts(pages, allowed_page_ids):
    count = lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return bool(pages) and [row.get('pageId') for row in pages] == list(allowed_page_ids or []) and all(
        count(row.get('node_property_gets')) and row['node_property_gets'] > 0 and count(row.get('node_property_has'))
        and count(row.get('reader_result_bytes')) and row['reader_result_bytes'] > 0
        and isinstance(row.get('by_property'), dict) and all(count(value) for value in row['by_property'].values())
        and isinstance(row.get('api_calls'), dict) and all(
            isinstance(call, dict) and count(call.get('calls')) and isinstance(call.get('elapsed_ms'), (int, float))
            for call in row['api_calls'].values())
        for row in pages)


def sample_from(workload, role, index, status, raw, end_to_end_ms, execution, expected_scope=None):
    """One control read. `raw` is the saved readback bytes or None; `expected_scope` is the requested file/page."""
    state = status.get('state', 'cli-error')
    sample = {'schema': SAMPLE_SCHEMA, 'workload': workload, 'role': role, 'index': index, 'execution': execution,
              'state': state, 'error': status.get('error'), 'operation_id': status.get('id'),
              'end_to_end_ms': end_to_end_ms, 'queue_ms': None, 'plugin_span_ms': None,
              'reader_elapsed_ms': None, 'reader_pages': None, 'discovery_elapsed_ms': None,
              'readback_bytes': None, 'content_sha256': None, 'observed_at': None, 'scope': None,
              'coverage': None, 'getter_counts': None}
    if isinstance(status.get('created_at'), (int, float)) and isinstance(status.get('claimed_at'), (int, float)):
        sample['queue_ms'] = (status['claimed_at'] - status['created_at']) * 1000
        if isinstance(status.get('completed_at'), (int, float)):
            sample['plugin_span_ms'] = (status['completed_at'] - status['claimed_at']) * 1000
    if state != 'ok':
        return sample
    if raw is None:
        sample.update(state='missing-readback', error='Control reported ok without a readable readback')
        return sample
    readback = json.loads(raw)
    measurement = readback.get('read_measurement')
    if (measurement or {}).get('mode') != WORKLOADS[workload]:
        sample.update(state='workload-mismatch', error='Readback measurement mode differs from the workload task')
        return sample
    if readback.get('schema') != 'figma-flow-graph-native-discovery-v1' or readback.get('status') not in (None, 'ok', 'success'):
        sample.update(state='not-full-discovery', error='Readback is not a successful full native discovery')
        return sample
    if expected_scope and (readback.get('fileKey'), readback.get('pageId')) != (expected_scope['file_key'], expected_scope['page_id']):
        sample.update(state='scope-mismatch', error='Readback file/page differs from the requested scope')
        return sample
    nodes = readback.get('nodes') or []
    sample.update(readback_bytes=len(raw), observed_at=readback.get('observed_at'),
                  content_sha256=canonical_sha256({key: value for key, value in readback.items() if key not in VOLATILE}))
    sample['scope'] = {'file_key': readback.get('fileKey'), 'page_id': readback.get('pageId'),
                       'allowed_page_ids': readback.get('allowed_page_ids'), 'profile': 'full', 'nodes': len(nodes),
                       'node_ids_sha256': canonical_sha256([row.get('id') for row in nodes])}
    reported = readback.get('coverage')
    sample['coverage'] = {'complete': reported.get('complete') if isinstance(reported, dict) else None,
                          'reported': isinstance(reported, dict), 'unavailable_fields': sum(len(row.get('unavailable_fields') or {}) for row in nodes),
                          'raster_images': len(readback.get('rasterImages') or {}), 'variables': len(readback.get('variables') or []),
                          'collections': len(readback.get('collections') or [])}
    if measurement:
        pages = measurement.get('pages') or []
        sample['reader_pages'] = [{'pageId': row.get('pageId'), 'reader_elapsed_ms': row.get('reader_elapsed_ms')} for row in pages]
        sample['reader_elapsed_ms'] = sum(row.get('reader_elapsed_ms') or 0 for row in pages)
        sample['discovery_elapsed_ms'] = measurement.get('discovery_elapsed_ms')
        sample['clock'] = measurement.get('clock')
        if measurement.get('mode') == 'getter-counts':
            if not valid_counts(pages, readback.get('allowed_page_ids')):
                sample.update(state='invalid-counts', error='Diagnostic getter counts are missing or do not cover every allowed page')
                return sample
            sample['getter_counts'] = [{key: row.get(key) for key in ('pageId', 'node_property_gets', 'node_property_has', 'by_property',
                                                                      'api_calls', 'reader_result_bytes')} for row in pages]
    return sample


def spread(values):
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return None
    return {'n': len(values), 'median': statistics.median(values), 'min': min(values), 'max': max(values)}


def diagnostic_profile(sample):
    if not sample or sample['state'] != 'ok' or not sample['getter_counts']:
        return None
    pages = []
    for row, timing in zip(sample['getter_counts'], sample['reader_pages']):
        named = sum(call['elapsed_ms'] for call in row['api_calls'].values())
        pages.append({**row, 'instrumented_reader_ms': timing['reader_elapsed_ms'], 'named_call_elapsed_ms': named,
                      'unattributed_ms': timing['reader_elapsed_ms'] - named,
                      'top_properties': sorted(row['by_property'].items(), key=lambda item: -item[1])[:10]})
    return {'content_sha256': sample['content_sha256'], 'pages': pages,
            'limits': 'Proxy instrumentation inflates time; named_call_elapsed_ms covers counted API calls only and '
                      'unattributed_ms mixes property getters, JSON copies and reader logic.'}


def summarize(samples, diagnostic, pins, readiness_before, readiness_after, minimum=MINIMUM_SAMPLES):
    reasons = []
    executions = {sample['execution'] for sample in samples + ([diagnostic] if diagnostic else [])}
    ok = [sample for sample in samples if sample['state'] == 'ok']
    hashes = sorted({sample['content_sha256'] for sample in ok})
    node_sets = sorted({sample['scope']['node_ids_sha256'] for sample in ok})
    drift = len(hashes) > 1 or len(node_sets) > 1
    if drift:
        reasons.append('content drift across successful samples')
    if diagnostic is None:
        reasons.append('getter-count diagnostic was not run')
    elif diagnostic['state'] != 'ok':
        reasons.append(f"getter-count diagnostic {diagnostic['state']}: {diagnostic.get('error')}")
    elif hashes and diagnostic['content_sha256'] not in hashes:
        reasons.append('diagnostic read saw different content')
    observed = [sample['observed_at'] for sample in sorted(ok, key=lambda item: item['index'])]
    if observed != sorted(observed) or len(set(observed)) != len(observed):
        reasons.append('observed_at is not strictly increasing across fresh reads')
    for state in (readiness_before, readiness_after):
        if not state or state.get('native_status') != 'current-self-reported' or state.get('expected_native') != state.get('observed_native'):
            reasons.append('native runtime was not current-self-reported around the run')
            break
    if (pins or {}).get('dirty') is not False:
        reasons.append('source checkout is dirty or its state is unpinned')
    if readiness_before and readiness_after and readiness_before.get('observed_native') != readiness_after.get('observed_native'):
        reasons.append('native runtime changed during the run')
    workloads = {}
    for name in [name for name in WORKLOADS if name != 'discovery-full-diagnostic']:
        rows = [sample for sample in samples if sample['workload'] == name]
        if not rows:
            continue
        good = [sample for sample in rows if sample['state'] == 'ok']
        failures = {}
        for sample in rows:
            if sample['state'] != 'ok':
                failures[sample['state']] = failures.get(sample['state'], 0) + 1
        entry = {'attempts': len(rows), 'ok': len(good), 'failures': failures,
                 'timeouts': sum(count for state, count in failures.items() if state in TIMEOUT_STATES), 'retries': 0,
                 'stats': None}
        if len(good) < minimum:
            reasons.append(f'{name}: {len(good)} successful samples, {minimum} required')
        elif not drift:
            entry['stats'] = {metric: spread(sample[metric] for sample in good)
                              for metric in ('end_to_end_ms', 'queue_ms', 'plugin_span_ms', 'reader_elapsed_ms',
                                             'discovery_elapsed_ms', 'readback_bytes')}
            if WORKLOADS[name] == 'timing':
                entry['stats']['reader_share_of_end_to_end'] = spread(
                    sample['reader_elapsed_ms'] / sample['end_to_end_ms'] for sample in good if sample['end_to_end_ms'])
        workloads[name] = entry
    default, timed = (workloads.get(name, {}).get('stats') for name in ('discovery-full-default', 'discovery-full-timed'))
    overhead = None
    if default and timed:
        left, right = default['end_to_end_ms'], timed['end_to_end_ms']
        overhead = {'default_end_to_end_ms': left, 'timed_end_to_end_ms': right,
                    'ranges_overlap': left['min'] <= right['max'] and right['min'] <= left['max']}
    reference = ok[0] if ok else None
    return {'schema': REPORT_SCHEMA, 'verdict': 'inconclusive' if reasons else 'baseline-recorded', 'reasons': reasons,
            'native_proof': executions == {'root-live'} and not reasons, 'executions': sorted(executions),
            'pins': pins, 'readiness_before': readiness_before, 'readiness_after': readiness_after,
            'scope': reference['scope'] if reference else None, 'coverage': reference['coverage'] if reference else None,
            'content_sha256': hashes, 'workloads': workloads, 'timing_overhead_check': overhead,
            'diagnostic': {'state': diagnostic['state'], 'profile': diagnostic_profile(diagnostic)} if diagnostic else None,
            'summary_profile': SUMMARY_UNMEASURED,
            'claims': 'Baseline only. No speedup claim. Summary and full are different work and are never compared.'}


def public_summary(report):
    secret = lambda value: hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:12] if value is not None else None
    scope = report['scope'] or {}
    pages = (report.get('diagnostic') or {}).get('profile') or {}
    return {'schema': PUBLIC_SCHEMA, 'verdict': report['verdict'], 'reasons': report['reasons'],
            'native_proof': report['native_proof'], 'executions': report['executions'],
            'pins': {key: value for key, value in (report['pins'] or {}).items() if key not in ('workspace', 'tasks')},
            'task_artifacts': {name: row.get('code_sha256') for name, row in ((report['pins'] or {}).get('tasks') or {}).items()},
            'scope': {'file': secret(scope.get('file_key')), 'page': secret(scope.get('page_id')),
                      'pages': len(scope.get('allowed_page_ids') or []), 'nodes': scope.get('nodes'), 'profile': scope.get('profile')},
            'coverage': report['coverage'], 'content_hashes': len(report['content_sha256']),
            'workloads': report['workloads'], 'timing_overhead_check': report['timing_overhead_check'],
            'diagnostic': None if not report.get('diagnostic') else {
                'state': report['diagnostic']['state'],
                'pages': [{key: value for key, value in row.items() if key not in ('pageId', 'by_property')}
                          for row in pages.get('pages', [])]},
            'summary_profile': report['summary_profile'], 'claims': report['claims']}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def source_pins():
    return {'source_commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain', '--untracked-files=no')),
            'blobs': {path: git('hash-object', path) for path in PINNED_SOURCES if (ROOT / path).exists()},
            'plugin_version': json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))['version']}


def readiness(workspace_root):
    sys.path.insert(0, str(ROOT / 'tools'))
    import figma_control
    import figma_workspace
    settings = figma_control.config(figma_workspace.private_dir(workspace_root))
    connection = http.client.HTTPConnection('127.0.0.1', settings['port'], timeout=3)
    try:
        connection.request('POST', '/control/readiness', b'{}', {'Host': f'localhost:{settings["port"]}',
                           'Content-Type': 'application/json', 'Authorization': 'Bearer ' + settings['token']})
        response = connection.getresponse()
        raw = response.read(figma_control.MAX_READINESS + 1)
        if response.status != 200 or len(raw) > figma_control.MAX_READINESS:
            raise ValueError('Control readiness rejected')
        return json.loads(raw)
    finally:
        connection.close()


def task_pins(workspace_root, keys):
    sys.path.insert(0, str(ROOT / 'tools'))
    import figma_workspace
    catalogue = figma_workspace.current(figma_workspace.private_dir(workspace_root), repair=False)
    rows = {row['key']: row for row in catalogue['tasks']}
    return {key: {'kind': rows[key]['kind'], 'revision': rows[key]['revision'], 'generator_args': rows[key].get('generator_args'),
                  'code_sha256': (rows[key].get('artifact_hashes') or {}).get('code.js')} for key in keys if key in rows}


def control_read(workspace_root, key, revision, file_key, page_id, timeout):
    command = [sys.executable, '-B', str(ROOT / 'tools' / 'figma_control.py'), 'run', '--workspace', str(workspace_root),
               '--key', key, '--operation', 'read', '--file-key', file_key, '--page-id', page_id,
               '--expected-revision', revision, '--timeout', str(timeout)]
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        return {'state': 'runner-timeout', 'error': 'figma_control run exceeded the runner guard'}, None, (time.monotonic() - started) * 1000
    elapsed = (time.monotonic() - started) * 1000
    try:
        status = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'state': 'cli-error', 'error': (result.stderr or result.stdout).strip()[:500]}, None, elapsed
    raw = None
    path = status.get('readback')
    if status.get('state') == 'ok' and path and Path(path).is_file() and Path(path).stat().st_size <= MAX_READBACK_FILE:
        raw = Path(path).read_bytes()
    return status, raw, elapsed


def run(plan, out, *, control, execution, pins, before, readiness_after, minimum=MINIMUM_SAMPLES):
    """plan: {'tasks': {workload: (key, revision)}, 'repeats': n, 'scope': {'file_key', 'page_id'}}.
    Sample workloads alternate; the diagnostic runs once last."""
    scope = plan['scope']
    if not scope.get('file_key') or not scope.get('page_id'):
        raise ValueError('The requested file/page scope is required')
    sampled = [name for name in WORKLOADS if name in plan['tasks'] and name != 'discovery-full-diagnostic']
    if not sampled:
        raise ValueError('At least one default or timed workload is required')
    samples, index = [], 0
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    with (out / 'samples.jsonl').open('w', encoding='utf-8') as log:
        for _ in range(plan['repeats']):
            for name in sampled:
                status, raw, elapsed = control(*plan['tasks'][name])
                sample = sample_from(name, 'sample', index, status, raw, elapsed, execution, scope)
                samples.append(sample)
                log.write(json.dumps(sample, sort_keys=True) + '\n')
                log.flush()
                index += 1
        diagnostic = None
        if 'discovery-full-diagnostic' in plan['tasks']:
            status, raw, elapsed = control(*plan['tasks']['discovery-full-diagnostic'])
            diagnostic = sample_from('discovery-full-diagnostic', 'diagnostic', index, status, raw, elapsed, execution, scope)
            log.write(json.dumps(diagnostic, sort_keys=True) + '\n')
    after = readiness_after()
    report = summarize(samples, diagnostic, pins, before, after, minimum=minimum)
    (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (out / 'public-summary.json').write_text(json.dumps(public_summary(report), indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return report


def task_argument(value):
    key, separator, revision = value.partition(':')
    if not separator or not key or len(revision) != 64:
        raise argparse.ArgumentTypeError('Use TASK_KEY:EXPECTED_REVISION')
    return key, revision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--file-key', required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--default', type=task_argument, help='Unmeasured discover task KEY:REVISION')
    parser.add_argument('--timed', type=task_argument, help='discover --read-measure timing task KEY:REVISION')
    parser.add_argument('--diagnostic', type=task_argument, help='discover --read-measure getter-counts task KEY:REVISION (one excluded run)')
    parser.add_argument('--repeats', type=int, default=MINIMUM_SAMPLES)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--out', type=Path, required=True, help='New private evidence directory')
    args = parser.parse_args(argv)
    if args.repeats < MINIMUM_SAMPLES:
        parser.error(f'--repeats must be at least {MINIMUM_SAMPLES}')
    tasks = {name: value for name, value in (('discovery-full-default', args.default), ('discovery-full-timed', args.timed),
                                             ('discovery-full-diagnostic', args.diagnostic)) if value}
    before = readiness(args.workspace)
    if before.get('native_status') != 'current-self-reported':
        print('native-read-benchmark: reopen the SAME registered Figma Flow plugin; runtime is not current-self-reported', file=sys.stderr)
        return 2
    pins = {**source_pins(), 'control_implementation': before.get('implementation'),
            'tasks': task_pins(args.workspace, [key for key, _ in tasks.values()])}
    pins['tasks'] = {name: pins['tasks'].get(key) for name, (key, _) in tasks.items()}
    report = run({'tasks': tasks, 'repeats': args.repeats, 'scope': {'file_key': args.file_key, 'page_id': args.page_id}}, args.out, execution='root-live', pins=pins, before=before,
                 readiness_after=lambda: readiness(args.workspace),
                 control=lambda key, revision: control_read(args.workspace, key, revision, args.file_key, args.page_id, args.timeout))
    print(json.dumps({'verdict': report['verdict'], 'reasons': report['reasons'], 'native_proof': report['native_proof'],
                      'report': str(args.out / 'report.json'), 'public_summary': str(args.out / 'public-summary.json')}))
    return 0 if report['verdict'] == 'baseline-recorded' else 2


if __name__ == '__main__':
    raise SystemExit(main())
