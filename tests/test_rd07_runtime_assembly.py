"""Publisher assembly and trusted sources share one runtime module list."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace


class RuntimeAssemblyTests(unittest.TestCase):
    def test_publisher_and_trusted_sources_share_the_module_list(self):
        source = (ROOT / 'tools/figma_workspace.py').read_text(encoding='utf-8')
        if 'def runtime_module_names' not in source or 'def assemble_shared_runtime' not in source:
            raise AssertionError('publisher assembly and trusted sources must share one module list')
        names = workspace.runtime_module_names()
        self.assertEqual(names, ('workspace_chat.js', 'workspace_transport.js', 'workspace_control.js', 'workspace_host.js'))
        bridge = ROOT / 'figma-bridge'
        self.assertEqual(workspace.assemble_shared_runtime(bridge), '\n'.join((bridge / name).read_text(encoding='utf-8') for name in names))
        trusted = source[source.index('def trusted_sources'):source.index('def load_runtime_boundary_trace')]
        self.assertIn('runtime_module_names()', trusted)
        publish = source[source.index('def publish'):source.index('def init')]
        self.assertIn('assemble_shared_runtime(bridge)', publish)
        self.assertNotIn("(bridge / 'workspace_chat.js').read_text()", publish)
        self.assertRegex(workspace.trusted_sources(), r'^[a-f0-9]{64}$')
        tasks = (ROOT / 'docs/development-roadmap/RD-07-runtime-boundaries/tasks.md').read_text(encoding='utf-8')
        self.assertIn('runtime_module_names', tasks)


if __name__ == '__main__':
    unittest.main()
