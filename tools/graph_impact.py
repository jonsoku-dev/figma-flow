"""Compare declared dependencies and source evidence for a Graph change."""

from collections import defaultdict, deque
from contextlib import contextmanager
from fnmatch import fnmatchcase
from functools import lru_cache
from graphlib import CycleError, TopologicalSorter
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory


def _identifier(value):
    return isinstance(value, str) and bool(value.strip())


def _relative_path(value):
    return (
        isinstance(value, str) and '\\' not in value and '\x00' not in value
        and ':' not in value and all(part not in {'', '.', '..'} for part in value.split('/'))
    )


def validate_graph(graph):
    """Reject malformed or contradictory declarations before analysis."""
    if not isinstance(graph, dict) or type(graph.get('schema')) is not int or graph['schema'] != 1:
        raise ValueError('Impact Graph must use schema 1')
    nodes = graph.get('nodes')
    relations = graph.get('relations')
    types = graph.get('relationTypes')
    if not isinstance(nodes, list) or not isinstance(relations, list) or not isinstance(types, dict):
        raise ValueError('Impact Graph requires nodes, relations and relationTypes')

    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not all(_identifier(node.get(key)) for key in ('id', 'kind', 'action')):
            raise ValueError('Declare a nonempty id, kind and action for every Graph node')
        node_id = node['id']
        if node_id in by_id:
            raise ValueError(f'Duplicate Graph node ID: {node_id}')
        if node.get('status') not in ('active', 'planned'):
            raise ValueError(f'Graph node {node_id} must be active or planned')
        paths = node.get('paths')
        if not isinstance(paths, list) or not all(_relative_path(path) for path in paths):
            raise ValueError(f'Graph node {node_id} must declare repository-relative paths or globs')
        if len(set(paths)) != len(paths):
            raise ValueError(f'Duplicate source path on Graph node {node_id}')
        by_id[node_id] = node

    for name, policy in types.items():
        if not _identifier(name) or not isinstance(policy, dict) or not all(
            type(policy.get(key)) is bool for key in ('impact', 'usage', 'acyclic')
        ):
            raise ValueError(f'Relation type {name!r} must declare boolean impact, usage and acyclic policies')

    keys = set()
    ordered = TopologicalSorter()
    for relation in relations:
        if not isinstance(relation, dict) or not all(_identifier(relation.get(key)) for key in ('from', 'to', 'type')):
            raise ValueError('Declare from, to and type for every Graph relation')
        key = _relation_key(relation)
        consumer, provider, relation_type = key
        if consumer not in by_id or provider not in by_id:
            raise ValueError(f'Declare both Graph nodes in relation {consumer} -> {provider}')
        if relation_type not in types:
            raise ValueError(f'Declare Graph relation type {relation_type} before using it')
        state = relation.get('state')
        if state not in ('required', 'optional', 'forbidden'):
            raise ValueError(f'Graph relation {consumer} -> {provider} must declare required, optional or forbidden')
        if key in keys:
            raise ValueError(f'Duplicate Graph relation {consumer} -> {provider} ({relation_type})')
        keys.add(key)
        if types[relation_type]['acyclic'] and state != 'forbidden':
            ordered.add(consumer, provider)
    try:
        ordered.prepare()
    except CycleError as error:
        raise ValueError('Graph relations that require an order form a cycle: ' + ' -> '.join(error.args[1])) from error


def _relation_key(relation):
    return relation['from'], relation['to'], relation['type']


def _has_glob(path):
    return any(mark in path for mark in ('*', '?', '['))


def matches_path(path, pattern):
    """Match one repository path, with ** spanning zero or more directories."""
    if not _has_glob(pattern):
        return path == pattern
    segments = tuple(pattern.split('/'))
    parts = tuple(path.split('/'))

    @lru_cache(maxsize=None)
    def match(pattern_at, path_at):
        if pattern_at == len(segments):
            return path_at == len(parts)
        if segments[pattern_at] == '**':
            return match(pattern_at + 1, path_at) or (
                path_at < len(parts) and match(pattern_at, path_at + 1)
            )
        return (
            path_at < len(parts) and fnmatchcase(parts[path_at], segments[pattern_at])
            and match(pattern_at + 1, path_at + 1)
        )

    return match(0, 0)


