"""Verify the repo-owned public Design baseline, SSOT renderer, and provenance manifest."""
from collections import deque
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / 'examples' / 'owned-design-baseline'
sys.path.insert(0, str(ROOT / 'skills' / 'figma-flow' / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools'))

import graph as graph_tool
import review_graph


class OwnedDesignBaselineTest(unittest.TestCase):
    def setUp(self):
        self.graph = json.loads((BASELINE_DIR / 'graph.json').read_text(encoding='utf-8'))
        self.manifest = json.loads((BASELINE_DIR / 'manifest.json').read_text(encoding='utf-8'))

    def test_canonical_graph_strict_local_and_review_projection(self):
        self.assertEqual(graph_tool.validate_graph(self.graph, strict_local=False), ([], []))
        self.assertEqual(graph_tool.validate_graph(self.graph, strict_local=True), ([], []))

        projected, sha = review_graph.project_graph(BASELINE_DIR / 'graph.json', None)
        self.assertEqual(projected['id'], 'owned-design-baseline')
        self.assertEqual(len(projected['nodes']), len(self.graph['nodes']))
        self.assertEqual(len(projected['edges']), len(self.graph['edges']))
        self.assertRegex(sha, r'^[0-9a-f]{64}$')

        for node in self.graph['nodes']:
            if 'source' in node:
                rel_target = node['source'].split('#', 1)[0]
                resolved = (BASELINE_DIR / rel_target).resolve()
                self.assertTrue(resolved.is_file(), f"Missing local source for {node['id']}: {rel_target}")
                self.assertTrue(resolved.is_relative_to(ROOT))

    def test_three_layer_separation_and_disclosure_reachability(self):
        expected_layers = {'reference-input', 'owned-public-baseline', 'generated-private-output'}
        self.assertEqual(set(self.manifest['artifact_layers']), expected_layers)

        layers_seen = set()
        for node in self.graph['nodes']:
            self.assertIn(node.get('layer'), expected_layers)
            layers_seen.add(node['layer'])
            if node['layer'] == 'reference-input':
                self.assertEqual(node['type'], 'reference')
            elif node['layer'] == 'generated-private-output':
                self.assertEqual(node['type'], 'figma')
                self.assertEqual(node['status'], 'planned')
        self.assertEqual(layers_seen, expected_layers)

        requirements = [n for n in self.graph['nodes'] if n['type'] == 'requirement']
        states = [n for n in self.graph['nodes'] if n['type'] == 'state']
        actions = [n for n in self.graph['nodes'] if n['type'] == 'action']
        self.assertEqual(len(requirements), 2)
        self.assertEqual(len(states), 3)
        self.assertEqual(len(actions), 6)

        kinds = [a['transition_kind'] for a in actions]
        self.assertEqual(kinds.count('open'), 2)
        self.assertEqual(kinds.count('close'), 2)
        self.assertEqual(kinds.count('switch'), 2)

        initial_states = [s for s in states if s.get('initial')]
        self.assertEqual(len(initial_states), 1)
        self.assertIsNone(initial_states[0]['expanded_requirement'])

        by_id = {n['id']: n for n in self.graph['nodes']}
        state_adj = {s['id']: set() for s in states}
        for edge in self.graph['edges']:
            if edge['type'] == 'accepts input' and edge['from'] in state_adj:
                action_id = edge['to']
                for nav in self.graph['edges']:
                    if nav['from'] == action_id and nav['type'] == 'navigates to':
                        self.assertIn(by_id[nav['to']]['type'], {'state'})
                        state_adj[edge['from']].add(nav['to'])

        visited = {initial_states[0]['id']}
        queue = deque([initial_states[0]['id']])
        while queue:
            cur = queue.popleft()
            for nxt in state_adj[cur]:
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        self.assertEqual(visited, {s['id'] for s in states})
        self.assertEqual(sum(len(targets) for targets in state_adj.values()), 6)

    def test_manifest_ownership_license_and_file_sharing_scope(self):
        license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        ownership = self.manifest['ownership']
        self.assertIn('MIT License', license_text)
        self.assertEqual(ownership['license'], 'MIT')
        self.assertIn(ownership['copyright'], license_text)
        self.assertTrue((BASELINE_DIR / ownership['license_path']).resolve().samefile(ROOT / 'LICENSE'))
        self.assertTrue(ownership['authored_in_repo'])
        self.assertEqual(ownership['third_party_sources'], [])
        self.assertEqual(ownership['third_party_licenses_claimed'], [])
        self.assertEqual(ownership['external_media_assets'], 0)
        self.assertEqual(ownership['external_font_requests'], 0)
        self.assertEqual(ownership['external_network_requests'], 0)

        policy = self.manifest['external_reference_policy']
        self.assertFalse(policy['requires_template_source'])
        self.assertFalse(policy['record_external_names'])
        self.assertFalse(policy['record_external_urls'])
        self.assertFalse(policy['record_external_screenshots'])
        self.assertFalse(policy['record_external_copy'])

        declared_files = [entry['path'] for entry in self.manifest['files']]
        actual_files = sorted(p.name for p in BASELINE_DIR.iterdir() if not p.name.startswith('.'))
        self.assertEqual(sorted(declared_files), actual_files)
        for entry in self.manifest['files']:
            self.assertEqual(entry['sharing_scope'], 'public')
            self.assertEqual(entry['layer'], 'owned-public-baseline')
            self.assertEqual(entry['ownership'], 'repo-authored')
            self.assertEqual(entry['license'], 'MIT')
            self.assertNotIn(Path(entry['path']).suffix.lower(), {'.png', '.jpg', '.jpeg', '.webp', '.gif'})

        self.assertTrue(self.manifest['private_generated_outputs'])
        for entry in self.manifest['private_generated_outputs']:
            self.assertEqual(entry['sharing_scope'], 'private')
            self.assertEqual(entry['layer'], 'generated-private-output')
            self.assertFalse(entry['git_tracked'])

    def test_single_canonical_source_and_zero_external_requests(self):
        renderer_sources = {
            name: (BASELINE_DIR / name).read_text(encoding='utf-8')
            for name in ('index.html', 'styles.css', 'renderer.js')
        }
        manifest_raw = (BASELINE_DIR / 'manifest.json').read_text(encoding='utf-8')

        for node in self.graph['nodes']:
            for name, content in renderer_sources.items():
                self.assertNotIn(node['id'], content, f"Semantic ID {node['id']} duplicated in {name}")
                self.assertNotIn(node['title'], content, f"Node title {node['title']!r} duplicated in {name}")
                if node.get('detail'):
                    self.assertNotIn(node['detail'], content, f"Node detail duplicated in {name}")
            self.assertNotIn(node['id'], manifest_raw, f"Semantic ID {node['id']} duplicated in manifest.json")
            self.assertNotIn(node['title'], manifest_raw, f"Node title {node['title']!r} duplicated in manifest.json")

        self.assertNotRegex(renderer_sources['styles.css'], r'@import|@font-face|url\(')
        for name in ('graph.json', 'manifest.json', 'index.html', 'styles.css', 'renderer.js'):
            raw = (BASELINE_DIR / name).read_text(encoding='utf-8')
            urls = re.findall(r'https?://[^\s"\'<>]+', raw)
            allowed = {'http://www.w3.org/2000/svg'} if name == 'renderer.js' else set()
            self.assertEqual(set(urls) - allowed, set(), f"Unexpected external URL in {name}: {urls}")

        for path in BASELINE_DIR.iterdir():
            if path.is_file():
                content = path.read_text(encoding='utf-8')
                self.assertNotIn('/Users/', content, f"Personal path leaked in {path.name}")
                self.assertNotIn('/home/', content, f"Personal path leaked in {path.name}")


if __name__ == '__main__':
    unittest.main()
