#!/usr/bin/env python3
"""Publish the graph-owned design values as stable CSS and a provenance manifest."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from graph_design_system import emit_web_module, load_graph, resolve_design_system

GRAPH = Path(__file__).resolve().parent / 'graph.json'
CSS = Path(__file__).resolve().parents[1] / 'static' / 'littlehands' / 'design-system.css'
MANIFEST = Path(__file__).resolve().parents[1] / 'static' / 'littlehands' / 'design-system.manifest.json'
MODULE = Path(__file__).resolve().parents[1] / 'static' / 'littlehands' / 'design-system.js'


def css_variable(name):
    segments = name.replace('.', '/').split('/')
    encoded = '-'.join(f'{len(part.encode("utf-8"))}-{part.encode("utf-8").hex()}' for part in segments)
    return '--ff-token-' + encoded


def _css_value(token, value):
    if token['type'] == 'COLOR':
        return '#' + ''.join(f"{round(value[channel] * 255):02x}" for channel in 'rgb')
    if token['type'] == 'FLOAT':
        return f'{value}px'
    raise ValueError(f"CSS publication does not support {token['type']} tokens")


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(graph_path=GRAPH, css_path=CSS, manifest_path=MANIFEST, module_path=MODULE):
    resolved = resolve_design_system(load_graph(graph_path))
    design = load_graph(graph_path)['design_system']
    definitions = design['tokens']
    css_names = {name: css_variable(name) for name in definitions}
    if len(set(css_names.values())) != len(css_names):
        raise ValueError('token CSS variable encoding collision')
    token_vars = []
    for name, token in definitions.items():
        value = f'var({css_names[token["alias"]]})' if 'alias' in token else _css_value(token, resolved['tokens'][name])
        token_vars.append(f'  {css_names[name]}: {value};')
    component_rules = []
    for name, component in design['components'].items():
        selector = component['web']['selector']
        properties = []
        for prop, token in component['properties'].items():
            css_prop = ''.join('-' + char.lower() if char.isupper() else char for char in prop)
            properties.append(f'{css_prop}: var({css_names[token]})')
        component_rules.append(selector + ' { ' + '; '.join(properties) + '; }')
    css = '/* graph-sha256: ' + resolved['graphSha256'] + ' */\n:root {\n' + '\n'.join(token_vars) + '\n}\n' + '\n'.join(component_rules) + '\n'
    css_bytes = css.encode('utf-8')
    module_path.parent.mkdir(parents=True, exist_ok=True)
    emit_web_module(graph_path, module_path, expected_sha256=resolved['graphSha256'])
    module_sha256 = hashlib.sha256(module_path.read_bytes()).hexdigest()
    native_bindings = {}
    for name, component in design['components'].items():
        native = component.get('native', {})
        native_bindings[name] = {
            'mainKeys': native.get('mainKeys', []),
            'instanceKeys': native.get('instanceKeys', []),
            'properties': {prop: {'semanticToken': token, 'primitiveToken': resolved['primitiveRoots'][token]}
                           for prop, token in component['properties'].items()},
        }
    native_namespace = design.get('namespace') or ('ssot/' + design['id'] if design.get('id') else None)
    native_token_names = ({name: name if name.startswith(native_namespace + '/') else native_namespace + '/' + name
                           for name in definitions} if native_namespace else {})
    manifest = {
        'schema': 1,
        'graphSha256': resolved['graphSha256'],
        'cssSha256': hashlib.sha256(css_bytes).hexdigest(),
        'moduleSha256': module_sha256,
        'tokens': resolved['tokens'],
        'primitiveRoots': resolved['primitiveRoots'],
        'nativeNamespace': native_namespace,
        'nativeTokenNames': native_token_names,
        'components': resolved['components'],
        'nativeBindings': native_bindings,
    }
    _atomic_write(css_path, css_bytes)
    _atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--graph', type=Path, default=GRAPH)
    parser.add_argument('--css', type=Path, default=CSS)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--module', type=Path, default=MODULE)
    args = parser.parse_args()
    manifest = publish(args.graph, args.css, args.manifest, args.module)
    print(json.dumps({'graphSha256': manifest['graphSha256'], 'cssSha256': manifest['cssSha256'],
                      'moduleSha256': manifest['moduleSha256'],
                      'css': str(args.css), 'manifest': str(args.manifest), 'module': str(args.module)}, indent=2))


if __name__ == '__main__':
    main()
