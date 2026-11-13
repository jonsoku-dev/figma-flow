"""A route owns each measured viewport and larger graphs admit bounded native edits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from native_edit import validate_plan
from web_design import build_plan
from web_route_graph import link_viewports


class ResponsiveGraphTests(unittest.TestCase):
    def fixture(self):
        nodes = []
        edges = []
        for index in range(18):
            key = f'WEB-route-{index}'
            nodes.append({'id': key, 'type': 'screen', 'status': 'observed', 'title': key,
                          'layout': {'width': 390, 'height': 500}, 'elements': []})
            nodes.append({'id': f'ref-{index}', 'type': 'reference', 'status': 'observed', 'title': key,
                          'capture_sha256': 'a' * 64, 'origin': 'http://localhost:8000',
                          'page_path': f'/page-{index // 2}', 'viewport': {'width': (390, 1440)[index % 2], 'height': 844}})
            edges.append({'from': key, 'to': f'ref-{index}', 'type': 'sourced from'})
        return {'version': 1, 'id': 'route-test', 'title': 'Route test', 'nodes': nodes, 'edges': edges}

    def test_scope_and_route_variants(self):
        graph = link_viewports(self.fixture())
        self.assertEqual(sum(n['type'] == 'state' for n in graph['nodes']), 9)
        self.assertEqual(sum(e['type'] == 'renders at viewport' for e in graph['edges']), 18)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'graph.json')
            plan = Path(directory, 'plan.json')
            source.write_text(json.dumps(graph))
            with self.assertRaisesRegex(ValueError, 'sixteen'):
                build_plan(source, 'fixture', '1:1', plan)
            build_plan(source, 'fixture', '1:1', plan, ['WEB-route-0', 'WEB-route-1'], readback_scope='screens')
            value = json.loads(plan.read_bytes())
            self.assertEqual(len(validate_plan(value)['web_design']['screens']), 2)
            self.assertEqual(value['web_design']['readback_scope'], 'screens')

    def test_duplicate_measurements_rejected(self):
        graph = self.fixture()
        graph['nodes'][3]['viewport'] = copy.copy(graph['nodes'][1]['viewport'])
        with self.assertRaisesRegex(ValueError, 'unique observation'):
            link_viewports(graph)
