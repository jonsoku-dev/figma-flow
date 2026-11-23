#!/usr/bin/env python3
"""Explain local Git changes using the existing repository authority Graph."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True

from graph_document import decode_json
from graph_impact import changed_paths
from release_ownership import REGISTRY, ReleaseOwnership, json_member, pointer_parts, relative

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    '@biomejs/biome': 'biome.json',
    'oxlint': '.oxlintrc.json',
    'knip': 'knip.config.mjs',
}


def git(root, *args):
    return subprocess.run(['git', '--no-optional-locks', '--no-replace-objects', *args], cwd=root,
                          capture_output=True, check=True).stdout


def names(raw):
    return [os.fsdecode(name) for name in raw.rstrip(b'\0').split(b'\0') if name]


def linked_parent(root, path):
    return any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root))


def working_bytes(root, name):
    path = root / relative(name)
    if path.is_symlink() or linked_parent(root, path):
        raise ValueError(f'Symbolic link is not an authority input: {name}')
    return path.read_bytes()


def read_at(root, revision, name):
    return git(root, 'show', '--no-textconv', f'{revision}:{relative(name)}') if revision is not None else working_bytes(root, name)


def snapshot(root, revision, files):
    if REGISTRY not in files:
        return None
    source = read_at(root, revision, REGISTRY)
    index = ReleaseOwnership(decode_json(source))
    inputs = {REGISTRY: sha256(source).hexdigest()}
    authorities = defaultdict(list)
    readers = defaultdict(list)
    for key, name in index.authorities.items():
        authorities[name].append(key)
        membership = index.nodes[key].get('members')
        if membership is None:
            continue
        if name not in files:
            raise ValueError(f'Authority member registry is absent: {name}')
        source = read_at(root, revision, name)
        inputs[name] = sha256(source).hexdigest()
        value = json_member(decode_json(source), pointer_parts(membership['pointer']))
        if not isinstance(value, list):
            raise ValueError(f'Authority member index must be an array: {name}')
        for record in value:
            member = relative(record[membership['pathField']])
            authorities[member].append(key)
    for surface, keys in index.owned_by.items():
        for key in keys:
            readers[key].append(surface)
    checks = defaultdict(list)
    for key, name in index.checks.items():
        checks[name].append(key)
    return {'index': index, 'inputs': inputs, 'authorities': authorities,
            'readers': readers, 'checks': checks}


def route(name, registry):
    if registry is None:
        return {'status': 'authority-unavailable'}
    index = registry['index']
    owner = index.locate(name)
    keys = sorted(set(registry['authorities'].get(name, ())))
    checks = sorted(registry['checks'].get(name, ()))
    affected = {surface for key in keys for surface in registry['readers'][key]}
    affected.update(surface for surface, ids in index.checked_by.items() if ids.intersection(checks))
    return {'status': 'mapped' if owner else 'unmapped',
            'owner': {'surface': owner[0], 'root': owner[1],
                      'role': index.surfaces[owner[0]]['coverage']} if owner else None,
            'authorityIds': keys, 'checkIds': checks, 'declaredConsumers': sorted(affected)}


def historical_witnesses(root, revision, files, path, surface, cache):
    def load(name):
        if (revision, name) not in cache:
            raw = read_at(root, revision, name)
            cache[(revision, name)] = (sha256(raw).hexdigest(), decode_json(raw))
        return cache[(revision, name)]

    review_path = f'release/reviews/{surface}.json'
    if review_path not in files:
        return {'status': 'no-file-witness', 'checks': []}
    checks = []
    try:
        _, review = load(review_path)
        if review['schema'] != 'figma-flow-major-review-v1' or review['surface'] != surface:
            raise ValueError(f'Unexpected review scope: {review_path}')
        for binding in review['bindings']:
            if path not in binding['files']:
                continue
            authority = binding['authority']
            for witness in binding['witnesses']:
                source = relative(witness['path'])
                if source not in files:
                    raise ValueError(f'Mapped witness file is absent: {source}')
                stamp, evidence = load(source)
                if stamp != witness['sha256']:
                    raise ValueError(f'Mapped witness file differs from its declaration: {source}')
                if evidence['surfaceFingerprint'] != review['fingerprint'] or evidence['status'] != 'passed':
                    raise ValueError(f'Mapped witness is incomplete or bound to another review: {source}')
                for check in evidence['checks']:
                    if path in check['covers'] and authority == check['authority']:
                        test = relative(check['test'])
                        checks.append({'test': test, 'case': check['case'], 'authority': authority,
                                       'witness': source, 'expectedTestSha256': check['testSha256'],
                                       'testPresent': test in files})
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError, IndexError) as error:
        return {'status': 'needs-review', 'reason': str(error), 'checks': []}
    return {'status': 'historical-candidates' if checks else 'no-file-witness', 'checks': checks}


def panel_tools(root, run_tools):
    project = 'panel-ui'
    manifest = f'{project}/package.json'
    try:
        pins = decode_json(working_bytes(root, manifest)).get('devDependencies', {})
    except FileNotFoundError:
        return {'scope': project, 'status': 'not-configured', 'tools': {}}
    tools = {}
    for name, config in TOOLS.items():
        path = f'{project}/{config}'
        try:
            installed = decode_json((root / project / 'node_modules' / name / 'package.json').read_bytes())['version']
        except (OSError, ValueError, KeyError, TypeError):
            installed = None
        pinned, configured = pins.get(name), (root / path).is_file()
        status = ('not-configured' if not pinned or not configured else 'not-installed' if not installed
                  else 'ready' if installed == pinned else 'version-mismatch')
        tools[name] = {'pinned': pinned, 'installed': installed, 'configuration': path, 'status': status}
    result = {'scope': project, 'status': 'not-run', 'tools': tools}
    if run_tools:
        if any(tool['status'] != 'ready' for tool in tools.values()):
            result['status'] = 'unavailable'
            return result
        import graph_governance as gate

        try:
            policy = gate.read_json(root / gate.POLICY)
            graph = gate.bind_graph(gate.read_json(root / gate.GRAPH), policy)
            start = gate.snapshot(root, graph)
            evidence, findings = gate.quality_proof(root)
            current = gate.snapshot(root, graph)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            result.update(status='unavailable', reason=str(error))
            return result
        result.update(status='changed-during-check' if start != current else 'failed' if findings else 'passed',
                      evidence=evidence, findings=findings, before=start, after=current)
    return result


def declared_surfaces(registry):
    if registry is None:
        return {}
    index = registry['index']
    return {key: {'role': node['coverage'], 'roots': sorted(node['roots']),
                  'authorities': {owner: index.authorities[owner] for owner in sorted(index.owned_by[key])},
                  'checks': {control: index.checks[control] for control in sorted(index.checked_by[key])}}
            for key, node in index.surfaces.items()}


def analyze(root, base, inventory=False, run_tools=False):
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    base = git(root, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}').decode().strip()
    changes = changed_paths(root, base)
    old_tree = names(git(root, 'ls-tree', '-r', '-z', base))
    old_links = {entry.split('\t', 1)[1] for entry in old_tree if entry.startswith('160000 ')}
    base_files = {entry.split('\t', 1)[1] for entry in old_tree} - old_links
    staged = names(git(root, 'ls-files', '--stage', '-z'))
    index_files = {record.split('\t', 1)[1] for record in staged if not record.startswith('160000 ')}
    index_links = {record.split('\t', 1)[1] for record in staged if record.startswith('160000 ')}
    masked = [line[2:] for line in names(git(root, 'ls-files', '-v', '-z')) if line[0].islower() or line[0] == 'S']
    candidate_files = set(names(git(root, 'ls-files', '-co', '--exclude-standard', '-z'))) - index_links
    directories = {name for name in candidate_files if name.endswith('/')}
    candidate_files -= directories
    external = {name for name in candidate_files if linked_parent(root, root / name)}
    excluded = {'maskedWorkingPaths': sorted(set(masked)), 'submodules': sorted(old_links | index_links),
                'uninspectedDirectories': sorted(name.rstrip('/') for name in directories),
                'symlinkedWorkingPaths': sorted(external)}
    work_files = {name for name in candidate_files - external if (root / name).is_file() or (root / name).is_symlink()}
    revisions = {'base': (base, base_files), 'index': ('', index_files), 'working': (None, work_files)}
    registries = {key: snapshot(root, revision, files) for key, (revision, files) in revisions.items()}
    moved_ownership = set()
    input_sets = {key: registry['inputs'] if registry else None for key, registry in registries.items()}
    if input_sets['base'] != input_sets['index'] or input_sets['index'] != input_sets['working']:
        for path in base_files | index_files | work_files:
            before, index, working = [route(path, registries[key]) if path in revisions[key][1] else None for key in revisions]
            present = [row for row in (before, index, working) if row is not None]
            if any(row != present[0] for row in present[1:]):
                moved_ownership.add(path)
    rows, per_surface, cache = {}, defaultdict(lambda: defaultdict(set)), {}
    for name in sorted(changes.keys() | moved_ownership):
        change = changes.get(name, {'kind': 'ownership-changed'})
        locations = {}
        for key, (revision, files) in revisions.items():
            if name not in files:
                continue
            location = locations[key] = route(name, registries[key])
            if owner := location.get('owner'):
                surface = owner['surface']
                per_surface[key][surface].add(name)
                if owner['role'] == 'review':
                    location['witnesses'] = historical_witnesses(root, revision, files, name, surface, cache)
            for surface in location.get('declaredConsumers', ()):
                per_surface[key][surface].add(name)
        rows[name] = {**change, 'revisions': locations}

    definitions = {key: declared_surfaces(value) for key, value in registries.items()}
    definitions_changed = {}
    for surface in sorted(set().union(*(rows.keys() for rows in definitions.values()))):
        revised = {key: rows.get(surface) for key, rows in definitions.items()}
        if revised['base'] != revised['index'] or revised['index'] != revised['working']:
            definitions_changed[surface] = revised
            for key, value in revised.items():
                if value is not None:
                    per_surface[key][surface].add(REGISTRY)
    surface_reports = {}
    for key, surfaces in per_surface.items():
        index = registries[key]['index']
        surface_reports[key] = {
            surface: {'reasons': sorted(sources),
                      'declaredChecks': [{'path': index.checks[check],
                                          'status': 'surface-declaration' if index.checks[check] in revisions[key][1]
                                          else 'missing-source'}
                                         for check in sorted(index.checked_by[surface])],
                      'status': 'check-candidates' if index.checked_by[surface] else 'no-surface-check'}
            for surface, sources in sorted(surfaces.items())}

    missing = [name for name, row in rows.items() if not row['revisions'] or
               any(item['status'] != 'mapped' for item in row['revisions'].values())]
    report = {'schema': 'figma-flow-development-changes-v1', 'base': base, 'head': head,
              'authoritySnapshots': input_sets, 'surfaceDefinitionsChanged': definitions_changed,
              'changes': rows, 'surfaces': surface_reports, 'unmapped': missing, 'notInspected': excluded}
    if inventory:
        counts, unowned = Counter(), []
        for name in sorted(work_files):
            found = registries['working']['index'].locate(name) if registries['working'] else None
            if found:
                counts[found[0]] += 1
            else:
                unowned.append(name)
        report['inventory'] = {'files': len(work_files), 'bySurface': dict(sorted(counts.items())), 'unmapped': unowned}
    report['panelTools'] = panel_tools(root, run_tools)
    if head != git(root, 'rev-parse', 'HEAD').decode().strip():
        raise ValueError('HEAD changed during developer analysis.')
    if changed_paths(root, base) != changes:
        raise ValueError('Git changes drifted during developer analysis. Rerun on the current snapshot.')
    report['status'] = 'review-required' if (missing or any(excluded.values()) or any(v is None for v in registries.values())
                            or report.get('inventory', {}).get('unmapped')) else 'ownership-mapped'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--base', default='HEAD')
    parser.add_argument('--inventory', action='store_true', help='Also list ownership of the whole local checkout')
    parser.add_argument('--panel-tools', action='store_true', help='Run the existing local panel quality checks')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        requested = args.repo.resolve(strict=True)
        root = Path(os.fsdecode(git(requested, 'rev-parse', '--show-toplevel').rstrip(b'\n'))).resolve(strict=True)
        report = analyze(root, args.base, args.inventory, args.panel_tools)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=True))
        else:
            print(f'Development changes {report["base"][:12]} → {report["head"][:12]}: {report["status"]}')
            for name, change in report['changes'].items():
                routes = ', '.join(f'{rev}={(item.get("owner") or {}).get("surface", item["status"])}'
                                   for rev, item in change['revisions'].items())
                print(f'  {json.dumps(name, ensure_ascii=False)} {change["kind"]} {routes}')
                chosen = next((change['revisions'][rev] for rev in ('working', 'index', 'base')
                               if rev in change['revisions']), {})
                witness = chosen.get('witnesses')
                if witness and witness['checks']:
                    suggested = ', '.join(sorted({check['test'] for check in witness['checks'] if check['testPresent']}))
                    if suggested:
                        print(f'    Historical check candidates: {suggested}')
                elif witness:
                    print(f'    File-specific check: {witness["status"]}')
            if 'inventory' in report:
                entry = report['inventory']
                print(f'  Inventory: {entry["files"]} files, {len(entry["bySurface"])} surfaces, {len(entry["unmapped"])} unmapped')
                for path in entry['unmapped']:
                    print(f'    Unmapped: {json.dumps(path, ensure_ascii=False)}')
            for limit, paths in report['notInspected'].items():
                for path in paths:
                    print(f'  {limit}: {json.dumps(path, ensure_ascii=False)}')
            groups = {}
            for rev in ('base', 'index', 'working'):
                groups.update(report['surfaces'].get(rev, {}))
            for surface, group in sorted(groups.items()):
                candidates = ', '.join(f'{check["path"]} ({check["status"]})' for check in group['declaredChecks'])
                print(f'  {surface}: {candidates or "no declared surface check"}')
            print(f'  Biome / Oxlint / Knip (panel-ui): {report["panelTools"]["status"]}')
            for name, tool in report['panelTools']['tools'].items():
                print(f'    {name}: {tool["status"]} (pinned {tool["pinned"]}, installed {tool["installed"]})')
        return int(report['status'] == 'review-required' or (args.panel_tools and report['panelTools']['status'] != 'passed'))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, IndexError) as error:
        parser.exit(2, f'Development analysis: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
