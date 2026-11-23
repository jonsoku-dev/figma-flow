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
from development_witnesses import witness_index
from graph_impact import changed_paths, intent_to_add_paths, read_git as git, read_git_blobs
from release_ownership import REGISTRY, ReleaseOwnership, json_member, pointer_parts, relative

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    '@biomejs/biome': 'biome.json',
    'oxlint': '.oxlintrc.json',
    'knip': 'knip.config.mjs',
}


def names(raw):
    return [os.fsdecode(name) for name in raw.rstrip(b'\0').split(b'\0') if name]


def linked_parent(root, path):
    return any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root))


def working_bytes(root, name):
    path = root / relative(name)
    if path.is_symlink() or linked_parent(root, path):
        raise ValueError(f'Symbolic link is not an authority input: {name}')
    return path.read_bytes()


class RevisionReader:
    def __init__(self, root, objects, blob_cache):
        self.root = root
        self.objects = objects
        self.blob_cache = blob_cache
        self.working_cache = {}

    def prefetch(self, paths):
        if self.objects is None:
            return
        needed = {oid for path in paths if (entry := self.objects.get(path)) is not None
                  for mode, oid in (entry,) if mode in ('100644', '100755')}
        self.blob_cache.update(read_git_blobs(self.root, needed - self.blob_cache.keys()))

    def __call__(self, name):
        relative(name)
        if self.objects is None:
            if name not in self.working_cache:
                self.working_cache[name] = working_bytes(self.root, name)
            return self.working_cache[name]
        if name not in self.objects:
            raise FileNotFoundError(name)
        mode, oid = self.objects[name]
        if mode not in ('100644', '100755'):
            raise ValueError(f'Authority or evidence is not a regular Git file: {name}')
        if oid not in self.blob_cache:
            self.prefetch([name])
        return self.blob_cache[oid]

    def verify_working_inputs(self):
        for name, observed in self.working_cache.items():
            if observed != working_bytes(self.root, name):
                raise ValueError(f'Working evidence drifted during developer analysis: {name}')


def snapshot(read, files):
    if REGISTRY not in files:
        return None
    source = read(REGISTRY)
    index = ReleaseOwnership(decode_json(source))
    inputs = {REGISTRY: sha256(source).hexdigest()}
    authorities = defaultdict(list)
    consumers = defaultdict(list)
    for key, name in index.authorities.items():
        authorities[name].append(key)
        membership = index.nodes[key].get('members')
        if membership is None or name not in files:
            continue
        source = read(name)
        inputs[name] = sha256(source).hexdigest()
        value = json_member(decode_json(source), pointer_parts(membership['pointer']))
        if not isinstance(value, list):
            raise ValueError(f'Authority member index must be an array: {name}')
        for record in value:
            member = relative(record[membership['pathField']])
            authorities[member].append(key)
    for surface, keys in index.owned_by.items():
        for key in keys:
            consumers[key].append(surface)
    checks = defaultdict(list)
    for key, name in index.checks.items():
        checks[name].append(key)
    return {'index': index, 'inputs': inputs, 'authorities': authorities,
            'readers': consumers, 'checks': checks}


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


def git_tree(root, base):
    result = {}
    for entry in names(git(root, 'ls-tree', '-r', '-z', base)):
        fields, path = entry.split('\t', 1)
        mode, _, oid = fields.split()
        result[path] = (mode, oid)
    return result


def current_inventory(root):
    intents = intent_to_add_paths(root)
    objects = {}
    for entry in names(git(root, 'ls-files', '--stage', '-z')):
        fields, path = entry.split('\t', 1)
        mode, oid, stage = fields.split()
        if stage != '0':
            raise ValueError(f'Resolve the unmerged Git index path before analyzing: {path}')
        if path not in intents:
            objects[path] = (mode, oid)
    index_links = {name for name, (mode, _) in objects.items() if mode == '160000'}
    masked = {line[2:] for line in names(git(root, 'ls-files', '-v', '-z')) if line[0].islower() or line[0] == 'S'}
    candidates = set(names(git(root, 'ls-files', '-co', '--exclude-standard', '-z'))) - index_links
    directories = {name for name in candidates if name.endswith('/')}
    candidates -= directories
    external = {name for name in candidates if linked_parent(root, root / name)}
    work_files = {name for name in candidates - external if (root / name).is_file() or (root / name).is_symlink()}
    return {'index': objects, 'intentToAdd': intents, 'working': work_files,
            'notInspected': {'maskedWorkingPaths': sorted(masked), 'submodules': sorted(index_links),
                             'uninspectedDirectories': sorted(name.rstrip('/') for name in directories),
                             'symlinkedWorkingPaths': sorted(external)}}


