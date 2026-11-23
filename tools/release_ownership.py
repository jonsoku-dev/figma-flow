"""Shared path and relationship parsing for the repository authority Graph."""
from pathlib import PurePosixPath
import re


REGISTRY = 'release/authority.json'
COVERAGE = {'review', 'projection', 'build-projection', 'test-oracle', 'upstream', 'record', 'gate-data'}


def relative(name):
    if not isinstance(name, str) or not name or '\\' in name or '\0' in name:
        raise ValueError(f'Invalid relative path: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name or name == '.':
        raise ValueError(f'Invalid relative path: {name!r}')
    return name


def pointer_parts(pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
        raise ValueError('Invalid authority pointer.')
    return [part.replace('~1', '/').replace('~0', '~') for part in pointer[1:].split('/')]


def json_member(value, parts):
    for part in parts:
        if isinstance(value, list):
            if not part.isdecimal():
                raise ValueError(f'Invalid authority array index: {part!r}')
            value = value[int(part)]
        else:
            value = value[part]
    return value


class ReleaseOwnership:
    def __init__(self, graph):
        if graph.get('schema') != 'figma-flow-major-authority-v1':
            raise ValueError('Unknown release graph schema.')
        self.nodes = {node['id']: node for node in graph['nodes']}
        if len(self.nodes) != len(graph['nodes']) or not all(
                isinstance(key, str) and re.fullmatch(r'[a-z][a-z0-9-]*', key) for key in self.nodes):
            raise ValueError('Release graph IDs must be unique portable names.')
        self.authorities = {key: relative(node['source']) for key, node in self.nodes.items()
                            if node['type'] == 'authority'}
        self.surfaces = {key: node for key, node in self.nodes.items() if node['type'] == 'surface'}
        self.checks = {key: relative(node['source']) for key, node in self.nodes.items()
                       if node['type'] == 'check'}
        if len(self.nodes) != len(self.surfaces) + len(self.authorities) + len(self.checks) or not self.surfaces:
            raise ValueError('Invalid release graph node type or missing surfaces.')
        self.owned_by = {key: set() for key in self.surfaces}
        self.checked_by = {key: set() for key in self.surfaces}
        for edge in graph['edges']:
            kind, surface, target = edge['type'], edge['from'], edge['to']
            if kind == 'owned-by' and surface in self.surfaces and target in self.authorities:
                self.owned_by[surface].add(target)
            elif kind == 'checked-by' and surface in self.surfaces and target in self.checks:
                self.checked_by[surface].add(target)
            else:
                raise ValueError('Invalid release authority edge.')
        self.roots = {}
        for key, surface in self.surfaces.items():
            if not isinstance(surface['roots'], list) or not surface['roots'] or surface['coverage'] not in COVERAGE:
                raise ValueError('Missing roots or unsupported coverage: ' + key)
            for path in map(relative, surface['roots']):
                if path in self.roots:
                    raise ValueError('Ambiguous release graph ownership: ' + path)
                self.roots[path] = key

    def locate(self, name):
        path = PurePosixPath(name)
        return next(((self.roots[str(part)], str(part)) for part in (path, *path.parents)
                     if str(part) in self.roots), None)
