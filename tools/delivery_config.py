#!/usr/bin/env python3
"""Render pinned CI inputs into GitHub's required workflow files."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
GRAPH = Path('library/delivery/graph.json')
FIELD = re.compile(r'\{\{delivery\.([A-Za-z0-9_.-]+)\}\}')


def templates(root):
    graph = json.loads((root / GRAPH).read_bytes())
    if graph['schema'] != 'figma-flow-delivery-v1':
        raise ValueError('Unsupported delivery graph')
    inputs = dict(graph['inputs'])
    ts = inputs['typescript']
    inputs['typescript'] = json.loads((root/ts['source']).read_bytes())['devDependencies'][ts['dependency']]
    ci = inputs['appCi']
    database = json.loads((root / ci['deploymentSource']).read_bytes())['database']
    inputs['appCi'] = {**ci, 'database':database['name'], 'port':str(database['port']), 'image':database['image']}
    if not all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in inputs['actions'].values()):
        raise ValueError('CI actions require exact Git SHAs')
    if not all(re.fullmatch(r'[0-9a-f]{64}', row['sha256']) for row in inputs['sandboxCli']['artifacts'].values()):
        raise ValueError('Sandbox CLI archives require SHA-256')
    entries = {}
    for name, spec in graph['workflows'].items():
        src, dst = Path(spec['source']), Path(spec['output'])
        if (src.parent != GRAPH.parent or src.name != name + '.yml.in' or
                dst != Path('.github/workflows') / (name + '.yml')):
            raise ValueError('Unexpected workflow source or destination')
        def expand(m):
            value = inputs
            for key in m[1].split('.'):
                value = value[key]
            if not isinstance(value, str) or not value or '\n' in value:
                raise ValueError('Invalid scalar CI input: ' + m[1])
            return value
        result = FIELD.sub(expand, (root/src).read_text(encoding='utf-8'))
        if '{{delivery.' in result:
            raise ValueError('Unresolved workflow reference in ' + name)
        entries[dst] = '# Generated from ' + src.as_posix() + ' and ' + GRAPH.as_posix() + '.\n' + result
    if set((root/GRAPH.parent).glob('*.yml.in')) != {root / spec['source'] for spec in graph['workflows'].values()}:
        raise ValueError('Unregistered delivery template')
    return entries


def marketplace(root):
    """Resolve this plugin by local source, keeping the marketplace operator's policy."""
    root = Path(root)
    settings = json.loads((root / GRAPH).read_bytes())['native']['marketplace']
    path = root/settings['source']
    catalog = json.loads(path.read_bytes())
    local = [plugin for plugin in catalog['plugins'] if plugin.get('source') == {
        'source':'local', 'path':settings['localRoot']}]
    if len(local) != 1:
        raise ValueError('Expected exactly one local root plugin in the marketplace')
    product = json.loads((root/settings['plugin']).read_bytes())
    local[0].update(name=product['name'], category=product['extensions']['com.openai']['interface']['category'])
    return path, catalog


def check(root):
    root = Path(root)
    entries = templates(root)
    found = {p.relative_to(root) for p in (root/'.github/workflows').iterdir() if p.suffix in {'.yml','.yaml'}}
    issues = [str(p) for p in found | entries.keys()
              if p not in found or p not in entries or (root/p).read_bytes() != entries[p].encode()]
    path, catalog = marketplace(root)
    if catalog != json.loads(path.read_bytes()):
        issues.append(str(path.relative_to(root)))
    return sorted(issues)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.write:
        path, catalog = marketplace(ROOT)
        if catalog != json.loads(path.read_bytes()):
            path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for name, content in templates(ROOT).items():
            if not (ROOT/name).exists() or (ROOT/name).read_bytes() != content.encode():
                (ROOT/name).write_text(content,encoding='utf-8')
    drift = check(ROOT)
    if drift:
        print('Workflow projection differs: ' + ', '.join(drift), file=sys.stderr)
    return int(bool(drift))


if __name__ == '__main__':
    raise SystemExit(main())
