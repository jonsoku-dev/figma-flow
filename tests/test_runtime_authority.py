import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import runtime_authority


class RuntimeAuthorityTests(unittest.TestCase):
    def test_current_runtime_uses_the_policy_as_its_task_authority(self):
        self.assertEqual(runtime_authority.check(ROOT), [])

    def test_unmapped_task_operation_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('figma-bridge/workspace_control.js', 'figma-bridge/workspace_host.js',
                             'tools/figma_workspace.py', 'tools/operation_detail.py'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            policy_path = root / 'library/figma-profile/policy.json'
            policy_path.parent.mkdir(parents=True)
            policy = json.loads((ROOT / 'library/figma-profile/policy.json').read_text(encoding='utf-8'))
            policy['taskOperations']['discover'].append('unmapped-test-operation')
            policy_path.write_text(json.dumps(policy), encoding='utf-8')

            codes = {finding['code'] for finding in runtime_authority.check(root)}
            self.assertIn('TASK_OPERATION_UNMAPPED', codes)

    def test_undeclared_seat_value_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('figma-bridge/workspace_control.js', 'figma-bridge/workspace_host.js',
                             'tools/figma_workspace.py', 'tools/operation_detail.py'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            policy_path = root / 'library/figma-profile/policy.json'
            policy_path.parent.mkdir(parents=True)
            policy = json.loads((ROOT / 'library/figma-profile/policy.json').read_text(encoding='utf-8'))
            policy['facts']['declaredDevSeat']['seat'].append('unlisted-test-seat')
            policy_path.write_text(json.dumps(policy), encoding='utf-8')

            findings = runtime_authority.check(root)
            self.assertTrue(any(item['code'] == 'PROFILE_OPTION_UNDECLARED' for item in findings))

    def test_duplicated_fallback_matrix_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ('figma-bridge/workspace_host.js', 'tools/figma_workspace.py',
                             'tools/operation_detail.py'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            control = root / 'figma-bridge/workspace_control.js'
            control.parent.mkdir(parents=True, exist_ok=True)
            source = (ROOT / 'figma-bridge/workspace_control.js').read_text(encoding='utf-8')
            source = source.replace(
                'Object.freeze({});',
                "{review: ['create'], import: ['read']};",
                1,
            )
            control.write_text(source, encoding='utf-8')
            policy_path = root / 'library/figma-profile/policy.json'
            policy_path.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'library/figma-profile/policy.json', policy_path)

            codes = {finding['code'] for finding in runtime_authority.check(root)}
            self.assertIn('CONTROL_AUTHORITY_FALLBACK', codes)

    def test_duplicated_kind_matrices_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative_files = (
                'figma-bridge/workspace_control.js', 'figma-bridge/workspace_host.js',
                'tools/figma_workspace.py', 'tools/operation_detail.py',
            )
            for relative in relative_files:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            policy_path = root / 'library/figma-profile/policy.json'
            policy_path.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'library/figma-profile/policy.json', policy_path)

            host = root / 'figma-bridge/workspace_host.js'
            host.write_text(host.read_text(encoding='utf-8').replace(
                "const workspaceKinds = new Set(typeof WORKSPACE_PROFILE_POLICY !== 'undefined'\n  ? Object.keys(WORKSPACE_PROFILE_POLICY?.taskOperations || {}) : []);",
                "const workspaceKinds = new Set(['discover', 'import']);"), encoding='utf-8')
            detail = root / 'tools/operation_detail.py'
            detail.write_text(detail.read_text(encoding='utf-8').replace(
                "ALLOWED_TASK_KINDS = set(_PROFILE_POLICY['taskOperations'])",
                "ALLOWED_TASK_KINDS = {'discover', 'import'}"), encoding='utf-8')
            workspace = root / 'tools/figma_workspace.py'
            workspace.write_text(workspace.read_text(encoding='utf-8').replace(
                "return tuple(sorted(policy['taskOperations']))",
                "return ('discover', 'import')"), encoding='utf-8')

            codes = {finding['code'] for finding in runtime_authority.check(root)}
            self.assertTrue({
                'HOST_KIND_POLICY_NOT_USED', 'HOST_KIND_MATRIX_DUPLICATED',
                'DETAIL_KIND_POLICY_NOT_USED', 'DETAIL_KIND_MATRIX_DUPLICATED',
                'BUNDLE_KIND_POLICY_NOT_USED', 'BUNDLE_KIND_MATRIX_DUPLICATED',
            }.issubset(codes), sorted(codes))

    def test_dispatch_without_policy_denies_registered_task(self):
        control = (ROOT / 'figma-bridge/workspace_control.js').read_text(encoding='utf-8')
        program = "globalThis.workspaceHomeSession = '';\n" + control + """
(async () => {
  try {
    await controlExecute({kind:'discover',revision:'r'}, {operation:'read',revision:'r'});
    process.exitCode = 1;
  } catch (error) {
    if (!/Prepared task changed/.test(error.message)) throw error;
  }
})();
"""
        completed = subprocess.run(['node', '-e', program], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_view_graph_gate_reads_candidate_root_without_git(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            windows = json.loads((ROOT / 'library/figma-profile/native-windows.json').read_bytes())
            required = (
                'library/figma-profile/native-windows.json', *windows['bindings'],
                'library/component-families.json', 'figma-bridge/semantic_components.js',
                'figma-bridge/workspace_control.js', 'figma-bridge/workspace_host.js',
                'tools/figma_workspace.py', 'tools/operation_detail.py', 'tools/plugin_panel.py',
                'panel-ui/src/app.jsx', 'panel-ui/build.mjs', 'panel-ui/view-registry.mjs',
                'library/figma-profile/policy.json', 'library/panel-design/views.json',
            )
            for relative in required:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            for source in (ROOT / 'figma-bridge').glob('*.html'):
                shutil.copyfile(source, root / 'figma-bridge' / source.name)
            for source in (ROOT / 'tools').glob('*.py'):
                shutil.copyfile(source, root / 'tools' / source.name)
            graph_path = root / 'library/panel-design/views.json'
            graph = json.loads(graph_path.read_text(encoding='utf-8'))
            for node in graph['nodes']:
                if node.get('type') != 'code' or not node.get('source'):
                    continue
                parts = Path(node['source']).parts
                original = ROOT.joinpath(*parts[parts.index('panel-ui'):])
                target = (graph_path.parent / node['source']).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)

            self.assertEqual(runtime_authority.check(root), [])
            graph['nodes'][1]['source'] = '../../panel-ui/src/Missing.jsx'
            graph_path.write_text(json.dumps(graph), encoding='utf-8')
            findings = runtime_authority.check(root)
            self.assertTrue(any(item['code'] == 'PANEL_VIEW_GRAPH_INVALID' for item in findings))


if __name__ == '__main__':
    unittest.main()
