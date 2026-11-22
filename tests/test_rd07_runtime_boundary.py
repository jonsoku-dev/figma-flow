"""Pin the current control transport trace and trusted source range."""
import json
import subprocess
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace
import figma_control as control_server


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
        expected = trace['allowed']
        self.assertEqual(expected, {
            'review': ['create'],
            'import': ['read', 'import', 'sync', 'native-summary'],
            'discover': ['read', 'native-summary', 'select-node', 'selection-info', 'viewer-history', 'viewer-language'],
            'sync': ['read', 'apply'],
            'native-edit': ['read', 'apply', 'carousel-select', 'carousel-present'],
        })
        policy = json.loads((ROOT / 'library/figma-profile/policy.json').read_bytes())
        self.assertEqual(policy['taskOperations'], expected)
        self.assertEqual(control_server.OPERATIONS, {kind: set(ops) for kind, ops in expected.items()})
        control = (ROOT / 'figma-bridge/workspace_control.js').read_text(encoding='utf-8')
        program = 'const WORKSPACE_PROFILE_POLICY = ' + json.dumps(policy) + ';\n' + control
        actual = subprocess.check_output(['node'], input=program + '\nconsole.log(JSON.stringify(controlAllowed))', text=True)
        self.assertEqual(json.loads(actual), expected)
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