def missing_sources(registry, files):
    if registry is None:
        return [{'rule': 'authority-graph-unavailable', 'path': REGISTRY}]
    findings = []
    for name, authorities in registry['authorities'].items():
        affected = {surface for key in authorities for surface in registry['readers'][key]}
        if affected and name not in files:
            findings.append({'rule': 'missing-authority-source', 'path': name, 'surfaces': sorted(affected)})
    for surface, checks in registry['index'].checked_by.items():
        for check in sorted(checks):
            name = registry['index'].checks[check]
            if name not in files:
                findings.append({'rule': 'missing-check-source', 'path': name, 'surfaces': [surface]})
    return sorted(findings, key=lambda row: (row['rule'], row['path'], row.get('surfaces', ())))


def witness_dependents(witnesses, name):
    direct = {key: index.dependencies(name) for key, index in witnesses.items()}
    by_revision = {key: list(rows) for key, rows in direct.items()}
    for key, earlier in (('index', ('base',)), ('working', ('index', 'base'))):
        index = witnesses.get(key)
        if index is None:
            continue
        known = [(revision, row) for revision in earlier for row in direct.get(revision, ())
                 if row.get('test') == name]
        for revision, prior in known:
            covered = set(prior['coveredPaths'])
            for row in by_revision[key]:
                if row.get('test') == name and row['surface'] == prior['surface']:
                    covered.difference_update(row['coveredPaths'])
            if not covered:
                continue
            unavailable = next((row for source in (prior['witness'], prior['review'])
                                for row in index.dependencies(source)
                                if row['surface'] == prior['surface'] and row['status'] == 'needs-review'
                                and (source == prior['witness'] or not row['coveredPaths'])), None)
            if unavailable:
                by_revision[key].append({**prior, 'coveredPaths': sorted(covered), 'status': 'needs-review',
                                         'basis': 'prior-witness', 'basisRevision': revision,
                                         'reason': unavailable['reason']})
    return {key: rows for key, rows in by_revision.items() if rows}


def analyze(root, base, inventory=False, run_tools=False):
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    base = git(root, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}').decode().strip()
    start = current_inventory(root)
    changes = changed_paths(root, base, intent_to_add=start['intentToAdd'])
    old_tree = git_tree(root, base)
    old_links = {name for name, (mode, _) in old_tree.items() if mode == '160000'}
    excluded = {**start['notInspected'], 'submodules': sorted(old_links | set(start['notInspected']['submodules']))}
    work_files = start['working']
    revisions = {'base': set(old_tree) - old_links,
                 'index': set(start['index']) - set(start['notInspected']['submodules']),
                 'working': work_files}
    blob_cache = {}
    readers = {key: RevisionReader(root, tree, blob_cache) for key, tree in
               (('base', old_tree), ('index', start['index']), ('working', None))}
    registries = {key: snapshot(readers[key], files) for key, files in revisions.items()}
    moved_ownership = set()
    input_sets = {key: registry['inputs'] if registry else None for key, registry in registries.items()}
    if input_sets['base'] != input_sets['index'] or input_sets['index'] != input_sets['working']:
        for path in set().union(*revisions.values()):
            before, index, working = [route(path, registries[key]) if path in files else None
                                      for key, files in revisions.items()]
            present = [row for row in (before, index, working) if row is not None]
            if any(row != present[0] for row in present[1:]):
                moved_ownership.add(path)
    witnesses = {}
    if changes or moved_ownership:
        for key, registry in registries.items():
            if registry is not None:
                files = revisions[key]
                readers[key].prefetch(path for path in files if path.startswith('release/reviews/') and path.endswith('.json'))
                witnesses[key] = witness_index(readers[key], files, registry['index'].surfaces)
    findings = {key: missing_sources(registry, revisions[key]) for key, registry in registries.items()}
    rows, per_surface = {}, defaultdict(lambda: defaultdict(set))
    for name in sorted(changes.keys() | moved_ownership):
        change = changes.get(name, {'kind': 'ownership-changed'})
        locations = {}
        for key, files in revisions.items():
            if name not in files:
                continue
            location = locations[key] = route(name, registries[key])
            if owner := location.get('owner'):
                surface = owner['surface']
                per_surface[key][surface].add(name)
                if owner['role'] == 'review' and key in witnesses:
                    decision = location['witnesses'] = witnesses[key].for_path(name, surface)
                    if decision['status'] == 'needs-review':
                        findings[key].append({'rule': 'invalid-file-witness', 'path': name, 'surfaces': [surface],
                                              'reason': decision.get('reason', 'Review the declared checks.')})
            for surface in location.get('declaredConsumers', ()):
                per_surface[key][surface].add(name)
        dependencies = witness_dependents(witnesses, name)
        for key, found in dependencies.items():
            for dependency in found:
                surface = dependency['surface']
                per_surface[key][surface].add(name)
                if dependency['status'] == 'needs-review':
                    findings[key].append({'rule': 'invalid-dependent-witness', 'path': name, 'surfaces': [surface],
                                          'reason': dependency.get('reason', 'Refresh the declared witness.')})
        rows[name] = {**change, 'revisions': locations, 'witnessDependents': dependencies}

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
                                          'status': 'surface-declaration' if index.checks[check] in revisions[key]
                                          else 'missing-source'}
                                         for check in sorted(index.checked_by[surface])],
                      'status': 'check-candidates' if index.checked_by[surface] else 'no-surface-check'}
            for surface, sources in sorted(surfaces.items())}

    missing = [name for name, row in rows.items() if not row['revisions'] or
               any(item['status'] != 'mapped' for item in row['revisions'].values())]
    report = {'schema': 'figma-flow-development-changes-v1', 'base': base, 'head': head,
              'authoritySnapshots': input_sets, 'surfaceDefinitionsChanged': definitions_changed,
              'changes': rows, 'surfaces': surface_reports, 'unmapped': missing, 'notInspected': excluded,
              'findings': findings}
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
    end = current_inventory(root)
    if end != start or changed_paths(root, base, intent_to_add=end['intentToAdd']) != changes:
        raise ValueError('Git changes drifted during developer analysis. Rerun on the current snapshot.')
    readers['working'].verify_working_inputs()
    report['status'] = 'review-required' if (missing or any(excluded.values()) or any(v is None for v in registries.values())
                            or findings['index'] or findings['working']
                            or report.get('inventory', {}).get('unmapped')) else 'ownership-mapped'
    return report


