#!/usr/bin/env python3
"""Check repository maintenance contracts and retain locally executed evidence."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

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


def verify(profile, out, base=None):
    steps = policy(ROOT)['profiles'][profile]
    if profile == 'ui' and base is None:
        raise ValueError('UI evidence needs --base PATH for the before/after screenshots')
    out.mkdir(parents=True, exist_ok=False)
    sources = {'candidate':fingerprint(ROOT)}
    if base is not None:
        sources['base'] = fingerprint(base)
    rows = []
    for step in steps:
        name = step['id']
        argv = step['argv']
        root = base if name == 'panel-before' else ROOT
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
        if argv[0] == 'python3':
            argv = [sys.executable, *argv[1:]]
        if profile == 'ui':
            env['FIGMA_FLOW_PANEL_WORKSPACE_SCREENSHOT'] = str(out / (name + '.png'))
        log = out / (name + '.log')
        returncode = None
        with log.open('x', encoding='utf-8') as stream:
            try:
                result = subprocess.run(argv, cwd=root, env=env, check=False,
                                        stdout=stream, stderr=subprocess.STDOUT, timeout=300)
                returncode = result.returncode
                status = 'failed' if returncode else 'passed'
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                stream.write(str(exc) + '\n')
                status = 'unavailable'
        if profile == 'ui' and status == 'passed' and not (out / (name+'.png')).is_file():
            status = 'unavailable'
        body = log.read_text(encoding='utf-8', errors='replace')
        skipped = re.findall(r'(?:skipped=|# skipped |ℹ skipped )(\d+)', body)
        row = {'id':name, 'status':status, 'log':log.name, 'returncode':returncode, 'skipped':sum(int(n) for n in skipped)}
        if (out / (name+'.png')).is_file():
            row['screenshot'] = name + '.png'
        rows.append(row)
    status = 'passed' if all(r['status']=='passed' for r in rows) else 'incomplete'
    if fingerprint(ROOT)!=sources['candidate'] or (base and fingerprint(base)!=sources['base']):
        status = 'source-changed'
    result = {'schema':'figma-flow-maintenance-evidence-v1', 'profile':profile,
              'sources':sources, 'steps':rows, 'status':status}
    (out/'evidence.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
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
    raise SystemExit(main())
