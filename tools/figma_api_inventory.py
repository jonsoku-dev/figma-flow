#!/usr/bin/env python3
"""Search pinned official Plugin API declarations, without executing Figma code."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'library' / 'figma-api'
INDEX = LIBRARY / 'index.json'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def verify_source():
    source = json.loads((LIBRARY / 'source.json').read_text())
    for name, expected in source['files'].items():
        if hashlib.sha256((LIBRARY / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Pinned source hash mismatch: {name}')
    return source


def inherited_members(catalog, owner):
    declarations = {row['name']: row for row in catalog['declarations']}
    effective = declarations.get(owner, {}).get('effective_member_ids')
    if effective is not None:
        ids = set(effective)
        return [row for row in catalog['members'] if row['id'] in ids]
    by_owner = {}
    for member in catalog['members']:
        by_owner.setdefault(member['owner'], []).append(member)
    seen = set()
    result = []
    def collect(name):
        if name in seen:
            return
        seen.add(name)
        result.extend(by_owner.get(name, []))
        for base in declarations.get(name, {}).get('extends', []):
            collect(base)
    collect(owner)
    return result


def build(typescript=None):
    source = verify_source()
    command = ['node', str(LIBRARY / 'generate.cjs')]
    if typescript:
        command.append(str(Path(typescript).resolve()))
    parsed = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
    catalog = {'schema': 'figma-flow-plugin-api-inventory-v1', 'source': source,
               'generator': {'parser': 'typescript', 'version': '5.9.3'},
               'evidence': 'Official declaration presence only; implementation and runtime acceptance unverified.', **parsed}
    declarations = {row['name']: row for row in catalog['declarations']}
    routes = {'PluginAPI': ['figma']}
    pending = ['PluginAPI']
    while pending:
        owner = pending.pop(0)
        for row in inherited_members(catalog, owner):
            target = row['value_type']
            if target in declarations and target.endswith('API') and target not in routes:
                routes[target] = [f'{routes[owner][0]}.{row["name"]}']
                pending.append(target)
    namespace_context = {}
    for row in catalog['members']:
        if row['owner'] == 'PluginAPI' and row['value_type'] in routes:
            namespace_context[row['value_type']] = row['documentation']
    for row in catalog['members']:
        context = namespace_context.get(row['owner'], '') + '\n' + row['documentation']
        editor_lines = [line for line in context.splitlines() if 'only available in' in line.lower()]
        editor_names = {'Dev Mode': 'dev', 'FigJam': 'figjam', 'Figma Design': 'figma', 'Figma Slides': 'slides', 'Figma Buzz': 'buzz', 'Buzz': 'buzz'}
        row['documented_editors'] = sorted({value for name, value in editor_names.items() if any(name in line for line in editor_lines)})
        row['required_permissions'] = sorted(set(re.findall(r'`([a-z]+)` must be specified in the permissions array', context)))
        row['restricted_access'] = bool(re.search(r'(?:This (?:is a |property.*)private API)|enablePrivatePluginApi', context, re.I))
        row['value_restrictions'] = [line.strip(' *') for line in context.splitlines()
            if re.search(r'only available to.*partner', line, re.I)]
        row['source_url'] = f'{source["repository"]}/blob/{source["ref"]}/plugin-api.d.ts#L{row["line"]}-L{row["end_line"]}'
        row['routes'] = [f'{route}.{row["name"]}' for route in routes.get(row['owner'], [])]
        row['execution'] = 'not-executed'
        row['context'] = 'Review source documentation, editorType, mode, manifest permissions and capability requirements before use.'
    nodes = []
    for name in declarations:
        if not name.endswith('Node') or declarations[name]['kind'] != 'InterfaceDeclaration':
            continue
        types = [member['signature'] for member in inherited_members(catalog, name) if member['name'] == 'type']
        nodes.append({'name': name, 'type_signatures': types,
                      'member_count': len(inherited_members(catalog, name)),
                      'extends': declarations[name]['extends']})
    catalog['nodes'] = nodes
    catalog['node_aliases'] = [row for row in catalog['declarations']
                               if row['kind'] == 'TypeAliasDeclaration' and ('Node' in row['name'] or row['name'] == 'NodeType')]
    catalog['namespaces'] = [{'interface': owner, 'routes': paths} for owner, paths in sorted(routes.items())]
    return catalog


def load():
    source = verify_source()
    catalog = json.loads(INDEX.read_text())
    if catalog['source'] != source:
        raise ValueError('Index provenance does not match pinned source; regenerate')
    return catalog


def search(catalog, query='', *, owner=None, kind=None, limit=50):
    rows = inherited_members(catalog, owner) if owner else catalog['members']
    words = query.casefold().split()
    matches = [row for row in rows if (not kind or row['kind'] == kind)
               and all(word in json.dumps(row, ensure_ascii=False).casefold() for word in words)]
    return {'evidence': catalog['evidence'], 'source': catalog['source'],
            'total': len(matches), 'rows': matches[:limit] if limit else matches,
            'declarations': [row for row in catalog['declarations']
                if all(word in ' '.join(str(row.get(key, '')) for key in ('name', 'documentation', 'signature')).casefold() for word in words)
                and (not owner or row['name'] == owner)][:limit or None]}



def coverage_sources():
    paths = sorted((ROOT / 'figma-bridge').glob('*.js'))
    bundle = json.loads((ROOT / 'library/figma-recipes/bundle.json').read_text())
    paths += [ROOT / 'library/figma-recipes' / row['entry'] for row in bundle['recipes']]
    sources = [{'path': path.relative_to(ROOT).as_posix(), 'text': path.read_text()} for path in paths]
    import workspace_recipes
    sources.append({'path': 'tools/workspace_recipes.py::dispatch_source', 'text': workspace_recipes.dispatch_source()})
    return sources


def coverage(catalog, typescript=None, sources=None):
    sources = coverage_sources() if sources is None else sources
    command = ['node', str(LIBRARY / 'scan.cjs')]
    if typescript:
        command.append(str(Path(typescript).resolve()))
    references = json.loads(subprocess.run(command, input=json.dumps(sources), check=True,
                                          capture_output=True, text=True).stdout)
    exact = {}
    generic = {}
    known_routes = {route for row in catalog['members'] for route in row['routes']}
    for reference in references:
        if reference['qualified'] in known_routes:
            exact.setdefault(reference['qualified'], []).append(reference)
        else:
            generic.setdefault(reference['name'], []).append(reference)
    rows = []
    counts = {'qualified-static-reference': 0, 'unresolved-receiver-name-reference': 0, 'no-static-reference': 0}
    for member in catalog['members']:
        qualified = [ref for route in member['routes'] for ref in exact.get(route, [])]
        unresolved = generic.get(member['name'], [])
        status = 'qualified-static-reference' if qualified else 'unresolved-receiver-name-reference' if unresolved else 'no-static-reference'
        counts[status] += 1
        rows.append({'id': member['id'], 'owner': member['owner'], 'name': member['name'],
                     'status': status, 'qualified_references': qualified,
                     'unresolved_receiver_references': unresolved,
                     'implementation': 'unverified', 'runtime_acceptance': 'unverified'})
    return {'schema': 'figma-flow-api-static-coverage-v1',
            'evidence': 'AST source occurrences only. Qualified names do not prove execution or implementation. Generic receiver names do not identify a Plugin API member. No source occurrence does not prove missing functionality.',
            'parser': {'name': 'typescript', 'version': '5.9.3'},
            'declaration_sha256': catalog['source']['files']['plugin-api.d.ts'],
            'scope': 'Top-level figma-bridge JavaScript, shipped compiled recipe entries, and generated recipe dispatcher. Excludes tests, generated panel assets, unshipped TS recipes, dynamic access and alias resolution.',
            'sources': [{'path': row['path'], 'sha256': hashlib.sha256(row['text'].encode()).hexdigest()} for row in sources],
            'counts': counts, 'members': rows}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('generate', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('--typescript', help='Path to TypeScript 5.9.3 compiler module; otherwise use local dependency')
    command = commands.add_parser('search')
    command.add_argument('query', nargs='?', default='')
    command.add_argument('--owner', help='Include this interface and inherited mixin members')
    command.add_argument('--kind')
    command.add_argument('--limit', type=int, default=50, help='0 returns all matches')
    command = commands.add_parser('route', help='Inspect a declarative route and documented context constraints; never executes it')
    command.add_argument('symbol', help='Exact path such as figma.variables.createVariable, or Interface.member')
    command.add_argument('--editor', choices=['figma', 'figjam', 'dev', 'slides', 'buzz'], required=True)
    command.add_argument('--permission', action='append', default=[])
    command = commands.add_parser('coverage', help='Report static source references, never implementation or runtime support')
    command.add_argument('--typescript')
    baseline = command.add_mutually_exclusive_group()
    baseline.add_argument('--check-baseline', action='store_true')
    baseline.add_argument('--write-baseline', action='store_true', help='Write reviewed static evidence baseline for this source tree')
    commands.add_parser('summary')
    commands.add_parser('nodes')
    args = parser.parse_args(argv)
    try:
        if args.command in ('generate', 'verify'):
            output = canonical(build(args.typescript))
            if args.command == 'verify':
                if INDEX.read_text() != output:
                    raise ValueError('Inventory differs from deterministic regeneration')
                print('Verified pinned sources and deterministic inventory')
            else:
                INDEX.write_text(output, encoding='utf-8')
                print('Generated library/figma-api/index.json')
        else:
            catalog = load()
            if args.command == 'coverage':
                result = coverage(catalog, args.typescript)
                if args.check_baseline or args.write_baseline:
                    compact = {key: value for key, value in result.items() if key != 'members'}
                    compact['members'] = [{key: row[key] for key in ('id', 'status', 'implementation', 'runtime_acceptance')} for row in result['members']]
                    if args.write_baseline:
                        (LIBRARY / 'coverage-baseline.json').write_text(canonical(compact), encoding='utf-8')
                    baseline = json.loads((LIBRARY / 'coverage-baseline.json').read_text())
                    if compact != baseline:
                        raise ValueError('Static API reference baseline differs; regenerate and review coverage-baseline.json')
                    result = {'baseline': 'written' if args.write_baseline else 'verified', 'counts': result['counts'], 'evidence': result['evidence']}
            elif args.command == 'search':
                if args.limit < 0:
                    raise ValueError('limit must be nonnegative')
                if args.owner and args.owner not in {row['name'] for row in catalog['declarations']}:
                    raise ValueError(f'Unknown interface: {args.owner}')
                result = search(catalog, args.query, owner=args.owner, kind=args.kind, limit=args.limit)
            elif args.command == 'route':
                route_owner, _, route_member = args.symbol.rpartition('.')
                matches = [row for row in catalog['members'] if args.symbol in row['routes'] or args.symbol == row['owner'] + '.' + row['name']]
                if not matches and route_owner in {row['name'] for row in catalog['declarations']}:
                    matches = [row for row in inherited_members(catalog, route_owner) if row['name'] == route_member]
                if not matches:
                    raise ValueError(f'Unknown API symbol: {args.symbol}')
                result = {'symbol': args.symbol, 'execution': 'not-executed', 'evidence': catalog['evidence'], 'routes': []}
                for row in matches:
                    blockers = []
                    if row['restricted_access']:
                        blockers.append('Restricted or private API; no public route authorized')
                    if row['documented_editors'] and args.editor not in row['documented_editors']:
                        blockers.append('Editor excluded by declaration documentation')
                    missing = sorted(set(row['required_permissions']) - set(args.permission))
                    if missing:
                        blockers.append('Missing manifest permissions: ' + ', '.join(missing))
                    result['routes'].append({'member': row, 'blockers': blockers,
                        'status': 'blocked' if blockers else 'documentation-review-required',
                        'runtime_support': 'unverified', 'invocation': 'Use the official Plugin API inside an authorized plugin context; this catalog does not dispatch commands.'})
            elif args.command == 'nodes':
                result = {'nodes': catalog['nodes'], 'aliases': catalog['node_aliases'], 'evidence': catalog['evidence']}
            else:
                result = {'source': catalog['source'], 'evidence': catalog['evidence'],
                          **{key: len(catalog[key]) for key in ('declarations', 'members', 'nodes', 'node_aliases')},
                          'namespaces': catalog['namespaces']}
            print(canonical(result), end='')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f'figma-api-inventory: {detail}\n')


if __name__ == '__main__':
    main()
