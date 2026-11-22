#!/usr/bin/env python3
"""Check repository maintenance contracts and retain locally executed evidence."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path('tools/maintenance-contract.json')


def policy(root):
    data = json.loads((root / CONTRACT).read_bytes())
    if data['schema'] != 'figma-flow-maintenance-v1':
        raise ValueError('Unknown maintenance contract')
    return data


def graph_decode_findings(root):
    findings = []
    for name, functions in policy(root)['graphDecoding'].items():
        tree = ast.parse((root / name).read_bytes(), filename=name)
        imports = list(ast.walk(tree))
        modules = {a.asname or a.name for n in imports if isinstance(n, ast.Import)
                   for a in n.names if a.name == 'json'}
        decoders = {a.asname or a.name for n in imports
                    if isinstance(n, ast.ImportFrom) and n.module == 'json'
                    for a in n.names if a.name in ('load', 'loads')}
        declared = {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for function in functions:
            if function not in declared:
                findings.append({'path':name, 'line':1, 'message':f'Register the replacement for graph boundary {function}.'})
                continue
            for n in ast.walk(declared[function]):
                if (isinstance(n, ast.Attribute) and n.attr in ('load','loads')
                        and isinstance(n.value, ast.Name) and n.value.id in modules
                        or isinstance(n, ast.Name) and n.id in decoders):
                    findings.append({'path':name, 'line':n.lineno,
                        'message':'Raw JSON decoding can silently select a duplicate graph field. Use graph_document.read_json/decode_json or the portable graph decoder.'})
    return findings


def fingerprint(root):
    try:
        files = subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'], cwd=root, stderr=subprocess.DEVNULL)
        paths = sorted({Path(name.decode()) for name in files.split(b'\0') if name})
    except (OSError, subprocess.SubprocessError):
        paths = sorted(path.relative_to(root) for path in root.rglob('*') if path.is_file()
                       and not {'node_modules', '.figma-flow', '.git', '__pycache__'} & set(path.relative_to(root).parts))
    sha = hashlib.sha256()
    for path in paths:
        item = root/path
        if item.is_file() and not item.is_symlink():
            sha.update(path.as_posix().encode() + b'\0')
            with item.open('rb') as stream:
                sha.update(hashlib.file_digest(stream,'sha256').digest())
    return sha.hexdigest()


def artifact_digest(path):
    with path.open('rb') as stream:
        return {'sha256': hashlib.file_digest(stream, 'sha256').hexdigest(),
                'bytes': os.fstat(stream.fileno()).st_size}


def run_step(step, root, scratch, capture_screen):
    name = step['id']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        raise ValueError(f'Invalid verification step ID: {name!r}')
    argv = step['argv']
    if argv[0] == 'python3':
        argv = [sys.executable, *argv[1:]]
    env = {**os.environ, **dict.fromkeys(('TMPDIR','TMP','TEMP'), str(scratch)),
           'PYTHONDONTWRITEBYTECODE': '1'}
    screenshot = scratch / (name + '.png')
    if capture_screen:
        env['FIGMA_FLOW_PANEL_WORKSPACE_SCREENSHOT'] = str(screenshot)
    log = scratch / (name + '.log')
    status = 'unavailable'
    returncode = None
    with log.open('xb') as stream:
        try:
            process = subprocess.Popen(argv, cwd=root, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=(os.name == 'posix'))
        except FileNotFoundError:
            reason = 'executable-missing'
        else:
            try:
                returncode = process.wait(timeout=step.get('timeoutSeconds', 300))
                status = 'failed' if returncode else 'passed'
                reason = 'exit-nonzero' if returncode else None
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                try:
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
                if isinstance(exc, KeyboardInterrupt):
                    raise
                reason = 'timeout'
    if capture_screen and status == 'passed' and not screenshot.is_file():
        status, reason = 'unavailable', 'screenshot-missing'
    output = artifact_digest(log)
    with log.open('rb') as stream:
        # unittest/TAP summarize counts at the end. Never retain arbitrary child output.
        stream.seek(max(0, output['bytes'] - 16384))
        tail = stream.read().decode('utf-8', errors='replace')
    skipped = re.findall(r'(?:skipped=|# skipped |ℹ skipped )(\d+)', tail)
    row = {'id':name, 'argv':step['argv'], 'status':status, 'returncode':returncode,
           'skipped':sum(map(int, skipped)), 'output':output}
    if reason:
        row['reason'] = reason
    if capture_screen and screenshot.is_file() and not screenshot.is_symlink():
        row['screenshot'] = artifact_digest(screenshot)
    return row


def verify(profile, out, base=None):
    contract = policy(ROOT)
    steps = contract['profiles'][profile]
    capture_screen = profile == 'ui'
    if capture_screen and base is None:
        raise ValueError('UI evidence needs --base PATH for before/after verification')
    limit = contract.get('artifactRetention', {}).get('receiptBytes', 65536)
    out.mkdir(parents=True, exist_ok=False)
    try:
        sources = {'candidate': fingerprint(ROOT)}
        if base is not None:
            sources['base'] = fingerprint(base)
        with tempfile.TemporaryDirectory(prefix='figma-flow-verify-') as temporary:
            scratch = Path(temporary).resolve()
            rows = [
                run_step(step, base if step['id']=='panel-before' else ROOT, scratch, capture_screen)
                for step in steps
            ]
        status = 'passed' if all(r['status']=='passed' for r in rows) else 'incomplete'
        if fingerprint(ROOT)!=sources['candidate'] or (base and fingerprint(base)!=sources['base']):
            status = 'source-changed'
        evidence = json.dumps({'schema':'figma-flow-maintenance-evidence-v2', 'profile':profile,
                               'sources':sources, 'steps':rows, 'status':status},
                              indent=2, ensure_ascii=False).encode() + b'\n'
        if len(evidence) > limit:
            raise ValueError('Verification receipt exceeds the declared byte limit')
        with (out/'evidence.json').open('xb') as receipt:
            receipt.write(evidence)
    except BaseException:
        # The output directory is owned by this invocation. Keep a completed receipt only.
        if not any(out.iterdir()):
            out.rmdir()
        raise
    print(f'{profile}: {status} ({out / "evidence.json"})')
    return int(status != 'passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='Reject known graph ownership bypasses')
    evidence = commands.add_parser('verify', help='Execute a declared verification profile and write evidence')
    evidence.add_argument('--profile', required=True, choices=tuple(policy(ROOT)['profiles']))
    evidence.add_argument('--out', type=Path, required=True)
    evidence.add_argument('--base', type=Path, help='Baseline checkout for UI before/after screenshots')
    args = parser.parse_args()
    if args.command == 'check':
        findings = graph_decode_findings(ROOT)
        for item in findings:
            print(f"{item['path']}:{item['line']}: {item['message']}", file=sys.stderr)
        return int(bool(findings))
    try:
        return verify(args.profile,args.out.resolve(),args.base.resolve() if args.base else None)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'maintenance: {exc}\n')


if __name__ == '__main__':
    def cancel(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Verification cancelled. Temporary output was reclaimed.', file=sys.stderr)
        raise SystemExit(130)