def _different(before, after):
    return json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True)


def _node_change(before, after, source_paths):
    if before is None:
        kind = 'added'
    elif after is None:
        kind = 'removed'
    elif _different(before, after):
        kind = 'modified'
        old_paths, new_paths = set(before['paths']), set(after['paths'])
        removed, added = old_paths - new_paths, new_paths - old_paths
        if len(removed) == len(added) == 1 and not any(map(_has_glob, removed | added)):
            kind = 'moved'
    elif source_paths:
        kind = 'source-changed'
    else:
        return None
    return {'kind': kind, 'before': before, 'after': after, 'sourcePaths': source_paths}


def _reverse_traces(relations, revision, seeds):
    dependents = defaultdict(list)
    for relation in relations:
        dependents[relation['to']].append(relation)
    for seed in sorted(seeds):
        visited = {seed}
        queue = deque([(seed, [])])
        while queue:
            node, path = queue.popleft()
            yield node, {'root': seed, 'revision': revision, 'relations': path}
            for relation in dependents[node]:
                dependent = relation['from']
                if dependent in visited:
                    continue
                visited.add(dependent)
                queue.append((dependent, path + [relation]))


def _dependency_traces(graph, revision, seeds):
    relations = [
        relation for relation in sorted(graph['relations'], key=_relation_key)
        if relation['state'] != 'forbidden' and graph['relationTypes'][relation['type']]['impact']
    ]
    return _reverse_traces(relations, revision, seeds.intersection(node['id'] for node in graph['nodes']))


def analyze_impact(base, current, changed_paths, *, observed_targets=()):
    """Return stable-ID changes, revision-local reverse traces and actions."""
    validate_graph(base)
    validate_graph(current)
    old_nodes = {node['id']: node for node in base['nodes']}
    new_nodes = {node['id']: node for node in current['nodes']}
    old_edges = {_relation_key(relation): relation for relation in base['relations']}
    new_edges = {_relation_key(relation): relation for relation in current['relations']}
    path_names = sorted(changed_paths)
    node_changes = {}
    mapped = set()
    for node_id in sorted(old_nodes.keys() | new_nodes.keys()):
        before, after = old_nodes.get(node_id), new_nodes.get(node_id)
        patterns = set((before or {}).get('paths', [])) | set((after or {}).get('paths', []))
        paths = [path for path in path_names if any(matches_path(path, pattern) for pattern in patterns)]
        mapped.update(paths)
        change = _node_change(before, after, paths)
        if change is not None:
            node_changes[node_id] = change

    relation_changes = []
    for key in sorted(old_edges.keys() | new_edges.keys()):
        before, after = old_edges.get(key), new_edges.get(key)
        old_policy = base['relationTypes'].get(key[2])
        new_policy = current['relationTypes'].get(key[2])
        policy_changed = _different(old_policy, new_policy)
        if _different(before, after) or policy_changed:
            kind = 'added' if before is None else 'removed' if after is None else 'modified'
            relation_changes.append({
                'id': key[0], 'kind': kind, 'before': before, 'after': after,
                'beforePolicy': old_policy, 'afterPolicy': new_policy,
            })

    seeds = node_changes.keys() | {change['id'] for change in relation_changes}
    observed = {'base': defaultdict(set), 'current': defaultdict(set)}
    for target in observed_targets:
        for trace in target['traces']:
            revision = trace['revision']
            for node_id in target['bindings'][revision]:
                observed[revision][node_id].add((target['path'], trace['root']))

    traces = defaultdict(list)
    for graph, revision in ((base, 'base'), (current, 'current')):
        for node_id, trace in _dependency_traces(graph, revision, seeds | observed[revision].keys()):
            origins = observed[revision].get(trace['root'], ())
            if origins:
                trace['observedOrigins'] = [{'path': path, 'root': root} for path, root in sorted(origins)]
            traces[node_id].append(trace)
    impacts = []
    for node_id, paths in sorted(traces.items()):
        before, after = old_nodes.get(node_id), new_nodes.get(node_id)
        node = after or before
        impacts.append({
            'id': node_id, 'kind': node['kind'], 'action': node['action'],
            'status': node['status'], 'paths': node['paths'], 'traces': paths,
            'before': before, 'after': after, 'removed': after is None,
        })
    return {
        'changes': {
            'nodes': node_changes, 'relations': relation_changes,
            'sources': changed_paths if isinstance(changed_paths, dict) else {path: None for path in path_names},
        },
        'impacts': impacts,
        'unmappedPaths': sorted(set(path_names) - mapped),
    }


