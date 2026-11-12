"""Pin the current control transport trace and trusted source range."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace


class RuntimeBoundaryTraceTests(unittest.TestCase):
    def test_trace_pins_transport_and_source_range(self):
        source = (ROOT / 'tools/figma_workspace.py').read_text(encoding='utf-8')
        if 'def load_runtime_boundary_trace' not in source:
            raise AssertionError('runtime boundary trace must pin transport and source pins')
        trace = workspace.load_runtime_boundary_trace()
        self.assertEqual(trace['schema'], 'figma-flow-runtime-boundary-v1')
        self.assertEqual(trace['transport']['routes'], ['poll', 'native-started', 'result'])
        self.assertEqual(trace['transport']['method'], 'POST')
        self.assertEqual(trace['transport']['authorization'], 'Bearer')
        self.assertEqual(trace['allowed'], {
            'review': ['create'],
            'import': ['read', 'import', 'sync'],
            'discover': ['read'],
            'sync': ['read', 'apply'],
            'native-edit': ['read', 'apply'],
        })
        control = (ROOT / 'figma-bridge/workspace_control.js').read_text(encoding='utf-8')
        self.assertIn("const controlAllowed = {review: ['create'], import: ['read', 'import', 'sync'], discover: ['read'], sync: ['read', 'apply'], 'native-edit': ['read', 'apply']};", control)
        self.assertIn("controlRequest('poll'", control)
        self.assertIn("controlRequest('native-started'", control)
        self.assertIn("controlRequest('result'", control)
        self.assertEqual(trace['source_pins']['folders'], ['figma-bridge', 'library', 'tools'])
        self.assertEqual(trace['source_pins']['suffixes'], ['.css', '.html', '.js', '.json', '.py'])
        self.assertIn("for folder in ('tools', 'figma-bridge', 'library'):", source)
        self.assertIn("path.suffix in {'.py', '.js', '.html', '.css', '.json'}", source)
        tasks = (ROOT / 'docs/development-roadmap/RD-07-runtime-boundaries/tasks.md').read_text(encoding='utf-8')
        self.assertIn('workspace_transport', tasks)
        self.assertIn('도메인 검사는 workspace_control', tasks)
        self.assertIn('publisher 조립과 trusted_sources는 이 단위에서 옮기지 않는다', tasks)


if __name__ == '__main__':
    unittest.main()
