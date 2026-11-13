#!/usr/bin/env python3
"""Publish the graph-owned design values as stable CSS and a provenance manifest."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from graph_design_system import (
    _atomic_write,
    _check_web_path,
    _locked_graph,
    load_graph,
    resolve_design_system,
    web_module_source,
)
from graph_sync import token_native_names

GRAPH = Path(__file__).resolve().parent / 'graph.json'
CSS = Path(__file__).resolve().parents[1] / 'static' / 'littlehands' / 'design-system.css'
MANIFEST = Path(__file__).resolve().parents[1] / 'static' / 'littlehands' / 'design-system.manifest.json'
MODULE = Path(__file__).resolve().parents[1] / 'static' / 'littlehands' / 'design-system.js'


def css_variable(name):
    encoded = name.encode('utf-8').hex()
    return f'--ff-token-{len(name.encode("utf-8"))}-{encoded}'


def _css_value(token, value):
    if token['type'] == 'COLOR':
        return '#' + ''.join(f"{round(value[channel] * 255):02x}" for channel in 'rgb')
    if token['type'] == 'FLOAT':
        return f'{value}px'
    raise ValueError(f"CSS publication does not support {token['type']} tokens")


def publish(graph_path=GRAPH, css_path=CSS, manifest_path=MANIFEST, module_path=MODULE):
    graph_path = Path(graph_path).resolve()
    css_path, manifest_path, module_path = map(Path, (css_path, manifest_path, module_path))
    outputs = [css_path.resolve(), manifest_path.resolve(), module_path.resolve()]
    if len(set(outputs)) != len(outputs):
        raise ValueError('CSS, module, and manifest outputs must be distinct')
    for output in outputs:
        _check_web_path(graph_path, output)
    with _locked_graph(graph_path):
        graph = load_graph(graph_path)
        resolved = resolve_design_system(graph)
        design = graph['design_system']
        definitions = design['tokens']
        css_names = {name: css_variable(name) for name in definitions}
        if len(set(css_names.values())) != len(css_names):
            raise ValueError('token CSS variable encoding collision')
        token_vars = []
        for name, token in definitions.items():
            value = f'var({css_names[token["alias"]]})' if 'alias' in token else _css_value(token, resolved['tokens'][name])
            token_vars.append(f'  {css_names[name]}: {value};')
        component_rules = []
        for component in design['components'].values():
            properties = []
            for prop, token in component['properties'].items():
                css_prop = ''.join('-' + char.lower() if char.isupper() else char for char in prop)
                properties.append(f'{css_prop}: var({css_names[token]})')
            component_rules.append(component['web']['selector'] + ' { ' + '; '.join(properties) + '; }')
        css = ('/* graph-sha256: ' + resolved['graphSha256'] + ' */\n:root {\n' + '\n'.join(token_vars)
               + '\n}\n' + '\n'.join(component_rules) + '\n')
        css_bytes = css.encode('utf-8')
        module_bytes = web_module_source(resolved).encode('utf-8')
        native_namespace, native_names = token_native_names(graph, require_namespace=True)
        native_bindings = {}
        for name, component in design['components'].items():
            native = component.get('native', {})
            native_bindings[name] = {
                'mainKeys': native.get('mainKeys', []),
                'instanceKeys': native.get('instanceKeys', []),
                'properties': {prop: {'semanticToken': token, 'primitiveToken': resolved['primitiveRoots'][token]}
                               for prop, token in component['properties'].items()},
            }
        manifest = {
            'schema': 1,
            'graphSha256': resolved['graphSha256'],
            'cssSha256': hashlib.sha256(css_bytes).hexdigest(),
            'moduleSha256': hashlib.sha256(module_bytes).hexdigest(),
            'tokens': resolved['tokens'],
            'primitiveRoots': resolved['primitiveRoots'],
            'nativeNamespace': native_namespace,
            'nativeTokenNames': native_names,
            'components': resolved['components'],
            'designFoundations': resolved['designFoundations'],
            'nativeBindings': native_bindings,
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        _atomic_write(css_path, css_bytes, mode=0o644)
        _atomic_write(module_path, module_bytes, mode=0o644)
        _atomic_write(manifest_path, manifest_bytes, mode=0o644)
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
