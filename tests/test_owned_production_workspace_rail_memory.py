"""Check in a real browser that the rail keeps its current card across re-renders and resets on a new review."""
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
DRIVER = ROOT / 'tests' / 'owned_production_workspace_rail_memory.mjs'
sys.path.insert(0, str(ROOT / 'tools'))

import owned_production_workspace as workspace  # noqa: E402

RERENDERS = ('gate opened after direct scroll', 'gate closed after direct scroll', 'gate opened after next', 'invalid decision re-render')


class RailMemoryTest(unittest.TestCase):
    def observe(self, viewport, initial_position=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'examples' / 'owned-production-workspace'
        shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
        graph = json.loads((root / 'graph.json').read_text(encoding='utf-8'))
        rail_state = next(node for node in graph['nodes'] if node['type'] == 'state' and 'initial_position' in node)
        if initial_position is not None:
            rail_state['initial_position'] = initial_position
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
                result = subprocess.run(['node', str(DRIVER), url, str(viewport[0]), str(viewport[1])],
                                        capture_output=True, text=True, timeout=120, check=True)
            except FileNotFoundError:
                self.skipTest('node is not on PATH')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        if 'skipped' in observed:
            self.skipTest(observed['skipped'])
        return rail_state['initial_position'], {step['label']: step for step in observed['steps']}, observed['steps']

    def test_rail_position_survives_rerender_and_resets_on_new_review(self):
        for name, viewport, initial in (('mobile', (390, 844), None), ('desktop', (1440, 900), None), ('mobile initial 1', (390, 844), 1)):
            with self.subTest(name):
                initial, by_label, steps = self.observe(viewport, initial)
                positions = [step['position'] for step in steps]
                self.assertEqual(by_label['entered review']['position'], initial, positions)
                self.assertNotEqual(by_label['direct scroll']['position'], initial, f'wheel did not move the rail: {positions}')
                self.assertTrue(by_label['invalid decision re-render']['hash'].startswith('#/review/invalid'), steps)
                for previous, current in zip(steps, steps[1:]):
                    if current['label'] in RERENDERS:
                        self.assertEqual(current['position'], previous['position'],
                                         f'rail position must survive {current["label"]}: {positions}')
                self.assertEqual(by_label['new review entered']['position'], initial,
                                 f'a new review must start at the graph initial position: {positions}')


if __name__ == '__main__':
    unittest.main()
