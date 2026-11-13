#!/usr/bin/env python3
"""Replay optional native readback and private fixture tests without source writes."""
from concurrent.futures import ThreadPoolExecutor
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_draft

SHADOW_ID = 'tests.test_design_quality.RealLayoutCalibrationTests.test_shadow_troupe_light_bars_are_placeholder_bars'
NATIVE_ID = 'tests.test_figma_draft.OptionalLiveReadbackTests.test_supplied_native_evidence_and_tampering'
MOSS_NAME = 'actual saved initial Moss tint packet is rejected without writes'
MOSS_ID = f'tests/test_direction_color_admission.cjs::{MOSS_NAME}'
HELPERS = ('semantic_tokens.js', 'native_annotations.js', 'native_semantic_read.js',
           'foundation_palette.js', 'design_note_board.js', 'direction_review.js')


def file_input(path, label):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'{label} must be a regular file')
    return path


def directory_input(path, label):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f'{label} must be a regular directory')
    return path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_hash(path):
    return sha(path.read_bytes())


def python_counts(output):
    ran = re.search(r'^Ran (\d+) tests? in ', output, re.M)
    skipped_match = re.search(r'skipped=(\d+)', output)
    failed = re.search(r'^FAILED \((.*?)\)$', output, re.M)
    if not ran:
        return {'tests': 0, 'passed': 0, 'skipped': 0, 'failed': 0, 'recognized': False}
    tests = int(ran.group(1))
    skips = int(skipped_match.group(1)) if skipped_match else 0
    failures = 0
    if failed:
        for name in ('failures', 'errors'):
            count = re.search(rf'(\d+) {name}', failed.group(1))
            failures += int(count.group(1)) if count else 0
    passed = tests - skips - failures
    return {'tests': tests, 'passed': max(0, passed), 'skipped': skips, 'failed': failures, 'recognized': True}


def tap_counts(output):
    fields = {}
    for key in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo'):
        match = re.search(rf'^# {key} (\d+)$', output, re.M)
        if match:
            fields[key] = int(match.group(1))
    return {
        'tests': fields.get('tests', 0),
        'passed': fields.get('pass', 0),
        'failed': fields.get('fail', 0) + fields.get('cancelled', 0),
        'skipped': fields.get('skipped', 0) + fields.get('todo', 0),
        'recognized': 'tests' in fields and 'pass' in fields and 'fail' in fields and 'skipped' in fields,
    }


def result_record(test_id, result, counts):
    output = (result.stdout + result.stderr).encode()
    successful = result.returncode == 0 and counts['recognized'] and counts['tests'] > 0 \
        and counts['passed'] == counts['tests'] and counts['failed'] == 0 and counts['skipped'] == 0
    if successful:
        status = 'passed'
    elif counts['skipped']:
        status = 'skipped'
    else:
        status = 'failed'
    return {
        'test_id': test_id,
        'status': status,
        'counts': {key: counts[key] for key in ('tests', 'passed', 'skipped', 'failed')},
        'output': {'bytes': len(output), 'sha256': sha(output)},
    }


@contextmanager
def isolated_checkout(shadow_root=None, moss_root=None):
    with tempfile.TemporaryDirectory(prefix='figma-flow-optional-tests-') as temporary:
        temp = Path(temporary)
        project = temp / 'figma-flow'
        (project / 'tests').mkdir(parents=True)
        (project / 'tools').symlink_to(ROOT / 'tools', target_is_directory=True)
        (project / 'figma-bridge').symlink_to(ROOT / 'figma-bridge', target_is_directory=True)
        shutil.copy2(ROOT / 'tests/test_design_quality.py', project / 'tests/test_design_quality.py')
        shutil.copy2(ROOT / 'tests/test_figma_draft.py', project / 'tests/test_figma_draft.py')
        shutil.copy2(ROOT / 'tests/test_direction_color_admission.cjs', project / 'tests/test_direction_color_admission.cjs')
        demo = project / 'examples/native-direction-review'
        demo.mkdir(parents=True)
        shutil.copy2(ROOT / 'examples/native-direction-review/demo.py', demo / 'demo.py')
        if shadow_root:
            (temp / 'shadow-troupe').symlink_to(shadow_root, target_is_directory=True)
        if moss_root:
            (temp / 'moss-choir').symlink_to(moss_root, target_is_directory=True)
        yield project, temp


