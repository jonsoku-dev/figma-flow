import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import plugin_panel


def isolated_registry(graph):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    graph_path = root / 'library/panel-design/views.json'
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps(graph), encoding='utf-8')
    for node in graph['nodes']:
        if node.get('type') != 'code' or not node.get('source'):
            continue
        source = (graph_path.parent / node['source']).resolve()
        parts = Path(node['source']).parts
        source_index = parts.index('panel-ui')
        original = ROOT.joinpath(*parts[source_index:])
        if original.is_file():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, source)
    for folder in ('figma-bridge', 'tools'):
        target = root / folder
        target.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / 'figma-bridge').glob('*.html'):
        shutil.copyfile(source, root / 'figma-bridge' / source.name)
    for name in ('figma_workspace.py', 'figma_draft.py', 'relay_alignment.py'):
        shutil.copyfile(ROOT / 'tools' / name, root / 'tools' / name)
    return temporary, root, graph_path


class PanelViewRegistryTests(unittest.TestCase):
    def test_registry_owns_routes_roles_and_registered_home(self):
        registry = plugin_panel.VIEW_REGISTRY
        self.assertEqual(set(registry), {'relay', 'workspace', 'import', 'review', 'graph', 'chat'})
        self.assertEqual(plugin_panel.registered_home_view(), 'relay')
        self.assertEqual({key for key, value in registry.items() if value['role'] == 'task'},
                         {'import', 'review', 'graph'})
        self.assertEqual({key for key, value in registry.items() if value['role'] == 'standalone'},
                         {'workspace', 'chat'})

    def test_added_view_reaches_python_renderer(self):
        graph = json.loads(plugin_panel.VIEW_GRAPH.read_text(encoding='utf-8'))
        graph['nodes'].extend([
            {'id': 'preview', 'type': 'screen', 'title': 'Preview task surface', 'status': 'observed',
             'role': 'task', 'lifecycle': 'active', 'locale': 'relay'},
            {'id': 'react-preview', 'type': 'code', 'title': 'Preview React view', 'status': 'observed',
             'source': '../../panel-ui/src/RelayViewer.jsx'},
        ])
        graph['edges'].append({'from': 'preview', 'type': 'implemented by', 'to': 'react-preview'})
        temporary, root, graph_path = isolated_registry(graph)
        try:
            registry = plugin_panel.load_view_registry(root=root, graph_path=graph_path)
            self.assertEqual(registry['preview']['role'], 'task')
            rendered = plugin_panel.render_app('preview', view_registry=registry)
            self.assertIn('data-flow-view="preview"', rendered)
        finally:
            temporary.cleanup()

    def test_removed_view_with_existing_entrypoint_is_reported(self):
        graph = json.loads(plugin_panel.VIEW_GRAPH.read_text(encoding='utf-8'))
        graph['nodes'] = [node for node in graph['nodes'] if node['id'] not in {'relay', 'react-relay'}]
        next(node for node in graph['nodes'] if node.get('role') == 'task').update(
            role='registered-home', lifecycle='active')
        graph['edges'] = [edge for edge in graph['edges'] if edge['from'] != 'relay' and edge['to'] != 'react-relay']
        temporary, root, graph_path = isolated_registry(graph)
        try:
            with self.assertRaisesRegex(ValueError, "unregistered view relay"):
                plugin_panel.load_view_registry(root=root, graph_path=graph_path)
        finally:
            temporary.cleanup()

    def test_duplicate_registered_home_and_missing_component_are_rejected(self):
        graph = json.loads(plugin_panel.VIEW_GRAPH.read_text(encoding='utf-8'))
        workspace = next(node for node in graph['nodes'] if node['id'] == 'workspace')
        workspace.update(role='registered-home', lifecycle='active')
        temporary, root, graph_path = isolated_registry(graph)
        try:
            with self.assertRaisesRegex(ValueError, 'exactly one registered-home'):
                plugin_panel.load_view_registry(root=root, graph_path=graph_path)
        finally:
            temporary.cleanup()

        graph = json.loads(plugin_panel.VIEW_GRAPH.read_text(encoding='utf-8'))
        implementation = next(node for node in graph['nodes'] if node['id'] == 'react-relay')
        implementation['source'] = '../../panel-ui/src/Missing.jsx'
        temporary, root, graph_path = isolated_registry(graph)
        try:
            with self.assertRaisesRegex(ValueError, 'React source is missing'):
                plugin_panel.load_view_registry(root=root, graph_path=graph_path)
        finally:
            temporary.cleanup()


if __name__ == '__main__':
    unittest.main()
