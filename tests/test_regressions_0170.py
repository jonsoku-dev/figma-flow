"""0.17.0 audit fixes and features. Each defect case here failed on 0.16.1 (checked against main)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import audit_brief  # noqa: E402
import design_directions  # noqa: E402
import review_destination  # noqa: E402
import safe_node_tests  # noqa: E402
from direction_fixture import selected_direction  # noqa: E402


class DestinationTests(unittest.TestCase):
    LOCAL = ['Skip Figma; HTML only. Build a campaign landing page', 'Do not create a Figma file, just HTML',
             'instead of Figma, build local HTML', 'no need for Figma', 'Figma is not needed', 'without using Figma',
             '피그마는 필요 없어요. HTML로만 캠페인 페이지 만들어줘', '피그마 안 써도 돼', 'Figma가 아니라 HTML로',
             '피그마로 하지 말고 웹페이지로', 'Figma 파일은 만들지 마. HTML로만', '피그마 없이 HTML로만',
             'Figmaは使わないで、HTMLだけでキャンペーンページを作って', 'Figmaを使わずにHTMLだけで', 'フィグマは不要']
    FIGMA = ['We have no Figma file yet, so create the campaign page drafts in Figma',
             '아직 피그마 파일 없이 시작하는 신규 게임이라 피그마에 캠페인 시안을 만들어줘',
             'Figma에 시안 만들고 HTML 페이지만 구현', 'Use Figma without Dev Mode', '피그마로 캠페인 시안을 만들어줘']

    def test_explicit_exclusions_resolve_local(self):
        for text in self.LOCAL:
            with self.subTest(text=text):
                self.assertEqual(review_destination.requested(text), 'local')
                self.assertEqual(review_destination.resolve(text, explicit='local'), 'local')

    def test_figma_requests_stay_figma(self):
        for text in self.FIGMA:
            with self.subTest(text=text):
                self.assertEqual(review_destination.requested(text), 'figma')
                self.assertEqual(review_destination.resolve(text, explicit='figma'), 'figma')


class RevocationTests(unittest.TestCase):
    def after_selection(self, message):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as fixture:
            design_directions.require_selected(fixture.selection_path)
            with fixture.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': message}}) + '\n')
            try:
                design_directions.require_selected(fixture.selection_path)
                return 'selected'
            except design_directions.SelectionRequired:
                return 'revoked'

    def test_ordinary_follow_up_keeps_the_selection(self):
        for message in ('다시 선택할 필요 없어요. A로 확정입니다', '시안 A 이미지를 다시 보여줘',
                        'Great, now rework the header design copy for mobile'):
            with self.subTest(message=message):
                self.assertEqual(self.after_selection(message), 'selected')

    def test_explicit_reselection_still_revokes(self):
        for message in ('시안을 다시 선택할게요', '다시 고를래', 'reselect', 'rework the directions', '선택 취소'):
            with self.subTest(message=message):
                self.assertEqual(self.after_selection(message), 'revoked')


class ReloadNegationTests(unittest.TestCase):
    def audit(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'brief.md'
            path.write_text(text)
            return audit_brief.audit([path])

    def test_negated_reset_with_preserve_is_not_a_contradiction(self):
        for text in ('Progress is not reset on reload.\nProgress is preserved after reload.\n',
                     'Progress is never lost on reload.\nProgress persists after reload.\n',
                     'The score should not be cleared on reload.\nThe score is kept after reload.\n',
                     '새로고침해도 진행 상황은 사라지지 않는다.\n새로고침 후에도 진행 상황을 유지한다.\n',
                     '새로고침해도 점수는 지워지지 않는다.\n새로고침 후에도 점수를 유지한다.\n'):
            with self.subTest(text=text):
                self.assertNotEqual(self.audit(text)['status'], 'fail')

    def test_genuine_contradiction_still_fails(self):
        self.assertEqual(self.audit('Reload resets the progress.\nProgress is preserved after reload.\n')['status'], 'fail')


class KillGroupTests(unittest.TestCase):
    def test_eperm_from_exited_group_returns_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            argv = ['/bin/sh', '-c', 'exit 0']
            with patch.object(safe_node_tests.os, 'killpg', side_effect=PermissionError(1, 'Operation not permitted')):
                code = safe_node_tests._execute(argv, base, base / 'out', base / 'err', 5)
            self.assertEqual(code, 0)

    def test_detached_pipe_holder_times_out_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            helper = sys.executable + ' -c "import os,time; os.setsid(); time.sleep(2)"'
            code = safe_node_tests._execute(['/bin/sh', '-c', helper + ' & exit 0'], base, base / 'out', base / 'err', .5)
            self.assertEqual(code, 124)


class CliErrorTests(unittest.TestCase):
    def test_figma_draft_cli_reports_errors_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/figma_draft.py'), 'prepare', '--manifest',
                                     str(Path(tmp) / 'missing.json'), '--out', str(Path(tmp) / 'out')], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(json.loads(result.stderr)['passed'])

    def test_malformed_readback_is_a_clean_error(self):
        for raw in ({'pages': [{'id': '1:1'}], 'variables': [None]},
                    {'pages': [{'id': '1:1', 'reactions': [{'actions': [None]}]}], 'variables': []},
                    {'pages': [{'id': '1:1', 'reactions': 'x'}], 'variables': []}):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'readback.json'
                path.write_text(json.dumps({'format': 'figma-flow-readback-v1', **raw}))
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/figma_bridge.py'), '--check-readback', str(path)],
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('Traceback', result.stderr)
                self.assertIn('figma-bridge:', result.stderr)

    def test_hex_case_is_not_a_color_mismatch(self):
        import figma_draft
        self.assertEqual(figma_draft._hex_map({'ink': '#AA4422'}), figma_draft._hex_map({'ink': '#aa4422'}))
        self.assertNotEqual(figma_draft._hex_map({'ink': '#AA4422'}), figma_draft._hex_map({'ink': '#aa4423'}))


class ProductionCompileTests(unittest.TestCase):
    """Production plugin compile/import cases (offline Plugin API mock; not live Figma)."""

    def compile_and_import(self, mutate, graph_mutate=None):
        import hashlib
        import shutil as _shutil
        import test_figma_bridge as bridge_tests
        node = _shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = bridge_tests.design()
            mutate(source)
            (root / 'resolved.json').write_text(json.dumps(source))
            digest = hashlib.sha256((root / 'resolved.json').read_bytes()).hexdigest()
            graph = bridge_tests.selected_graph(source)
            if graph_mutate:
                graph_mutate(graph)
            with selected_direction(root / 'directions', graph=graph, native_review=True) as admitted:
                bridge_tests.bridge.compile_plugin(root / 'resolved.json', digest, root / 'out',
                                                   selection_path=admitted.selection_path, product_graph=admitted.product_graph)
            (root / 'mock.cjs').write_text(bridge_tests.MOCK.split('(async()=>{')[0] + r'''
(async()=>{ load(process.argv[2]); await send({type:'ready'}); await send({type:'import'});
  console.log(JSON.stringify({imports:imported().length}));
})().catch(e=>{console.error(e);process.exitCode=1;});''')
            result = subprocess.run([node, str(root / 'mock.cjs'), str(root / 'out/code.js')], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout.strip().splitlines()[-1])

    def test_two_type_roles_with_one_size_value_import(self):
        def source(s):
            s['tokens']['type.label'] = {'type': 'dimension', 'value': '16px'}
            s['components']['button']['variants']['primary']['font-size'] = 'type.label'

        def graph(g):
            g['design_foundations']['roles'].append({'name': 'Label size', 'kind': 'typography', 'token': 'type/label', 'value': '16px'})
        self.assertEqual(self.compile_and_import(source, graph)['imports'], 1)

    def test_incompatible_or_doubled_component_props_fail_at_compile(self):
        def padding_color(s):
            s['components']['button']['variants']['primary']['padding'] = 'palette.blue'

        def doubled(s):
            s['tokens']['size.lg'] = {'type': 'dimension', 'value': '20px'}
            s['components']['button']['variants']['primary']['fontSize'] = 'size.lg'
        for mutate, message in ((padding_color, 'needs a compatible token type'), (doubled, 'only one spelling')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.compile_and_import(mutate)


class StatusTests(unittest.TestCase):
    def snapshot(self, root):
        import hashlib
        return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}

    def test_status_is_read_only_and_reports_freshness(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('status_demo', ROOT / 'examples/native-direction-review/demo.py')
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'workshop'
            manifest = Path(demo.instantiate(project)['manifest'])
            before = self.snapshot(project)
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/design_actions.py'), 'status', '--manifest', str(manifest)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(self.snapshot(project), before)
            self.assertEqual(report['writes'], [])
            self.assertEqual(report['workflow_symbol'], 'NATIVE_REVIEW_PENDING')
            self.assertTrue(report['inputs'] and all(item['status'] == 'current' for item in report['inputs']), report['inputs'])
            expected = [edge['event'] for edge in design_directions.workflow._GRAPH['edges'] if edge['from'] == report['workflow_state']]
            self.assertEqual([edge['event'] for edge in report['next_events']], expected)
            (project / 'brief.md').write_text('changed\n')
            preview = next(item for item in report['inputs'] if item['role'].startswith('preview-'))
            Path(preview['path']).unlink()
            report = design_directions.status(manifest)
            statuses = {(item['role'], item['path']): item['status'] for item in report['inputs']}
            self.assertEqual(statuses[('brief', next(i['path'] for i in report['inputs'] if i['role'] == 'brief'))], 'stale')
            self.assertEqual(statuses[(preview['role'], preview['path'])], 'missing')


class ErrorReportingTests(unittest.TestCase):
    def test_all_unused_color_roles_are_named_together(self):
        from draft_token_plan import foundation_bindings
        project = ROOT / 'examples/native-direction-review'
        candidate = json.loads((project / 'native-layout.json').read_text())['candidates'][0]
        graph = json.loads((project / candidate['graph']['path']).read_text())
        for name, value in (('unused-a', '#111112'), ('unused-b', '#111113')):
            candidate['colors'][name] = value
            graph['design_foundations']['roles'].append({'kind': 'color', 'token': 'color/' + name, 'value': value})
        with self.assertRaisesRegex(ValueError, r'color/unused-a, color/unused-b: no visible authored screen/control COLOR consumer \(2 roles\)'):
            foundation_bindings(candidate, graph)

    def test_control_role_needs_the_same_role_on_its_main_component(self):
        from draft_token_plan import foundation_bindings
        project = ROOT / 'examples/native-direction-review'
        candidate = json.loads((project / 'native-layout.json').read_text())['candidates'][0]
        graph = json.loads((project / candidate['graph']['path']).read_text())
        foundation_bindings(candidate, graph)  # Shipped example: instances and mains share roles.
        role = next(r for r in graph['design_foundations']['roles'] if r['token'] == 'space/content')
        role['native']['bindings'] = [b for b in role['native']['bindings'] if '.component.' not in b['key']]
        with self.assertRaisesRegex(ValueError, 'needs the same role on its main component'):
            foundation_bindings(candidate, graph)

    def test_blocked_cli_reports_a_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/design_actions.py'), 'status', '--manifest', str(Path(tmp) / 'x.json')],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)['cause'], 'invalid-input')


if __name__ == '__main__':
    unittest.main()