def _observed_index(observation, types):
    if observation.get('schema') != 'figma-flow-observed-panel-v1' or not observation.get('sourceFingerprint'):
        raise ValueError('Observed impact needs source-pinned panel observations')
    sources = {
        path: {'path': path, 'origin': 'input', 'sha256': digest}
        for path, digest in observation['inputFiles'].items()
    }
    sources.update((node['path'], node) for node in observation['nodes'])
    edges = {}

    def include(origin, target, kind, mode, resolution, evidence, symbol=''):
        if (not types.get(kind, {}).get('impact') or origin not in sources or target not in sources):
            return
        key = (origin, target, kind, mode, symbol)
        if key not in edges:
            edges[key] = {'from': origin, 'to': target, 'type': kind, 'mode': mode,
                          'resolution': resolution, 'evidence': []}
            if symbol:
                edges[key]['targetSymbol'] = symbol
        edges[key]['evidence'].append(evidence)

    for edge in observation['edges']:
        if edge.get('certainty') != 'extracted':
            continue
        if (edge['type'] == 'CALLS' and edge.get('mode') == 'static-import-binding' and
                _identifier(edge.get('targetSymbol'))):
            include(edge['from'], edge['to'], edge['type'], edge['mode'], 'local',
                    {'location': edge.get('location'), 'importLocation': edge.get('importLocation'),
                     'calledAs': edge.get('symbol')}, edge['targetSymbol'])
        elif edge.get('resolution') in ('local', 'external-file', 'asset'):
            include(edge['from'], edge['to'], edge['type'], edge['mode'], edge['resolution'],
                    {'location': edge.get('location'), 'specifier': edge.get('specifier')})
    for row in observation['externalEvidence']:
        if row.get('certainty') == 'extracted':
            include(row['consumer'], row['path'], 'IMPORTS', 'external-consumer', 'external-file', row)
    for node in observation['nodes']:
        graph_input = node.get('generatedFrom')
        if node.get('origin') == 'generated' and graph_input in sources:
            include(node['path'], graph_input, 'GENERATED_FROM', 'projection', 'local',
                    {'path': graph_input, 'inputSha256': sources[graph_input]['sha256'],
                     'generatedSha256': node['sha256']})
    return sources, edges


def _observed_unknowns(observation, revision):
    yield from ({'revision': revision, **finding} for finding in observation['findings'])
    for edge in observation['edges']:
        if edge.get('importCandidate'):
            yield {
                'revision': revision, 'rule': 'call-target-unknown', 'path': edge['from'],
                'location': edge.get('location'), 'candidate': edge['importCandidate'],
            }