def run_command(command, cwd, env=None):
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def native_inputs(args):
    names = ('manifest', 'readback', 'packet', 'code', 'source_dir')
    values = {name: getattr(args, name) for name in names}
    supplied = {name for name, value in values.items() if value}
    if not supplied:
        return None
    if len(supplied) != len(names):
        raise ValueError('Supply all native replay inputs: --manifest, --readback, --packet, --code, and --source-dir')
    manifest = file_input(args.manifest, 'Manifest')
    readback = file_input(args.readback, 'Readback')
    packet_path = file_input(args.packet, 'Renderer packet')
    original_code = file_input(args.code, 'Generated plugin code')
    source_dir = directory_input(args.source_dir, 'Renderer source directory')
    sources = {name: file_input(source_dir / name, f'Renderer source {name}') for name in HELPERS}

    manifest_data = json.loads(manifest.read_text(encoding='utf-8'))
    pinned = manifest_data.get('native_review', {}).get('readback', {})
    if not isinstance(pinned, dict) or not isinstance(pinned.get('path'), str) or not isinstance(pinned.get('sha256'), str):
        raise ValueError('Manifest must pin its native readback path and SHA-256')
    if Path(pinned['path']).resolve() != readback.resolve() or file_hash(readback) != pinned['sha256']:
        raise ValueError('Readback path and bytes must match the manifest pin')

    packet = json.loads(packet_path.read_text(encoding='utf-8'))
    source_text = {name: path.read_text(encoding='utf-8') for name, path in sources.items()}
    expected_code = figma_draft.review_plugin_code(
        json.dumps(packet, ensure_ascii=False),
        '\n'.join(source_text[name] for name in HELPERS[:-1]),
        source_text['direction_review.js'],
    ).encode()
    if original_code.read_bytes() != expected_code:
        raise ValueError('Generated plugin code does not reproduce from the supplied packet and renderer sources')
    return {
        'manifest': manifest, 'readback': readback, 'packet_path': packet_path,
        'packet': packet, 'original_code': original_code, 'sources': sources,
        'manifest_sha256': file_hash(manifest), 'readback_sha256': file_hash(readback),
        'packet_sha256': file_hash(packet_path), 'code_sha256': file_hash(original_code),
        'source_hashes': {name: file_hash(path) for name, path in sources.items()},
    }


def run_native(project, temp, inputs):
    evidence = temp / 'native-evidence'
    evidence.mkdir()
    manifest = evidence / 'directions.json'
    manifest.write_bytes(inputs['manifest'].read_bytes())
    packet = dict(inputs['packet'])
    packet['manifest'] = str(manifest.resolve())
    packet_path = evidence / 'packet.json'
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    helper_text = '\n'.join(inputs['sources'][name].read_text(encoding='utf-8') for name in HELPERS[:-1])
    review_source = inputs['sources']['direction_review.js'].read_text(encoding='utf-8')
    code = figma_draft.review_plugin_code(json.dumps(packet, ensure_ascii=False), helper_text, review_source)
    code_path = evidence / 'code.js'
    code_path.write_text(code, encoding='utf-8')
    snapshot = {
        'schema': 'figma-flow-native-renderer-snapshot-v1',
        'sources': {name: {'path': str(path), 'sha256': file_hash(path)} for name, path in inputs['sources'].items()},
        'packet': {'path': str(packet_path), 'sha256': file_hash(packet_path)},
        'code': {'path': str(code_path), 'sha256': file_hash(code_path)},
    }
    (evidence / 'renderer-snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')
    env = os.environ.copy()
    env['FIGMA_DRAFT_LIVE_MANIFEST'] = str(manifest)
    env['FIGMA_DRAFT_LIVE_READBACK'] = str(inputs['readback'])
    result = run_command([sys.executable, '-B', '-m', 'unittest', '-v', NATIVE_ID], project, env)
    record = result_record(NATIVE_ID, result, python_counts(result.stdout + result.stderr))
    record['inputs'] = {
        'manifest_sha256': inputs['manifest_sha256'], 'readback_sha256': inputs['readback_sha256'],
        'original_packet_sha256': inputs['packet_sha256'], 'original_code_sha256': inputs['code_sha256'],
        'renderer_source_sha256': inputs['source_hashes'],
        'isolated_snapshot_sha256': file_hash(evidence / 'renderer-snapshot.json'),
    }
    return record


