"""The runtime boundary keeps one transport definition and its public names."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace


class PublicRuntimeSymbolTests(unittest.TestCase):
    def test_only_public_runtime_symbols_remain(self):
        source = (ROOT / 'tools/figma_workspace.py').read_text(encoding='utf-8')
        if 'def public_runtime_symbols' not in source:
            raise AssertionError('runtime boundary must keep only its public symbols')
        self.assertNotIn('Transport stays in place', source)
        self.assertNotIn("(bridge / 'workspace_chat.js').read_text()", source)
        self.assertEqual(workspace.public_runtime_symbols(), (
            'assemble_shared_runtime',
            'bundle_task_kinds',
            'controlExecute',
            'controlRequest',
            'load_runtime_boundary_trace',
            'runtime_module_names',
            'trusted_sources',
            'workspaceControlTick',
        ))
        definitions = []
        for path in sorted((ROOT / 'figma-bridge').glob('*.js')):
            text = path.read_text(encoding='utf-8')
            if 'async function controlRequest' in text:
                definitions.append(path.name)
        self.assertEqual(definitions, ['workspace_transport.js'])
        self.assertIn('async function controlExecute', (ROOT / 'figma-bridge/workspace_control.js').read_text(encoding='utf-8'))
        self.assertIn('async function workspaceControlTick', (ROOT / 'figma-bridge/workspace_control.js').read_text(encoding='utf-8'))
        tasks = (ROOT / 'docs/development-roadmap/RD-07-runtime-boundaries/tasks.md').read_text(encoding='utf-8')
        self.assertIn('public_runtime_symbols', tasks)


if __name__ == '__main__':
    unittest.main()