def analyze_observed_impact(base_observation, current_observation, changed_paths, *, base_types, current_types):
    """Explain observed file impact and keep each trace within one revision."""
    old_sources, old_edges = _observed_index(base_observation, base_types)
    new_sources, new_edges = _observed_index(current_observation, current_types)
    relation_changes = []
    seeds = set(changed_paths)
    for key in sorted(old_edges.keys() ^ new_edges.keys()):
        before, after = old_edges.get(key), new_edges.get(key)
        relation_changes.append({
            'kind': 'added' if after is not None else 'removed',
            'before': before, 'after': after,
        })
        seeds.add(key[0])

    traces = defaultdict(list)
    for revision, sources, edges in (('base', old_sources, old_edges), ('current', new_sources, new_edges)):
        for target, trace in _reverse_traces(
            (edges[key] for key in sorted(edges)), revision, seeds.intersection(sources)
        ):
            traces[target].append(trace)
    return {
        'base': {key: base_observation[key] for key in ('sourceFingerprint', 'extractor')},
        'current': {key: current_observation[key] for key in ('sourceFingerprint', 'extractor')},
        'relationChanges': relation_changes,
        'targets': [
            {'path': target, 'before': old_sources.get(target), 'after': new_sources.get(target),
             'traces': paths}
            for target, paths in sorted(traces.items())
        ],
        'unknown': [
            finding
            for revision, observation in (('base', base_observation), ('current', current_observation))
            for finding in _observed_unknowns(observation, revision)
        ],
    }


def _git(root, *args):
    return subprocess.run(
        ['git', '--no-optional-locks', '--no-replace-objects', '-C', str(root), *args],
        capture_output=True, check=True,
    ).stdout


def _nul_items(raw):
    return raw.removesuffix(b'\0').split(b'\0') if raw else []


def _read_chunks(source, size=None):
    while size is None or size > 0:
        chunk = source.read(65536 if size is None else min(size, 65536))
        if not chunk:
            if size is not None:
                raise ValueError('Git blob ended before the declared size')
            break
        yield chunk
        if size is not None:
            size -= len(chunk)


def _digest_stream(source, size=None):
    digest = sha256()
    for chunk in _read_chunks(source, size):
        digest.update(chunk)
    return digest.hexdigest()


def _visit_blobs(root, items, read):
    command = ['git', '--no-optional-locks', '--no-replace-objects', '-C', str(root), 'cat-file', '--batch']
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        for key, object_id in items:
            process.stdin.write(object_id + b'\n')
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3 or header[:2] != [object_id, b'blob']:
                raise ValueError(f'Expected a Git blob for {object_id.decode("ascii")}')
            value = read(key, process.stdout, int(header[2]))
            if process.stdout.read(1) != b'\n':
                raise ValueError('Missing delimiter after Git blob')
            yield key, value
        process.stdin.close()
        if process.wait() != 0:
            raise subprocess.CalledProcessError(process.returncode, command)


def _blobs(root, items):
    if not items:
        return {}
    object_ids = sorted({object_id for _, object_id in items.values()})
    objects = dict(_visit_blobs(root, ((value, value) for value in object_ids),
                               lambda _, source, size: _digest_stream(source, size)))
    return {
        path: {'mode': mode.decode('ascii'), 'sha256': objects[object_id]}
        for path, (mode, object_id) in items.items()
    }


def _tree_entries(root, base):
    for entry in _nul_items(_git(root, 'ls-tree', '-rz', base)):
        fields, name = entry.split(b'\t', 1)
        mode, kind, object_id = fields.split()
        yield os.fsdecode(name), mode, kind, object_id


def _tree_blobs(root, base, paths):
    items = {path: (mode, object_id) for path, mode, kind, object_id in _tree_entries(root, base)
             if path in paths and kind == b'blob'}
    return _blobs(root, items)