def print_report(report):
    print(f'Development changes {report["base"][:12]} → {report["head"][:12]}: {report["status"]}')
    for name, change in report['changes'].items():
        routes = ', '.join(f'{rev}={(item.get("owner") or {}).get("surface", item["status"])}'
                           for rev, item in change['revisions'].items())
        intent = ' (intent-to-add)' if change.get('intentToAdd') and change['kind'] != 'intent-to-add' else ''
        print(f'  {json.dumps(name, ensure_ascii=False)} {change["kind"]}{intent} {routes}')
        for rev, location in change['revisions'].items():
            witness = location.get('witnesses')
            if not witness:
                continue
            print(f'    {rev} file-specific checks: {witness["status"]}')
            for check in witness['checks']:
                print(f'      {check["test"]} ({check["testStatus"]})')
        for rev, dependencies in change['witnessDependents'].items():
            for surface in sorted({row['surface'] for row in dependencies}):
                paths = sorted({path for row in dependencies if row['surface'] == surface for path in row['coveredPaths']})
                print(f'    {rev} witness impact: {surface}, {len(paths)} covered paths')
                for path in paths[:8]:
                    print(f'      {json.dumps(path, ensure_ascii=False)}')
                if len(paths) > 8:
                    print(f'      {len(paths) - 8} more in --json')
    if 'inventory' in report:
        entry = report['inventory']
        print(f'  Inventory: {entry["files"]} files, {len(entry["bySurface"])} surfaces, {len(entry["unmapped"])} unmapped')
        for path in entry['unmapped']:
            print(f'    Unmapped: {json.dumps(path, ensure_ascii=False)}')
    for limit, paths in report['notInspected'].items():
        for path in paths:
            print(f'  {limit}: {json.dumps(path, ensure_ascii=False)}')
    for rev, surfaces in report['surfaces'].items():
        for surface, group in sorted(surfaces.items()):
            candidates = ', '.join(f'{check["path"]} ({check["status"]})' for check in group['declaredChecks'])
            print(f'  {rev} {surface}: {candidates or "no declared surface check"}')
    for rev, findings in report['findings'].items():
        for item in findings:
            print(f'  {rev} {item["rule"]}: {item["path"]} {item.get("reason", "")}'.rstrip())
    print(f'  Biome / Oxlint / Knip (panel-ui): {report["panelTools"]["status"]}')
    for name, tool in report['panelTools']['tools'].items():
        print(f'    {name}: {tool["status"]} (pinned {tool["pinned"]}, installed {tool["installed"]})')


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
            print_report(report)
        return int(report['status'] == 'review-required' or (args.panel_tools and report['panelTools']['status'] != 'passed'))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, IndexError) as error:
        parser.exit(2, f'Development analysis: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
