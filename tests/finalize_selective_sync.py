"""Frozen RD04 oracle: exercise the exported production panel and sandbox handler."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from graph_design_system import load_graph, update_graph_values
from graph_sync import build_plan, normalize, receipt, export_bundle


def main():
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        tokens = {'size': {'type': 'FLOAT', 'value': 18},
                  'alias': {'type': 'FLOAT', 'alias': 'size'},
                  'left': {'type': 'FLOAT', 'value': 18},
                  'right': {'type': 'FLOAT', 'value': 18}}
        properties = {'fontSize': 'alias', 'paddingLeft': 'left', 'paddingRight': 'right'}
        graph = {'design_system': {'version': 1, 'tokens': tokens, 'components': {
            'button': {'properties': properties, 'native': {'mainKeys': ['main'], 'instanceKeys': ['instance']},
                       'web': {'selector': '#button'}}}}}
        variables = [{'id': key, 'name': key, 'resolvedType': 'FLOAT', 'variableCollectionId': 'collection',
                      'valuesByMode': {'mode': {'type': 'VARIABLE_ALIAS', 'id': 'size'} if key == 'alias' else 18}}
                     for key in tokens]
        nodes = []
        for identity, kind in [('main', 'COMPONENT'), ('instance', 'INSTANCE')]:
            nodes.extend([
                {'id': identity, 'type': kind, 'parentId': 'page', 'mainComponentId': 'main',
                 'paddingLeft': 18, 'paddingRight': 18, 'boundVariables': {
                     'paddingLeft': {'type': 'VARIABLE_ALIAS', 'id': 'left'},
                     'paddingRight': {'type': 'VARIABLE_ALIAS', 'id': 'right'}}},
                {'id': identity + '.text', 'type': 'TEXT', 'parentId': identity, 'fontSize': 18,
                 'boundVariables': {'fontSize': [{'type': 'VARIABLE_ALIAS', 'id': 'alias'}]}}])
        native = {'fileKey': 'file', 'pageId': 'page', 'variables': variables, 'nodes': nodes,
                  'collections': [{'id': 'collection', 'defaultModeId': 'mode', 'modes': [{'modeId': 'mode'}]}]}
        path = directory / 'graph.json'
        path.write_text(json.dumps(graph))
        original = load_graph(path)
        plan = build_plan(original, native)
        readback = normalize(native, plan)
        readback['baseline'] = {'page_id': 'page', 'collection_id': 'collection', 'graph_sha256': plan['graph_sha256']}
        paired = receipt(original, plan, readback)
        update_graph_values(path, {'size': 24, 'left': 22, 'right': 26}, original.source_sha256)
        export_bundle(path, directory / 'bundle', directory / 'tokens.mjs', pairing=paired)
        (directory / 'native.json').write_text(json.dumps(native))
        (directory / 'marker.json').write_text(json.dumps(readback['baseline']))
        subprocess.run(['node', '--test', str(ROOT / 'tests/finalize_selective_sync.cjs')],
                       env={**__import__('os').environ, 'RD04_BUNDLE': str(directory)}, check=True)


if __name__ == '__main__':
    main()
