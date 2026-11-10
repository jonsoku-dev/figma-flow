#!/usr/bin/env python3
"""Derive product state constants from its canonical requirement/state graph, never a second enum."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def render(graph_path, format='esm'):
    path = Path(graph_path).resolve()
    raw = path.read_bytes()
    graph = json.loads(raw)
    if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) or any(not isinstance(n, dict) for n in graph['nodes']):
        raise ValueError('Canonical product graph nodes required')
    rows = [n for n in graph['nodes'] if n.get('type') == 'state']
    values = {}
    for node in rows:
        identity = node.get('id')
        if not isinstance(identity, str) or not identity:
            raise ValueError('Canonical state id must be a nonempty string')
        symbol = node.get('symbol') or re.sub(r'[^A-Za-z0-9_]', '_', identity or '').upper()
        if not identity or not re.fullmatch(r'[A-Z_][A-Z0-9_]*', symbol) or symbol in values or identity in values.values():
            raise ValueError('State IDs/symbols must be unique and declared once in product graph')
        values[symbol] = identity
    fingerprint = hashlib.sha256(raw).hexdigest()
    header = '// GENERATED from canonical product graph; do not edit state names here.\n'
    labels = json.dumps({n['id']: n.get('title', n['id']) for n in rows}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if format == 'esm':
        return header + f'export const STATE_GRAPH_SHA256 = "{fingerprint}";\nexport const AppState = Object.freeze({payload});\nexport const AppStateLabel = Object.freeze({labels});\n'
    if format == 'cjs':
        return header + f'const STATE_GRAPH_SHA256 = "{fingerprint}";\nconst AppState = Object.freeze({payload});\nconst AppStateLabel = Object.freeze({labels});\nmodule.exports = {{AppState,AppStateLabel,STATE_GRAPH_SHA256}};\n'
    raise ValueError('State export format must be esm or cjs')


def validate(graph_path, declaration, base):
    base = Path(base).resolve()
    report = {'passed': False, 'errors': [], 'exports': [], 'consumers': [],
              'boundary': 'Checks canonical state/export/import drift, not that runtime transitions or behavior executed.'}
    graph = json.loads(Path(graph_path).read_text())
    states = [n for n in graph.get('nodes', []) if n.get('type') == 'state']
    if not states:
        report.update(passed=True, scope='no-product-states-declared')
        return report
    try:
        if not isinstance(declaration, dict) or not declaration.get('exports') or not declaration.get('consumers'):
            raise ValueError('Product states require app_state_ssot exports and real runtime/QA consumers')
        exported = {}
        for item in declaration['exports']:
            path = (base / item['path']).resolve()
            if not path.is_relative_to(base) or path.is_symlink() or path.read_text() != render(graph_path, item.get('format', 'esm')):
                raise ValueError('Generated state export drift: ' + str(path))
            exported[item['path']] = path
            report['exports'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        symbols = {n.get('symbol') or re.sub(r'[^A-Za-z0-9_]', '_', n['id']).upper() for n in states}
        for item in declaration['consumers']:
            path = (base / item['path']).resolve()
            if not path.is_relative_to(base) or path.is_symlink():
                raise ValueError('Invalid current state consumer')
            source = path.read_text()
            target = exported.get(item.get('export'))
            if target is None:
                raise ValueError('Consumer must identify a registered canonical export')
            relative = os.path.relpath(target, path.parent).replace(os.sep, '/')
            relative = relative if relative.startswith('.') else './' + relative
            if relative not in source or not re.search(r'\bAppState(?:\.|\[)', source):
                raise ValueError('State consumer does not import/use generated AppState: ' + str(path))
            unknown = set(re.findall(r'\bAppState\.([A-Za-z_][A-Za-z0-9_]*)', source)) - symbols
            if unknown:
                raise ValueError('Unknown canonical product state references: ' + ', '.join(sorted(unknown)))
            for node in states:
                if re.search(r'([\"\'])' + re.escape(node['id']) + r'\1', source):
                    raise ValueError('Handwritten state literal duplicates canonical graph: ' + str(path) + ' ' + node['id'])
            report['consumers'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        report.update(passed=True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        report['errors'].append(str(exc))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--format', choices=('esm', 'cjs'), default='esm')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    try:
        content = render(a.graph, a.format)
        if a.check:
            if not a.out.is_file() or a.out.read_text() != content:
                p.exit(1, 'State export drift\n')
        else:
            if a.out.exists() and not a.out.read_text().startswith('// GENERATED from canonical product graph;'):
                p.exit(1, 'Refuse to overwrite handwritten state definitions\n')
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(content)
    except (OSError, ValueError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
