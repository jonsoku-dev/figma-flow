#!/usr/bin/env python3
"""Resolve canonical graph tokens and export their exact values for native/web use."""
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
import tempfile


class LoadedGraph(dict):
    """Graph data carrying the hash of the exact source bytes, outside its schema."""


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def load_graph(path):
    raw = Path(path).read_bytes()
    graph = LoadedGraph(json.loads(raw))
    graph.source_sha256 = hashlib.sha256(raw).hexdigest()
    return graph


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_value(kind, value, name):
    if kind == 'FLOAT':
        valid = _number(value)
    elif kind == 'STRING':
        valid = isinstance(value, str) and bool(value.strip()) and all(ord(c) >= 32 for c in value)
    elif kind == 'COLOR':
        valid = (isinstance(value, dict) and set('rgb') <= set(value) <= set('rgba') and
                 all(_number(value[c]) and 0 <= value[c] <= 1 for c in 'rgb') and
                 _number(value.get('a', 1)) and value.get('a', 1) == 1)
    else:
        valid = False
    if not valid:
        raise ValueError(f'invalid {kind} token value: {name}')


_FLOAT_PROPERTIES = {'fontSize', 'paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom',
                     'gap', 'borderWidth', 'borderRadius', 'width', 'height', 'minWidth', 'minHeight'}
_COLOR_PROPERTIES = {'color', 'backgroundColor', 'borderColor'}
SUPPORTED_PROPERTY_TYPES = {**dict.fromkeys(_FLOAT_PROPERTIES, 'FLOAT'),
                            **dict.fromkeys(_COLOR_PROPERTIES, 'COLOR'), 'fontFamily': 'STRING'}


def _validate_property(prop, kind, value):
    if prop not in SUPPORTED_PROPERTY_TYPES:
        raise ValueError(f'unsupported component property: {prop}')
    valid = kind == SUPPORTED_PROPERTY_TYPES[prop]
    if prop == 'fontFamily':
        valid = (valid and value == value.strip() and len(value) <= 200 and
                 not any(c in value for c in ',;:{}\\\"\'<>/'))
    elif prop in _FLOAT_PROPERTIES:
        valid = valid and value >= 0 and (prop != 'fontSize' or value > 0)
    if not valid:
        raise ValueError(f'invalid component property value: {prop}')


def _mui_value(prop, value):
    if prop in _FLOAT_PROPERTIES:
        return f'{value}px'
    if prop in _COLOR_PROPERTIES:
        return 'rgba(' + ', '.join(str(value[c] * 255) for c in 'rgb') + ', 1)'
    return value


def _stylesheet(declarations, mui_components):
    rules = []
    for name, component in declarations.items():
        if 'web' not in component:
            continue
        web = component['web']
        selector = web.get('selector') if isinstance(web, dict) else None
        if (not isinstance(selector, str) or not selector.strip() or len(selector) > 1024 or
                not re.fullmatch(r'[A-Za-z0-9_#.*:(), >+~-]+', selector)):
            raise ValueError(f'invalid web selector: {name}')
        depth = 0
        for char in selector:
            depth += (char == '(') - (char == ')')
            if depth < 0:
                raise ValueError(f'invalid web selector: {name}')
        if depth:
            raise ValueError(f'invalid web selector: {name}')
        styles = '; '.join(re.sub(r'[A-Z]', lambda match: '-' + match[0].lower(), prop) + ': ' + value
                           for prop, value in mui_components[name].items())
        rules.append(selector + ' { ' + styles + '; }')
    return '\n'.join(rules)


def _display(kind, value):
    if kind == 'FLOAT':
        return f'{value}px'
    if kind == 'COLOR':
        return '#' + ''.join(f'{round(value[c] * 255):02x}' for c in 'rgb')
    return value


