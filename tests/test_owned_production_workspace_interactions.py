"""Drive the gate disclosure and evidence rail in a real browser from edited copies of the canonical graph."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples' / 'owned-production-workspace'
DRIVER = ROOT / 'tests' / 'owned_production_workspace_interactions.mjs'
sys.path.insert(0, str(ROOT / 'tools'))

import owned_production_workspace as workspace  # noqa: E402

BASELINE = {'gates': [None, 0, 1, None, 0, None], 'rail': [0, 1, 2, 2, 1, 0, 0]}


def without_action(action_id):
    def change(graph):
        graph['nodes'] = [node for node in graph['nodes'] if node['id'] != action_id]
        graph['edges'] = [edge for edge in graph['edges'] if action_id not in (edge['from'], edge['to'])]
    return change


def set_field(node_id, field, value):
    def change(graph):
        next(node for node in graph['nodes'] if node['id'] == node_id)[field] = value
    return change


def renamed(prefixes):
    def change(graph):
        ids = {node['id'] for node in graph['nodes'] if node['id'].startswith(prefixes)}
        new = {old: 'X-' + hashlib.sha256(old.encode()).hexdigest()[:10] for old in ids}
        for node in graph['nodes']:
            node['id'] = new.get(node['id'], node['id'])
            if 'target_ids' in node:
                node['target_ids'] = [new.get(target, target) for target in node['target_ids']]
        for edge in graph['edges']:
            edge['from'] = new.get(edge['from'], edge['from'])
            edge['to'] = new.get(edge['to'], edge['to'])
    return change


class GraphInteractionTest(unittest.TestCase):
    def observe(self, change=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'examples' / 'owned-production-workspace'
        shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
        if change:
            graph = json.loads((root / 'graph.json').read_text(encoding='utf-8'))
            change(graph)
            (root / 'graph.json').write_text(json.dumps(graph, indent=2) + '\n', encoding='utf-8')
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            for entry in manifest['files']:
                if entry['path'] == 'graph.json':
                    entry['sha256'] = hashlib.sha256((root / 'graph.json').read_bytes()).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        server, _ = workspace.make_server(root, '127.0.0.1', 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_address[1]}/index.html#/review?package=pkg-field-input'
            try:
                result = subprocess.run(['node', str(DRIVER), url], capture_output=True, text=True, timeout=120, check=True)
            except FileNotFoundError:
                self.skipTest('node is not on PATH')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        if 'skipped' in observed:
            self.skipTest(observed['skipped'])
        return observed

    def test_graph_rules_drive_the_disclosure_and_rail(self):
        cases = {
            'committed graph': (None, BASELINE),
            'switch removed': (without_action('ACT-GATE-SWITCH'), {'gates': [None, 0, 0, 0, None, 0]}),
            'close removed': (without_action('ACT-GATE-CLOSE'), {'gates': [None, 0, 1, 1, 0, 0]}),
            'next steps two cards': (set_field('ACT-RAIL-NEXT', 'step', 2), {'rail': [0, 2, 2, 2, 1, 0, 0]}),
            'previous removed': (without_action('ACT-RAIL-PREVIOUS'), {'rail': [0, 1, 2, 2, 2, 2, 2]}),
            'rail starts at the second card': (set_field('STATE-RAIL-BROWSING', 'initial_position', 1), {'rail': [1, 2, 2, 2, 1, 0, 0]}),
            'component ids renamed': (renamed(('STATE-GATES-', 'ACT-GATE-', 'STATE-RAIL-', 'ACT-RAIL-', 'CMP-')), BASELINE),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                observed = self.observe(change)
                for key, sequence in expected.items():
                    self.assertEqual(observed[key], sequence, f'{name}: {key}')


if __name__ == '__main__':
    unittest.main()
