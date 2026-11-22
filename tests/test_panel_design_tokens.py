"""The panel token projection and relay palette remain graph-owned."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from panel_authority import check as check_panel_authority


class PanelDesignTokenTests(unittest.TestCase):
    def test_graph_relationships_cover_each_token_once(self):
        graph = json.loads((ROOT / 'library/panel-design/tokens.json').read_text(encoding='utf-8'))
        surfaces = {surface['id'] for surface in graph['surfaces']}
        tokens = {token['id']: token for token in graph['tokens']}
        self.assertEqual(graph['schema'], 'figma-flow-panel-design-graph-v1')
        self.assertEqual(len(tokens), len(graph['tokens']))
        expected = {(token['surface'], 'uses-token', token_id) for token_id, token in tokens.items()}
        actual = {(edge['from'], edge['type'], edge['to']) for edge in graph['edges']}
        self.assertEqual(actual, expected)
        self.assertEqual(len(graph['edges']), len(expected))
        self.assertTrue(all(edge['from'] in surfaces for edge in graph['edges']))
        self.assertTrue(all(token['surface'] in surfaces and token['role'] for token in tokens.values()))

    def test_generated_palette_is_current_and_relay_css_uses_roles(self):
        check = subprocess.run(
            ['node', str(ROOT / 'panel-ui/build-tokens.mjs'), '--check'],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(check.returncode, 0, check.stderr)
        relay = (ROOT / 'panel-ui/src/styles/relay.css').read_text(encoding='utf-8')
        literal_color = re.compile(
            r'#[0-9a-f]{3,8}\b|\brgba?\s*\(|\b(?:color|background(?:-color)?|border-color)\s*:\s*(?:white|black)\b', re.I,
        )
        self.assertIsNone(literal_color.search(relay), 'relay colors must come from the panel design graph')
        self.assertIn('var(--relay-ink-dark)', relay)
        self.assertIn('var(--relay-canvas-dark)', relay)
        self.assertEqual(check_panel_authority(ROOT), [])

    def test_check_mode_rejects_a_changed_generated_projection(self):
        with __import__('tempfile').TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'panel-ui/src/styles').mkdir(parents=True)
            (root / 'library/panel-design').mkdir(parents=True)
            for relative in ('panel-ui/build-tokens.mjs', 'library/panel-design/tokens.json', 'panel-ui/src/styles/tokens.css'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            css = root / 'panel-ui/src/styles/tokens.css'
            css.write_text(css.read_text(encoding='utf-8').replace('--paper: #faf9f6;', '--paper: #faf9f5;'), encoding='utf-8')
            result = subprocess.run(
                ['node', str(root / 'panel-ui/build-tokens.mjs'), '--check'],
                cwd=root, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('tokens.css is stale', result.stderr)

    def test_runtime_check_fails_closed_for_stale_projection_and_raw_colors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('panel-ui/build-tokens.mjs', 'panel-ui/src/styles/tokens.css',
                             'panel-ui/src/styles/relay.css', 'library/panel-design/tokens.json'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            relay = root / 'panel-ui/src/styles/relay.css'
            relay.write_text(relay.read_text(encoding='utf-8') + '\n.bad { color: #123456; }\n', encoding='utf-8')
            raw_findings = check_panel_authority(root)
            self.assertIn('PANEL_RELAY_COLOR_LITERAL', {item['code'] for item in raw_findings})
            relay.write_text(relay.read_text(encoding='utf-8').replace('#123456', 'var(--not-a-token)'), encoding='utf-8')
            unknown_findings = check_panel_authority(root)
            self.assertIn('PANEL_RELAY_TOKEN_UNOWNED', {item['code'] for item in unknown_findings})
            relay.write_text(relay.read_text(encoding='utf-8').replace('var(--not-a-token)', '12px'), encoding='utf-8')
            dimension_findings = check_panel_authority(root)
            self.assertIn('PANEL_RELAY_DIMENSION_LITERAL', {item['code'] for item in dimension_findings})
            relay.write_text(relay.read_text(encoding='utf-8') + '\n.relay-view { --relay-ink: #fff; }\n', encoding='utf-8')
            override_findings = check_panel_authority(root)
            self.assertIn('PANEL_RELAY_LOCAL_TOKEN_OVERRIDE', {item['code'] for item in override_findings})
            relay.write_text((ROOT / 'panel-ui/src/styles/relay.css').read_text(encoding='utf-8'), encoding='utf-8')
            css = root / 'panel-ui/src/styles/tokens.css'
            css.write_text(css.read_text(encoding='utf-8').replace('--paper: #faf9f6;', '--paper: #faf9f5;'), encoding='utf-8')
            stale_findings = check_panel_authority(root)
            self.assertIn('PANEL_TOKEN_PROJECTION_INVALID', {item['code'] for item in stale_findings})

    def test_runtime_check_rejects_malformed_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('panel-ui/build-tokens.mjs', 'panel-ui/src/styles/tokens.css',
                             'panel-ui/src/styles/relay.css'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            graph = root / 'library/panel-design/tokens.json'
            graph.parent.mkdir(parents=True, exist_ok=True)
            graph.write_text('{bad json', encoding='utf-8')
            findings = check_panel_authority(root)
            self.assertIn('PANEL_TOKEN_GRAPH_UNAVAILABLE', {item['code'] for item in findings})

    def test_runtime_check_rejects_duplicate_tokens_and_incomplete_relationships(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('panel-ui/build-tokens.mjs', 'panel-ui/src/styles/tokens.css',
                             'panel-ui/src/styles/relay.css', 'library/panel-design/tokens.json'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            graph_path = root / 'library/panel-design/tokens.json'
            graph = json.loads(graph_path.read_text(encoding='utf-8'))
            graph['tokens'].append(dict(graph['tokens'][0]))
            graph['edges'].pop()
            graph_path.write_text(json.dumps(graph), encoding='utf-8')
            findings = check_panel_authority(root)
            self.assertIn('PANEL_TOKEN_PROJECTION_INVALID', {item['code'] for item in findings})


if __name__ == '__main__':
    unittest.main()