def resolve_design_system(graph):
    design = graph.get('design_system')
    if not isinstance(design, dict) or design.get('version') != 1:
        raise ValueError('design_system version 1 is required')
    definitions, declarations = design.get('tokens'), design.get('components')
    if not isinstance(definitions, dict) or not definitions or not isinstance(declarations, dict):
        raise ValueError('design_system requires tokens and components maps')
    values, roots = {}, {}

    def resolve(name, visiting):
        if not isinstance(name, str) or not name or name not in definitions:
            raise ValueError(f'unknown token: {name}')
        if name in visiting:
            raise ValueError(f'token alias cycle: {name}')
        if name in values:
            return
        token = definitions[name]
        if not isinstance(token, dict) or (('value' in token) == ('alias' in token)):
            raise ValueError(f'token requires exactly one value or alias: {name}')
        kind = token.get('type')
        if 'alias' in token:
            target = token['alias']
            resolve(target, visiting | {name})
            if kind != definitions[target]['type']:
                raise ValueError(f'token alias type mismatch: {name}')
            values[name], roots[name] = copy.deepcopy(values[target]), roots[target]
        else:
            _validate_value(kind, token['value'], name)
            values[name], roots[name] = copy.deepcopy(token['value']), name

    for name in definitions:
        resolve(name, set())
    components = {}
    for name, component in declarations.items():
        if not isinstance(name, str) or not name or not isinstance(component, dict) or not isinstance(component.get('properties'), dict):
            raise ValueError('components require named properties maps')
        components[name] = {}
        for prop, ref in component['properties'].items():
            resolve(ref, set())
            _validate_property(prop, definitions[ref]['type'], values[ref])
            components[name][prop] = copy.deepcopy(values[ref])
    mui_components = {}
    for name, properties in components.items():
        mui_components[name] = {prop: _mui_value(prop, value) for prop, value in properties.items()}
        if 'borderWidth' in properties:
            mui_components[name]['borderStyle'] = 'solid'
    foundations = copy.deepcopy(graph.get('design_foundations', {}))
    for role in foundations.get('roles', []):
        name = role.get('token')
        namespace = design.get('foundationNamespace')
        if namespace and name not in values:
            name = namespace.rstrip('/') + '/' + str(name)
        if name in values:
            kind, value = definitions[name]['type'], copy.deepcopy(values[name])
            role.setdefault('native', {}).update(type=kind, value=value)
            role['value'] = _display(kind, value)
            if 'source_values' in role:
                role['source_values'] = [role['value']]
            if 'alias' in definitions[name]:
                role['alias'] = definitions[name]['alias']
            else:
                role.pop('alias', None)
    return {'graphSha256': getattr(graph, 'source_sha256', hashlib.sha256(_encode(graph)).hexdigest()),
            'tokens': values, 'components': components, 'muiComponents': mui_components, 'primitiveRoots': roots,
            'designFoundations': foundations, 'graphStylesheet': _stylesheet(declarations, mui_components)}


def _atomic_write(path, raw):
    path = Path(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _locked_graph(path):
    # Keep the lock inode: unlinking it would allow concurrent independent locks.
    with path.with_name(path.name + '.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _check_web_path(graph_path, out):
    if Path(out).resolve() in {graph_path, graph_path.with_name(graph_path.name + '.lock')}:
        raise ValueError('web module must not overwrite graph or its lock')


def _emit_web_module_locked(graph_path, out):
    result = resolve_design_system(load_graph(graph_path))
    source = '// Generated from the canonical graph; do not edit.\n' + ''.join(
        f'export const {name} = {json.dumps(result[name], ensure_ascii=False, allow_nan=False)};\n'
        for name in ('graphSha256', 'tokens', 'components', 'muiComponents', 'primitiveRoots', 'graphStylesheet'))
    _atomic_write(out, source.encode('utf-8'))
    return result


def emit_web_module(graph_path, out, *, expected_sha256=None):
    path = Path(graph_path).resolve()
    _check_web_path(path, out)
    with _locked_graph(path):
        if expected_sha256 is not None and load_graph(path).source_sha256 != expected_sha256:
            raise ValueError('stale graph: expected SHA256 does not match')
        return _emit_web_module_locked(path, out)


def update_graph_values(graph_path, updates, expected_sha256, *, web_module=None):
    """Hold CAS lock through optional web publication; publication errors leave graph canonical.

    All writers must use this API. A caller publishing two files must retain its
    recovery journal because a crash can leave the module behind the graph.
    """
    path = Path(graph_path).resolve()
    if not isinstance(updates, dict) or (not updates and web_module is None):
        raise ValueError('updates must be a nonempty token/value map unless publishing web')
    if web_module is not None:
        _check_web_path(path, web_module)
    with _locked_graph(path):
        graph = load_graph(path)
        if graph.source_sha256 != expected_sha256:
            raise ValueError('stale graph: expected SHA256 does not match')
        before = resolve_design_system(graph)
        if not updates:
            return _emit_web_module_locked(path, web_module)
        writes = {}
        for name, value in updates.items():
            if name not in before['primitiveRoots']:
                raise ValueError(f'unknown token: {name}')
            root = before['primitiveRoots'][name]
            _validate_value(graph['design_system']['tokens'][root]['type'], value, root)
            if root in writes and writes[root] != value:
                raise ValueError(f'conflicting alias updates: {root}')
            writes[root] = value
        for root, value in writes.items():
            graph['design_system']['tokens'][root]['value'] = copy.deepcopy(value)
        resolved = resolve_design_system(graph)
        if 'design_foundations' in graph:
            graph['design_foundations'] = resolved['designFoundations']
        _atomic_write(path, _encode(graph))
        if web_module is not None:
            return _emit_web_module_locked(path, web_module)
        return resolve_design_system(load_graph(path))