def run_shadow(project, temp):
    result = run_command([sys.executable, '-B', '-m', 'unittest', '-v',
                          'tests.test_design_quality.RealLayoutCalibrationTests.test_shadow_troupe_light_bars_are_placeholder_bars'], project)
    return result_record(SHADOW_ID, result, python_counts(result.stdout + result.stderr))


def run_moss(project):
    result = run_command(['node', '--test', '--test-reporter=tap', 'tests/test_direction_color_admission.cjs'], project)
    counts = tap_counts(result.stdout + result.stderr)
    record = result_record(MOSS_ID, result, counts)
    record['file_test_counts'] = counts
    return record


def verify_fixture(root, name):
    if root is None:
        return None
    root = directory_input(root, f'{name} fixture root')
    if not (root / 'native-layout.json').is_file() or (root / 'native-layout.json').is_symlink():
        raise ValueError(f'{name} fixture root must contain a regular native-layout.json')
    return root


def run(args):
    shadow = verify_fixture(args.shadow_root, 'Shadow Troupe')
    moss = verify_fixture(args.moss_root, 'Moss Choir')
    native = native_inputs(args)
    if shadow is None and moss is None and native is None:
        raise ValueError('Supply at least one original fixture or native evidence set')
    with isolated_checkout(shadow, moss) as (project, temp):
        records = []
        if shadow:
            records.append(run_shadow(project, temp))
        else:
            records.append({'test_id': SHADOW_ID, 'status': 'not_run', 'reason': 'Shadow Troupe original not supplied', 'counts': {'tests': 0, 'passed': 0, 'skipped': 0, 'failed': 0}})
        if moss:
            records.append(run_moss(project))
        else:
            records.append({'test_id': MOSS_ID, 'status': 'not_run', 'reason': 'Moss Choir original not supplied', 'counts': {'tests': 0, 'passed': 0, 'skipped': 0, 'failed': 0}})
        if native:
            records.append(run_native(project, temp, native))
        else:
            records.append({'test_id': NATIVE_ID, 'status': 'not_run', 'reason': 'Native readback evidence not supplied', 'counts': {'tests': 0, 'passed': 0, 'skipped': 0, 'failed': 0}})

    complete = all(item['status'] == 'passed' for item in records)
    receipt = {
        'schema': 'figma-flow-optional-tests-replay-v1',
        'status': 'passed' if complete else 'incomplete',
        'tests': records,
        'paths_included': False,
    }
    output = Path(args.receipt).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing to overwrite replay receipt: {output.name}')
    if not output.parent.is_dir():
        raise ValueError('Receipt parent directory must already exist')
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    output.chmod(0o600)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shadow-root', help='Original project directory containing native-layout.json')
    parser.add_argument('--moss-root', help='Original project directory containing native-layout.json')
    parser.add_argument('--manifest', help='Exact native review manifest')
    parser.add_argument('--readback', help='Readback path pinned by the native review manifest')
    parser.add_argument('--packet', help='Original generated native review packet')
    parser.add_argument('--code', help='Generated plugin code from that packet')
    parser.add_argument('--source-dir', help='Directory with the six historical renderer source files')
    parser.add_argument('--receipt', required=True, help='New path for a privacy-safe JSON receipt')
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
