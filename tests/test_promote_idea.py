import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from direction_fixture import selected_direction
import promote_idea

ROOT = Path(__file__).resolve().parents[1]
PROMOTE = ROOT / 'tools/promote_idea.py'


class PromoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = self.root / 'brief.md'
        self.brief.write_text('Show a count and increment it. Treat <script> as plain text.\n')
        self.draft = self.root / 'draft.json'
        self.raw = {'version': 1, 'nodes': [
            {'id': 'REQ-001', 'type': 'requirement', 'title': 'Increment', 'status': 'planned'},
            {'id': 'SCR-001', 'type': 'screen', 'title': 'Counter', 'status': 'planned'}],
            'edges': [{'from': 'REQ-001', 'to': 'SCR-001', 'type': 'appears on'}]}
        self.draft.write_text(json.dumps(self.raw))
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(json.dumps({'version': 1, 'projects': [dict(label='Counter', status='draft',
            graph_sha256=self.sha(self.draft), nodes=[dict(n, freshness='unverified') for n in self.raw['nodes']], edges=self.raw['edges'])]}))
        self.fixture = self.root / 'fixture'
        self.fixture.mkdir()
        for directory in ('app', 'tests'):
            (self.fixture / directory).mkdir()
        (self.fixture / 'screen-spec.md').write_text('SCR-001 displays the counter. Node behavior only; browser unchecked.')
        (self.fixture / 'app/index.html').write_text('<!doctype html><title>Counter</title><button>Increment</button>')
        (self.fixture / 'app/count.cjs').write_text('exports.increment = n => n + 1;\n')
        (self.fixture / 'tests/count.test.cjs').write_text("const test=require('node:test'),assert=require('node:assert/strict');\ntest('increment',()=>assert.equal(require('../app/count.cjs').increment(0),1));\n")
        nodes = [dict(n, status='observed', source='brief.md' if n['type'] == 'requirement' else 'screen-spec.md') for n in self.raw['nodes']]
        receipt = 'evidence/promotion-receipts/' + hashlib.sha256(b'tests/count.test.cjs').hexdigest()[:16] + '.tap'
        self.receipt = receipt
        (self.fixture / 'test-mapping.json').write_text(json.dumps({'version': 1, 'tests': {'TEST-001': ['tests/count.test.cjs']}}))
        nodes += [dict(id=key, type=kind, title=kind, status='verified', source=source) for key, kind, source in [
            ('CODE-001', 'code', 'app/count.cjs'), ('AC-001', 'acceptance', receipt),
            ('TEST-001', 'test', receipt)]]
        edges = self.raw['edges'] + [dict(zip(('from', 'to', 'type'), edge)) for edge in [
            ('REQ-001', 'AC-001', 'accepted by'), ('SCR-001', 'CODE-001', 'implemented by'),
            ('AC-001', 'TEST-001', 'checked by'), ('CODE-001', 'TEST-001', 'checked by'),
            ('REQ-001', 'CODE-001', 'depends-on'), ('CODE-001', 'TEST-001', 'depends-on')]]
        self.generated = {'version': 1, 'nodes': nodes, 'edges': edges}
        (self.fixture / 'graph.json').write_text(json.dumps(self.generated))
        bindings = {'version': 1, 'delivery': {'intent': 'technical'}, 'authorities': {'intent': 'brief.md', 'implementation': 'app/count.cjs'},
                    'dependency_edge_types': ['depends-on'], 'evidence': {n['id']: [n['source']] for n in nodes}}
        bindings['evidence']['CODE-001'].append('app/index.html')
        for key in ('AC-001', 'TEST-001'):
            bindings['evidence'][key].append('tests/count.test.cjs')
        (self.fixture / 'bindings.json').write_text(json.dumps(bindings))
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        fake = self.bin / 'codex'
        fake.write_text('#!' + sys.executable + '\nREAL_CODEX=' + repr(str(Path(shutil.which('codex')).resolve())) + '\n' + """import json,os,pathlib,shutil,sys
if sys.argv[1:2] == ['sandbox']: os.execv(REAL_CODEX,[REAL_CODEX,*sys.argv[1:]])
prompt=sys.stdin.read()
pathlib.Path('invocation.json').write_text(json.dumps({'argv':sys.argv[1:],'prompt':prompt}))
if os.environ.get('FAKE_FAIL'): sys.exit(7)
fixture=os.environ.get('PROMOTION_REPAIR_FIXTURE',os.environ['PROMOTION_FIXTURE']) if 'Repair the existing' in prompt else os.environ['PROMOTION_FIXTURE']
shutil.copytree(fixture, pathlib.Path.cwd(), dirs_exist_ok=True)
if os.environ.get('REPLACE_LOGS'):
 shutil.rmtree('logs');os.symlink(os.environ['REPLACE_LOGS'],'logs')
print('Generated fixture, controlled fake Codex; not a real model run.')
""")
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ.get('PATH', ''), PROMOTION_FIXTURE=str(self.fixture))
        self.out = self.root / 'project'
        baseline = self.root / 'existing-ui.html'
        if (self.fixture / 'app/index.html').exists():
            baseline.write_bytes((self.fixture / 'app/index.html').read_bytes())
        catalog = json.loads(self.catalog.read_text())
        catalog['projects'][0]['technical_scope'] = {'targets': ['app/count.cjs'], 'protected_ui': [
            {'path': 'app/index.html', 'source': str(baseline), 'sha256': self.sha(baseline)}]}
        self.catalog.write_text(json.dumps(catalog))

    def sha(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_promote(self, *extra, out=None, env=None):
        baseline = self.root / 'existing-ui.html'
        if (self.fixture / 'app/index.html').exists():
            baseline.write_bytes((self.fixture / 'app/index.html').read_bytes())
        catalog = json.loads(self.catalog.read_text())
        catalog['projects'][0]['technical_scope'] = {'targets': ['app/count.cjs'], 'protected_ui': [
            {'path': 'app/index.html', 'source': str(baseline), 'sha256': self.sha(baseline)}]}
        self.catalog.write_text(json.dumps(catalog))
        return subprocess.run([sys.executable, str(PROMOTE), '--catalog', str(self.catalog), '--idea', 'Counter',
            '--graph', str(self.draft), '--brief', str(self.brief), '--intent', 'technical', '--out', str(out or self.out), *extra],
            capture_output=True, text=True, env=env or self.env, timeout=20)

    def test_default_ui_creation_requires_current_selection_before_output(self):
        result = self.run_promote('--intent', 'create')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WAIT_SELECTION', result.stderr)
        self.assertFalse(self.out.exists())
        claim = self.root / 'approval.json'
        claim.write_text('{"approved":true}')
        result = self.run_promote('--intent', 'create', '--selection', str(claim))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.out.exists())

    def test_exploratory_preparation_does_not_authorize_later_finish(self):
        result = self.run_promote('--intent', 'create', '--prepare-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = {str(path.relative_to(self.out)): path.read_bytes() for path in self.out.rglob('*') if path.is_file()}
        result = subprocess.run([sys.executable, str(PROMOTE), '--finish', '--out', str(self.out)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WAIT_SELECTION', result.stderr)
        self.assertEqual(before, {str(path.relative_to(self.out)): path.read_bytes() for path in self.out.rglob('*') if path.is_file()})
        self.assertFalse((self.out / 'invocation.json').exists())

    def test_exact_user_choice_admits_ui_entry_and_wrong_graph_does_not(self):
        with selected_direction(self.root, self.draft) as chosen:
            selected_manifest = json.loads(chosen.manifest.read_text())
            self.brief.write_bytes(Path(selected_manifest['brief']['path']).read_bytes())
            draft = json.loads(self.draft.read_text())
            catalog = json.loads(self.catalog.read_text())
            catalog['projects'][0].update(graph_sha256=self.sha(self.draft), nodes=draft['nodes'], edges=draft['edges'])
            self.catalog.write_text(json.dumps(catalog))
            with patch.object(promote_idea, 'trusted_executable', return_value='codex'), patch.object(promote_idea, 'run_logged', side_effect=RuntimeError('generator reached')) as execute:
                with self.assertRaisesRegex(RuntimeError, 'generator reached'):
                    promote_idea.promote(self.catalog, 'Counter', self.draft, self.brief, self.out, selection_path=chosen.selection_path)
                execute.assert_called_once()
            other = self.root / 'wrong-graph.json'
            other.write_text(json.dumps(self.raw))
            with patch.object(promote_idea, 'run_logged') as execute:
                with self.assertRaises(ValueError):
                    promote_idea.promote(self.catalog, 'Counter', other, self.brief, self.root / 'wrong', selection_path=chosen.selection_path)
                execute.assert_not_called()
            self.assertFalse((self.root / 'wrong').exists())

    def test_changed_current_brief_cannot_reuse_local_selection(self):
        with selected_direction(self.root, self.draft) as chosen:
            draft = json.loads(self.draft.read_text())
            catalog = json.loads(self.catalog.read_text())
            catalog['projects'][0].update(graph_sha256=self.sha(self.draft), nodes=draft['nodes'], edges=draft['edges'])
            self.catalog.write_text(json.dumps(catalog))
            for content in ('A changed local requirement.', 'Figma에서 노트 앱을 새로 만들어줘. Dev Mode 없이.'):
                with self.subTest(content=content):
                    self.brief.write_text(content)
                    with patch.object(promote_idea, 'trusted_executable') as executable, patch.object(promote_idea, 'run_logged') as execute:
                        with self.assertRaisesRegex(ValueError, 'current brief differs'):
                            promote_idea.promote(self.catalog, 'Counter', self.draft, self.brief, self.out, selection_path=chosen.selection_path)
                        executable.assert_not_called()
                        execute.assert_not_called()
                    self.assertFalse(self.out.exists())

    def test_prepared_job_rechecks_current_brief_before_any_status_write(self):
        with selected_direction(self.root, self.draft) as chosen:
            selected_manifest = json.loads(chosen.manifest.read_text())
            self.brief.write_bytes(Path(selected_manifest['brief']['path']).read_bytes())
            draft = json.loads(self.draft.read_text())
            catalog = json.loads(self.catalog.read_text())
            catalog['projects'][0].update(graph_sha256=self.sha(self.draft), nodes=draft['nodes'], edges=draft['edges'])
            self.catalog.write_text(json.dumps(catalog))
            promote_idea.promote(self.catalog, 'Counter', self.draft, self.brief, self.out, prepare_only=True)
            (self.out / 'brief.md').write_text('Create a new Figma app without Dev Mode.')
            before = {str(path.relative_to(self.out)): path.read_bytes() for path in self.out.rglob('*') if path.is_file()}
            with patch.object(promote_idea, 'run_logged') as execute:
                with self.assertRaisesRegex(ValueError, 'current brief differs'):
                    promote_idea.finish_prepared(self.out, selection_path=chosen.selection_path)
                execute.assert_not_called()
            self.assertEqual(before, {str(path.relative_to(self.out)): path.read_bytes() for path in self.out.rglob('*') if path.is_file()})

    def test_technical_flag_alone_cannot_create_ui_and_baseline_cannot_change(self):
        catalog = json.loads(self.catalog.read_text())
        del catalog['projects'][0]['technical_scope']
        self.catalog.write_text(json.dumps(catalog))
        with patch.object(promote_idea, 'run_logged') as execute:
            with self.assertRaisesRegex(ValueError, 'WAIT_SELECTION'):
                promote_idea.promote(self.catalog, 'Counter', self.draft, self.brief, self.out, intent='technical')
            execute.assert_not_called()
        self.assertFalse(self.out.exists())
        result = self.run_promote('--prepare-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        shutil.copytree(self.fixture, self.out, dirs_exist_ok=True)
        (self.out / 'app/index.html').write_text('<h1>New UI</h1>')
        result = subprocess.run([sys.executable, str(PROMOTE), '--finish', '--out', str(self.out)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('protected existing UI', result.stderr)
        self.assertFalse((self.out / 'admission').exists())

    def test_complete_job_runs_fixed_cli_real_tests_and_admission(self):
        result = self.run_promote('--catalog-sha256', self.sha(self.catalog), '--graph-sha256', self.sha(self.draft), '--brief-sha256', self.sha(self.brief))
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads((self.out / 'invocation.json').read_text())
        self.assertEqual(invocation['argv'], ['exec', '--sandbox', 'workspace-write', '--skip-git-repo-check', '-C', str(self.out), '-'])
        self.assertIn('$figma-flow', invocation['prompt'])
        self.assertIn('UNTRUSTED PRODUCT DATA', invocation['prompt'])
        self.assertEqual((self.out / 'draft.json').read_bytes(), self.draft.read_bytes())
        self.assertEqual((self.out / 'brief.md').read_bytes(), self.brief.read_bytes())
        self.assertIn('# pass 1', (self.out / self.receipt).read_text())
        self.assertEqual(json.loads((self.out / 'admission/summary.json').read_text())['status'], 'current')
        self.assertEqual(json.loads((self.out / 'promotion-status.json').read_text())['phase'], 'accepted')
        execution = json.loads((self.out / 'logs/tests.json').read_text())
        self.assertEqual(execution['sandbox']['probe_exit_code'], 0)
        self.assertEqual(execution['tests'][0]['exit_code'], 0)
        self.assertIn(':read-only', execution['tests'][0]['argv'])
        for name in ('generator', 'admission'):
            self.assertEqual(json.loads((self.out / f'logs/{name}.json').read_text())['exit_code'], 0)
        accepted = json.loads((self.out / 'logs/acceptance.json').read_text())
        audit = accepted['audit']
        self.assertEqual(audit['sha256'], self.sha(self.out / audit['report']))
        self.assertEqual(audit['status'], 'review')
        report = json.loads((self.out / audit['report']).read_text())
        self.assertTrue(report['brief_consistency']['unsupported'])
        self.assertFalse(report['source_dependencies']['missing'])

    def bind_html_import(self, *, declare):
        (self.fixture / 'app/index.html').write_text('<!doctype html><title>Counter</title><script src="./count.cjs"></script>')
        graph = json.loads((self.fixture / 'graph.json').read_text())
        graph['nodes'].append(dict(id='CODE-002', type='code', title='HTML entry', status='observed', source='app/index.html'))
        graph['edges'] += [dict(zip(('from', 'to', 'type'), edge)) for edge in [
            ('CODE-002', 'TEST-001', 'checked by'), ('CODE-002', 'TEST-001', 'depends-on')]]
        if declare:
            graph['edges'].append({'from': 'CODE-001', 'to': 'CODE-002', 'type': 'depends-on'})
        (self.fixture / 'graph.json').write_text(json.dumps(graph))
        bindings = json.loads((self.fixture / 'bindings.json').read_text())
        bindings['evidence']['CODE-001'] = ['app/count.cjs']
        bindings['evidence']['CODE-002'] = ['app/index.html']
        (self.fixture / 'bindings.json').write_text(json.dumps(bindings))

    def test_declared_static_html_import_can_be_admitted_with_review_limits(self):
        self.bind_html_import(declare=True)
        result = self.run_promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads((self.out / 'logs/attempt-1/audit.json').read_text())
        observed = audit['source_dependencies']['observations']
        self.assertTrue(any(item['from'] == 'CODE-001' and item['to'] == 'CODE-002' and item['declared_path'] for item in observed))
        self.assertFalse(audit['source_dependencies']['missing'])

    def test_passing_tests_cannot_hide_missing_html_import_dependency(self):
        self.bind_html_import(declare=False)
        result = self.run_promote()
        self.assertNotEqual(result.returncode, 0)
        audit = json.loads((self.out / 'logs/attempt-1/audit.json').read_text())
        self.assertEqual(audit['status'], 'findings')
        self.assertTrue(audit['source_dependencies']['missing'])
        self.assertTrue((self.out / 'logs/repair-1.json').exists())
        self.assertFalse((self.out / 'logs/repair-2.json').exists())
        self.assertFalse((self.out / 'admission').exists())
        self.assertFalse((self.out / self.receipt).exists())

    def test_contradictory_pinned_brief_cannot_be_accepted_or_repaired(self):
        self.brief.write_text('The session persists after reload.\nReload resets the session.\n')
        result = self.run_promote()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('contradictory pinned brief', result.stderr)
        audit = json.loads((self.out / 'logs/attempt-1/audit.json').read_text())
        self.assertEqual(audit['brief_consistency']['status'], 'fail')
        self.assertFalse((self.out / 'logs/repair-1.json').exists())
        self.assertFalse((self.out / 'admission').exists())
        self.assertEqual((self.out / 'brief.md').read_bytes(), self.brief.read_bytes())

    def test_generated_spec_contradiction_has_one_bounded_repair(self):
        self.brief.write_text('The session persists after reload.\n')
        repaired = self.root / 'repaired'
        shutil.copytree(self.fixture, repaired)
        (self.fixture / 'screen-spec.md').write_text('Reload resets the session.\n')
        result = self.run_promote(env=dict(self.env, PROMOTION_REPAIR_FIXTURE=str(repaired)))
        self.assertEqual(result.returncode, 0, result.stderr)
        first = json.loads((self.out / 'logs/attempt-1/audit.json').read_text())
        second = json.loads((self.out / 'logs/attempt-2/audit.json').read_text())
        self.assertEqual(first['brief_consistency']['status'], 'fail')
        self.assertFalse(second['brief_consistency']['findings'])
        self.assertTrue((self.out / 'logs/repair-1-before/screen-spec.md').exists())
        self.assertEqual((self.out / 'brief.md').read_bytes(), self.brief.read_bytes())

    def test_prepare_only_then_finish_has_no_build_claim_before_finish(self):
        result = self.run_promote('--prepare-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.out / 'invocation.json').exists())
        self.assertFalse((self.out / 'admission').exists())
        self.assertEqual(json.loads((self.out / 'promotion-status.json').read_text())['phase'], 'prepared')
        shutil.copytree(self.fixture, self.out, dirs_exist_ok=True)
        result = subprocess.run([sys.executable, str(PROMOTE), '--finish', '--out', str(self.out)], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stale_hash_and_startup_pin_reject_before_project_creation(self):
        self.draft.write_text(self.draft.read_text() + '\n')
        result = self.run_promote()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA-256', result.stderr)
        self.assertFalse(self.out.exists())
        result = self.run_promote('--catalog-sha256', '0' * 64)
        self.assertIn('requested SHA-256 pin', result.stderr)
        self.assertFalse(self.out.exists())

    def test_existing_output_and_symlink_are_preserved(self):
        self.out.mkdir()
        marker = self.out / 'keep'
        marker.write_text('mine')
        result = self.run_promote()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), 'mine')
        link = self.root / 'link'
        link.symlink_to(self.root / 'missing')
        result = self.run_promote(out=link)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(link.is_symlink())

    def test_generator_failure_keeps_partial_logs_and_no_admission(self):
        result = self.run_promote(env=dict(self.env, FAKE_FAIL='1'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('failed (7)', result.stderr)
        self.assertTrue((self.out / 'logs/generator.stderr.log').is_file())
        self.assertEqual(json.loads((self.out / 'promotion-status.json').read_text())['phase'], 'partial-failed')
        self.assertFalse((self.out / 'admission').exists())

    def test_generated_graph_cannot_drop_ids_or_expand_screens(self):
        for index, alter in enumerate(('drop', 'extra')):
            graph = json.loads(json.dumps(self.generated))
            if alter == 'drop':
                for n in graph['nodes']:
                    if n['id'] == 'SCR-001': n['id'] = 'SCR-RENAMED'
                for e in graph['edges']:
                    for field in ('from', 'to'):
                        if e[field] == 'SCR-001': e[field] = 'SCR-RENAMED'
            else:
                graph['nodes'].append(dict(id='SCR-002', type='screen', title='Extra', status='observed', source='screen-spec.md'))
                graph['edges'] += [dict(zip(('from', 'to', 'type'), e)) for e in [('REQ-001', 'SCR-002', 'appears on'), ('SCR-002', 'CODE-001', 'implemented by')]]
            (self.fixture / 'graph.json').write_text(json.dumps(graph))
            out = self.root / f'bad-{index}'
            result = self.run_promote(out=out)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((out / 'admission').exists())

    def test_failed_behavior_tests_never_admit(self):
        (self.fixture / 'app/count.cjs').write_text('exports.increment = n => n - 1;\n')
        result = self.run_promote()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Behavior tests failed', result.stderr)
        self.assertIn('# fail 1', next((self.out / 'logs/attempt-1/tests').glob('*.tap')).read_text())
        self.assertFalse((self.out / self.receipt).exists())
        self.assertFalse((self.out / 'admission').exists())

    def test_generated_test_outside_write_is_blocked_and_credentials_removed(self):
        outside = self.root / 'must-not-be-created'
        (self.fixture / 'tests/count.test.cjs').write_text(
            "const test=require('node:test'),assert=require('node:assert/strict');\n"
            "test('confinement',()=>{assert.equal(process.env.SECRET_TOKEN,undefined);"
            "require('node:fs').writeFileSync(" + json.dumps(str(outside)) + ",'forbidden')});\n")
        result = self.run_promote(env=dict(self.env, SECRET_TOKEN='do-not-inherit'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(outside.exists())
        self.assertIn('ERR_ACCESS_DENIED', ''.join(p.read_text() for p in (self.out / 'logs/attempt-1/tests').glob('*.stderr.log')))
        self.assertFalse((self.out / 'logs/repair-1.json').exists())
        self.assertFalse((self.out / 'admission').exists())

    def test_zero_real_tests_and_skipped_tests_cannot_pass(self):
        for index, body in enumerate(("// no tests\n", "require('node:test')('skipped',{skip:true},()=>{});\n")):
            (self.fixture / 'tests/count.test.cjs').write_text(body)
            out = self.root / f'no-tests-{index}'
            result = self.run_promote(out=out)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((out / 'admission').exists())

    def test_generated_hardlink_is_rejected_without_truncating_target(self):
        outside = self.root / 'outside'
        outside.write_text('preserve')
        os.link(outside, self.fixture / 'app/linked.cjs')
        result = self.run_promote()
        # copytree copies contents, so plant a hardlink in agent-native prepared output.
        other = self.root / 'prepared-linked'
        result = self.run_promote('--prepare-only', out=other)
        self.assertEqual(result.returncode, 0, result.stderr)
        shutil.copytree(self.fixture, other, dirs_exist_ok=True)
        (other / 'app/linked.cjs').unlink()
        os.link(outside, other / 'app/linked.cjs')
        result = subprocess.run([sys.executable, str(PROMOTE), '--finish', '--out', str(other)], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hardlinks', result.stderr)
        self.assertEqual(outside.read_text(), 'preserve')

    def test_bounded_repair_publishes_only_success_and_preserves_failed_attempt(self):
        repaired = self.root / 'repaired'
        shutil.copytree(self.fixture, repaired)
        (self.fixture / 'app/count.cjs').write_text('exports.increment=n=>n-1;\n')
        result = self.run_promote(env=dict(self.env, PROMOTION_REPAIR_FIXTURE=str(repaired)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / 'logs/repair-1.json').is_file())
        self.assertFalse((self.out / 'logs/repair-2.json').exists())
        first = next((self.out / 'logs/attempt-1/tests').glob('*.tap'))
        self.assertIn('# fail 1', first.read_text())
        self.assertIn('# pass 1', (self.out / self.receipt).read_text())
        self.assertTrue((self.out / 'logs/attempt-2/tests.json').is_file())
        accepted = json.loads((self.out / 'logs/acceptance.json').read_text())
        self.assertEqual(accepted['app_sha256']['app/count.cjs'], self.sha(self.out / 'app/count.cjs'))

    def test_safe_finish_can_resume_repaired_assertion_failure(self):
        result = self.run_promote('--prepare-only')
        self.assertEqual(result.returncode, 0)
        shutil.copytree(self.fixture, self.out, dirs_exist_ok=True)
        (self.out / 'app/count.cjs').write_text('exports.increment=n=>n-1;\n')
        argv = [sys.executable, str(PROMOTE), '--finish', '--out', str(self.out)]
        result = subprocess.run(argv, capture_output=True, text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(json.loads((self.out / 'promotion-status.json').read_text())['recoverable'])
        failed = next((self.out / 'logs/attempt-1/tests').glob('*.tap'))
        before = failed.read_bytes()
        (self.out / 'app/count.cjs').write_text('exports.increment=n=>n+1;\n')
        result = subprocess.run(argv, capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(failed.read_bytes(), before)
        accepted_status = (self.out / 'promotion-status.json').read_bytes()
        result = subprocess.run(argv, capture_output=True, text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.out / 'promotion-status.json').read_bytes(), accepted_status)

    def test_generator_cannot_redirect_controller_logs(self):
        external = self.root / 'outside-logs'
        external.mkdir()
        result = self.run_promote(env=dict(self.env, REPLACE_LOGS=str(external)))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(external.iterdir()), [])
        self.assertFalse((self.out / 'logs/repair-1.json').exists())

    def test_source_drift_during_tests_is_not_accepted(self):
        import time
        result = self.run_promote('--prepare-only')
        self.assertEqual(result.returncode, 0)
        shutil.copytree(self.fixture, self.out, dirs_exist_ok=True)
        (self.out / 'tests/count.test.cjs').write_text(
            "const test=require('node:test'),assert=require('node:assert/strict');"
            "const fn=require('../app/count.cjs').increment;"
            "test('slow increment',async()=>{assert.equal(fn(0),1);await new Promise(r=>setTimeout(r,1200))});")
        process = subprocess.Popen([sys.executable, str(PROMOTE), '--finish', '--out', str(self.out)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if list((self.out / 'logs').glob('attempt-*/tests/*.tap')):
                time.sleep(0.4)
                (self.out / 'app/count.cjs').write_text('exports.increment=n=>n-1;\n')
                break
            time.sleep(0.03)
        stdout, stderr = process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0, stdout + stderr)
        self.assertIn('source changed', stderr)
        self.assertFalse((self.out / 'admission').exists())
        self.assertFalse((self.out / 'logs/acceptance.json').exists())

    def test_owned_generator_timeout_kills_descendant_process_group(self):
        import importlib.util
        import time
        result = self.run_promote('--prepare-only')
        self.assertEqual(result.returncode, 0)
        sys.path.insert(0, str(ROOT / 'tools'))
        try:
            spec = importlib.util.spec_from_file_location('promoter_timeout_test', PROMOTE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(ROOT / 'tools'))
        marker = self.root / 'descendant-survived'
        child = 'import pathlib,time;time.sleep(.4);pathlib.Path(' + repr(str(marker)) + ').write_text("bad")'
        parent = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",' + repr(child) + ']);time.sleep(5)'
        execution = module.run_logged([sys.executable, '-c', parent], self.out, 'logs/timeout', timeout=.1)
        self.assertEqual(execution['exit_code'], 124)
        self.assertTrue(execution['timed_out'])
        time.sleep(.5)
        self.assertFalse(marker.exists())

    def test_changed_pinned_copy_missing_output_and_external_reference_fail(self):
        (self.fixture / 'brief.md').write_text('Replaced brief')
        result = self.run_promote()
        self.assertIn('Pinned brief changed', result.stderr)
        (self.fixture / 'brief.md').unlink()
        (self.fixture / 'app/index.html').unlink()
        result = self.run_promote(out=self.root / 'missing-artifact')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'missing-artifact/admission').exists())
        (self.fixture / 'app/index.html').write_text('<title>Counter</title>')
        data = json.loads((self.fixture / 'bindings.json').read_text())
        data['evidence']['CODE-001'].append('../brief.md')
        (self.fixture / 'bindings.json').write_text(json.dumps(data))
        result = self.run_promote(out=self.root / 'external')
        self.assertIn('escapes the project', result.stderr)


if __name__ == '__main__':
    unittest.main()