@contextmanager
def panel_base_snapshot(root, base, paths):
    """Stage selected regular files from an exact Git commit for the panel observer."""
    root = Path(root).resolve(strict=True)
    ref = _git(root, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}').strip().decode('ascii')
    patterns = set(paths)
    if not patterns or not all(_relative_path(path) for path in patterns):
        raise ValueError('Panel baseline requires repository-relative input paths')
    items = {}
    for name, mode, kind, object_id in _tree_entries(root, ref):
        if any(matches_path(name, pattern) for pattern in patterns):
            if not _relative_path(name) or kind != b'blob' or mode not in (b'100644', b'100755'):
                raise ValueError(f'Cannot observe a non-regular panel baseline input: {name}')
            items[name] = object_id

    with TemporaryDirectory(prefix='figma-flow-panel-base-') as directory:
        checkout = Path(directory).resolve()

        def copy_blob(name, source, size):
            path = checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as sink:
                for chunk in _read_chunks(source, size):
                    sink.write(chunk)

        for _ in _visit_blobs(root, sorted(items.items()), copy_blob):
            pass
        modules = Path('panel-ui/node_modules')
        if (root / modules).is_dir():
            target = checkout / modules
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(root / modules, target_is_directory=True)
        yield checkout


def _index_blobs(root, paths):
    items = {}
    for entry in _nul_items(_git(root, 'ls-files', '-sz')):
        fields, name = entry.split(b'\t', 1)
        mode, object_id, stage = fields.split()
        path = os.fsdecode(name)
        if path in paths and mode != b'160000':
            if stage != b'0':
                raise ValueError(f'Cannot produce source evidence for unmerged path {path}')
            items[path] = (mode, object_id)
    return _blobs(root, items)


def _working_blob(root, name):
    path = root / name
    if any((root / parent).is_symlink() for parent in Path(name).parents):
        return None
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            return {'mode': '120000', 'sha256': sha256(os.fsencode(os.readlink(path))).hexdigest()}
        if stat.S_ISREG(mode):
            with path.open('rb') as source:
                return {'mode': '100755' if mode & stat.S_IXUSR else '100644', 'sha256': _digest_stream(source)}
    except (FileNotFoundError, NotADirectoryError):
        return None
    return None


def _move_candidates(changes):
    removed = defaultdict(list)
    added = defaultdict(list)
    for path, record in changes.items():
        before, after = record['before'], record['after']
        if before is not None and after is None:
            removed[before['mode'], before['sha256']].append(path)
        if before is None and after is not None:
            added[after['mode'], after['sha256']].append(path)
    for key in removed.keys() & added.keys():
        old_paths, new_paths = removed[key], added[key]
        if len(old_paths) == len(new_paths) == 1:
            previous, current = old_paths[0], new_paths[0]
            changes[previous]['moveCandidate'] = {'to': current, 'evidence': 'identical-bytes-and-mode'}
            changes[current]['moveCandidate'] = {'from': previous, 'evidence': 'identical-bytes-and-mode'}
        else:
            for path in old_paths + new_paths:
                changes[path]['moveCandidate'] = {
                    'evidence': 'ambiguous-identical-bytes-and-mode', 'removed': old_paths, 'added': new_paths,
                }


def changed_paths(root, base_ref):
    """Compare the base commit, index and working tree using actual source bytes."""
    root = Path(root).resolve(strict=True)
    base = _git(root, 'rev-parse', '--verify', '--end-of-options', base_ref + '^{commit}').strip().decode('ascii')
    options = ('--name-only', '--no-renames', '--no-ext-diff', '--no-textconv', '-z', base, '--')
    worktree = _git(root, '-c', 'core.fileMode=true', '-c', 'diff.autoRefreshIndex=false', 'diff', *options)
    staged = _git(root, 'diff', '--cached', *options)
    untracked = _git(root, 'ls-files', '--others', '--exclude-standard', '-z')
    names = {os.fsdecode(path) for data in (worktree, staged, untracked) for path in _nul_items(data)}
    previous = _tree_blobs(root, base, names)
    index = _index_blobs(root, names)
    changes = {}
    for path in sorted(names):
        before, after = previous.get(path), _working_blob(root, path)
        staged = index.get(path)
        if before == after == staged:
            continue
        if after == before:
            kind = 'staged-only'
        elif before is None:
            kind = 'added'
        elif after is None:
            kind = 'removed'
        else:
            kind = 'modified'
        changes[path] = {'kind': kind, 'before': before, 'after': after, 'staged': staged}
    _move_candidates(changes)
    return changes
