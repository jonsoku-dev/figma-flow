"""Graph structure and mock API checks for the regression apps."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/regression-program'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RegressionAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load('regression_catalog', FIXTURE / 'catalog.py')
        cls.graph = load('product_graph', ROOT / 'skills/figma-flow/scripts/graph.py')
        sys.path.insert(0, str(FIXTURE / 'server'))
        cls.api = load('mock_api', FIXTURE / 'server/mock_api.py')

    def test_graphs_match_the_catalog_and_validate(self):
        screen_ids = []
        for app_id in ('atlas', 'morrow', 'paper'):
            expected = self.catalog.build_graph(app_id)
            actual = json.loads((FIXTURE / app_id / 'graph.json').read_text())
            self.assertEqual(actual, expected)
            errors, _warnings = self.graph.validate_graph(actual)
            self.assertEqual(errors, [])
            screen_ids.extend(node['id'] for node in actual['nodes'] if node['type'] == 'screen')
        self.assertEqual(len(screen_ids), len(set(screen_ids)))

    def test_mock_vectors_match_the_server(self):
        vectors = json.loads((FIXTURE / 'server/vectors.json').read_text())
        for vector in vectors:
            status, body = self.api.handle(vector['path'], vector['payload'])
            self.assertEqual(status, vector['status'], vector['name'])
            self.assertEqual(body, vector['body'], vector['name'])

    def test_live_mock_save_returns_the_same_draft(self):
        server = subprocess.Popen(
            [sys.executable, str(FIXTURE / 'server/serve.py'), '--port', '0'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            line = server.stdout.readline().strip()
            self.assertTrue(line.startswith('LISTENING '), line)
            port = int(line.split()[1])
            payload = json.dumps({'fault': 'save-task', 'draft': {'detail': '남김'}}).encode()
            request = Request(f'http://127.0.0.1:{port}/api/atlas/tasks/save', data=payload, headers={'content-type': 'application/json'})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 409)
            body = json.loads(caught.exception.read().decode())
            self.assertEqual(body['draft'], {'detail': '남김'})
            with urlopen(f'http://127.0.0.1:{port}/atlas/projects/north') as response:
                html = response.read().decode()
            self.assertIn('Atlas Workspace', html)
            self.assertNotIn('오늘의 검토', html)
            with urlopen(f'http://127.0.0.1:{port}/html/atlas/js/index.html') as response:
                js_html = response.read().decode()
            self.assertNotIn('JS로 만든 승인 큐', js_html)
        finally:
            server.terminate()
            server.wait(timeout=5)
            server.stdout.close()
            server.stderr.close()


if __name__ == '__main__':
    unittest.main()
