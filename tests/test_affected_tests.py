import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'skills/figma-flow/scripts'))
import ssot


class AffectedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('brief.md', 'app.js', 'a.txt', 'b.txt', 'proof.txt'):
            (self.root / name).write_text(name)
        for name in ('a', 'b'):
            (self.root / f'{name}.test.js').write_text("const {test}=require('node:test'); test('works',()=>{});\n")
        nodes = [{'id': n, 'type': t, 'title': n, 'status': 'observed', 'source': s} for n, t, s in [
            ('REQ-1', 'requirement', 'proof.txt'), ('SCR-A', 'screen', 'a.txt'), ('CODE-A', 'code', 'a.txt'), ('TEST-A', 'test', 'a.test.js'),
            ('SCR-B', 'screen', 'b.txt'), ('CODE-B', 'code', 'b.txt'), ('TEST-B', 'test', 'b.test.js')]]
        edges = [{'from': a, 'to': b, 'type': 'depends-on'} for a, b in [('REQ-1', 'SCR-A'), ('SCR-A', 'CODE-A'), ('CODE-A', 'TEST-A'), ('REQ-1', 'SCR-B'), ('SCR-B', 'CODE-B'), ('CODE-B', 'TEST-B')]]
        self.save('graph.json', {'version': 1, 'nodes': nodes, 'edges': edges})
        self.save('bindings.json', {'version': 1, 'authorities': {'intent': 'brief.md', 'implementation': 'app.js'}, 'dependency_edge_types': ['depends-on'], 'evidence': {'CODE-A': ['app.js']}})
        self.save('mapping.json', {'version': 1, 'tests': {'TEST-A': ['a.test.js'], 'TEST-B': ['b.test.js']}})
        code = ssot.main(['snapshot', '--brief', str(self.root / 'brief.md'), '--graph', str(self.root / 'graph.json'), '--bindings', str(self.root / 'bindings.json'), '--scope', 'local-only', '--out', str(self.root / 'manifest.json')])
        self.assertEqual(code, 0)

    def save(self, name, data):
        (self.root / name).write_text(json.dumps(data))

    def run_cli(self, out, *flags):
        return subprocess.run([sys.executable, str(PLUGIN / 'tools/affected_tests.py'), str(self.root / 'manifest.json'), '--project', str(self.root), '--mapping', str(self.root / 'mapping.json'), '--out', str(self.root / out), *flags], capture_output=True, text=True)

    def test_selective_execution_and_exclusion(self):
        (self.root / 'a.txt').write_text('changed')
        result = self.run_cli('result', '--run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'result/plan.json').read_text())
        self.assertEqual(plan['selected_tests'], ['TEST-A'])
        self.assertEqual(plan['excluded_tests'], ['TEST-B'])
        receipt = json.loads((self.root / 'result/receipt.json').read_text())
        self.assertEqual([x['file'] for x in receipt['tests']], ['a.test.js'])
        self.assertEqual(receipt['result'], 'passed')

    def test_missing_mapping_and_no_selected_tests_fail(self):
        self.save('mapping.json', {'version': 1, 'tests': {'TEST-A': ['a.test.js']}})
        self.assertNotEqual(self.run_cli('missing', '--run').returncode, 0)
        self.save('mapping.json', {'version': 1, 'tests': {'TEST-A': ['a.test.js'], 'TEST-B': ['b.test.js']}})
        self.assertNotEqual(self.run_cli('empty', '--run').returncode, 0)

    def test_detects_drift_and_skipped_tests(self):
        (self.root / 'a.test.js').write_text("const {test}=require('node:test'); test('drift',async()=>new Promise(r=>setTimeout(r, 700)));\n")
        ready = threading.Event()
        mutated = threading.Event()
        stop = threading.Event()

        def mutate_during_execution():
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not stop.wait(0.01):
                if (self.root / 'drift/node-tests').is_dir():
                    ready.set()
                    (self.root / 'a.txt').write_text('drift')
                    mutated.set()
                    return

        thread = threading.Thread(target=mutate_during_execution)
        thread.start()
        try:
            result = self.run_cli('drift', '--all', '--run')
        finally:
            stop.set()
            thread.join()
        self.assertTrue(ready.is_set(), 'Execution-ready directory was not observed')
        self.assertTrue(mutated.is_set(), 'Runtime input mutation did not complete')
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads((self.root / 'drift/receipt.json').read_text())['drift'])
        (self.root / 'a.test.js').write_text("const {test}=require('node:test'); test('passes',()=>{}); test.skip('skipped',()=>{});\n")
        self.assertNotEqual(self.run_cli('skip', '--all', '--run').returncode, 0)

    def test_missing_dependency_falls_back_and_symlink_rejected(self):
        data = json.loads((self.root / 'graph.json').read_text())
        data['edges'] = [e for e in data['edges'] if e['to'] != 'TEST-A']
        self.save('graph.json', data)
        result = self.run_cli('fallback')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'fallback/plan.json').read_text())['selected_tests'], ['TEST-A', 'TEST-B'])
        (self.root / 'escape.js').symlink_to(PLUGIN / 'tools/affected_tests.py')
        self.save('mapping.json', {'version': 1, 'tests': {'TEST-A': ['escape.js'], 'TEST-B': ['b.test.js']}})
        self.assertNotEqual(self.run_cli('escape', '--all', '--run').returncode, 0)

    def test_shared_files_are_not_reported_as_excluded(self):
        bindings = json.loads((self.root / 'bindings.json').read_text())
        bindings.setdefault('evidence', {})['TEST-B'] = ['a.test.js']
        self.save('bindings.json', bindings)
        # Establish a fresh baseline after adding the shared evidence declaration.
        (self.root / 'manifest.json').unlink()
        ssot.main(['snapshot', '--brief', str(self.root / 'brief.md'), '--graph', str(self.root / 'graph.json'), '--bindings', str(self.root / 'bindings.json'), '--scope', 'local-only', '--out', str(self.root / 'manifest.json')])
        self.save('mapping.json', {'version': 1, 'tests': {'TEST-A': ['a.test.js'], 'TEST-B': ['a.test.js', 'b.test.js']}})
        (self.root / 'a.txt').write_text('changed')
        result = self.run_cli('shared', '--run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'shared/plan.json').read_text())
        self.assertEqual(plan['shared_file_test_ids'], ['TEST-B'])
        self.assertEqual(plan['partial_file_test_ids'], ['TEST-B'])
        self.assertEqual(plan['excluded_tests'], [])

    def test_unbound_mapping_fails_and_existing_output_is_untouched(self):
        self.save('mapping.json', {'version': 1, 'tests': {'TEST-A': ['b.test.js'], 'TEST-B': ['b.test.js']}})
        self.assertNotEqual(self.run_cli('unbound', '--all', '--run').returncode, 0)
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'error.json').write_text('preserve')
        self.assertNotEqual(self.run_cli('existing').returncode, 0)
        self.assertEqual((existing / 'error.json').read_text(), 'preserve')

    def test_empty_and_outside_write_fail(self):
        (self.root / 'a.test.js').write_text('')
        self.assertNotEqual(self.run_cli('empty-file', '--all', '--run').returncode, 0)
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / 'outside.txt'
            (self.root / 'a.test.js').write_text("const {test}=require('node:test'); const fs=require('node:fs'); test('write',()=>fs.writeFileSync(" + json.dumps(str(target)) + ",'bad'));\n")
            self.assertNotEqual(self.run_cli('outside-write', '--all', '--run').returncode, 0)
            self.assertFalse(target.exists())

    def test_acceptance_checked_by_selects_only_its_test(self):
        data = json.loads((self.root / 'graph.json').read_text())
        (self.root / 'acceptance.txt').write_text('acceptance')
        for node in data['nodes']:
            if node['type'] == 'test':
                node['status'] = 'verified'
        data['nodes'].append({'id': 'ACC-A', 'type': 'acceptance', 'title': 'A', 'status': 'observed', 'source': 'acceptance.txt'})
        data['edges'].append({'from': 'ACC-A', 'to': 'TEST-A', 'type': 'checked by'})
        self.save('graph.json', data)
        (self.root / 'manifest.json').unlink()
        ssot.main(['snapshot', '--brief', str(self.root / 'brief.md'), '--graph', str(self.root / 'graph.json'), '--bindings', str(self.root / 'bindings.json'), '--scope', 'local-only', '--out', str(self.root / 'manifest.json')])
        (self.root / 'acceptance.txt').write_text('changed')
        result = self.run_cli('acceptance', '--run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'acceptance/plan.json').read_text())
        self.assertEqual(plan['selected_tests'], ['TEST-A'])
        self.assertEqual(plan['excluded_tests'], ['TEST-B'])
        self.assertEqual(plan['impacted']['TEST-A']['path_edges'][0]['meaning'], 'current-test-coverage')
        self.assertEqual(plan['impacted']['TEST-A']['path_edges'][0]['type'], 'checked by')
        data['edges'] = [edge for edge in data['edges'] if edge['type'] != 'checked by']
        self.save('graph.json', data)
        result = self.run_cli('uncovered')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads((self.root / 'uncovered/plan.json').read_text())['fallback'])

    def test_invalid_checked_by_rejected(self):
        data = json.loads((self.root / 'graph.json').read_text())
        data['edges'].append({'from': 'SCR-A', 'to': 'TEST-A', 'type': 'checked by'})
        self.save('graph.json', data)
        self.assertNotEqual(self.run_cli('invalid').returncode, 0)

    def test_evidence_only_binding_change_is_scoped(self):
        (self.root / 'new-proof.txt').write_text('new proof')
        bindings = json.loads((self.root / 'bindings.json').read_text())
        bindings.setdefault('evidence', {})['SCR-A'] = ['new-proof.txt']
        self.save('bindings.json', bindings)
        result = self.run_cli('scoped-binding')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'scoped-binding/plan.json').read_text())
        self.assertEqual(plan['bindings_change']['scope'], 'scoped-evidence')
        self.assertFalse(plan['global_change'])
        self.assertEqual(plan['selected_tests'], ['TEST-A'])
        self.assertEqual(plan['excluded_tests'], ['TEST-B'])

    def test_unpinned_old_binding_policy_is_broad(self):
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest.pop('bindings_policy_sha256', None)
        manifest['manifest_sha256'] = ssot.digest({k: v for k, v in manifest.items() if k != 'manifest_sha256'})
        self.save('manifest.json', manifest)
        (self.root / 'new-proof.txt').write_text('new proof')
        bindings = json.loads((self.root / 'bindings.json').read_text())
        bindings.setdefault('evidence', {})['SCR-A'] = ['new-proof.txt']
        self.save('bindings.json', bindings)
        result = self.run_cli('legacy-binding')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'legacy-binding/plan.json').read_text())
        self.assertTrue(plan['global_change'])
        self.assertEqual(plan['selected_tests'], ['TEST-A', 'TEST-B'])

    def test_policy_and_brief_changes_remain_broad(self):
        bindings = json.loads((self.root / 'bindings.json').read_text())
        bindings['dependency_edge_types'].append('checked by')
        self.save('bindings.json', bindings)
        result = self.run_cli('policy')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads((self.root / 'policy/plan.json').read_text())['global_change'])
        (self.root / 'brief.md').write_text('new brief')
        result = self.run_cli('brief')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads((self.root / 'brief/plan.json').read_text())['global_change'])

    def source_project(self, *, unresolved=False, complete=False):
        (self.root / 'a.js').write_text('module.exports = 1;\n')
        (self.root / 'b.js').write_text("module.exports = require('./a.js');\n" if not unresolved else 'require(name); module.exports = 1;\n')
        (self.root / 'a.test.js').write_text("const {test}=require('node:test'); const a=require('./a.js'); test('a',()=>{});\n")
        (self.root / 'b.test.js').write_text("const {test}=require('node:test'); const b=require('./b.js'); test('b',()=>{});\n")
        graph = json.loads((self.root / 'graph.json').read_text())
        for node in graph['nodes']:
            if node['id'] in ('CODE-A', 'CODE-B'):
                node['source'] = node['id'][-1].lower() + '.js'
        if complete:
            graph['edges'].append({'from': 'CODE-A', 'to': 'CODE-B', 'type': 'depends-on'})
        self.save('graph.json', graph)
        (self.root / 'manifest.json').unlink()
        ssot.main(['snapshot', '--brief', str(self.root / 'brief.md'), '--graph', str(self.root / 'graph.json'), '--bindings', str(self.root / 'bindings.json'), '--scope', 'local-only', '--out', str(self.root / 'manifest.json')])

    def test_proven_undeclared_source_dependency_prevents_exclusion(self):
        self.source_project()
        (self.root / 'a.js').write_text('module.exports = 2;\n')
        result = self.run_cli('omitted-import', '--run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'omitted-import/plan.json').read_text())
        self.assertTrue(plan['source_audit_fallback'])
        self.assertEqual(plan['selected_tests'], ['TEST-A', 'TEST-B'])
        self.assertEqual(plan['excluded_tests'], [])
        audit = json.loads((self.root / 'omitted-import/audit.json').read_text())
        self.assertEqual([(x['from'], x['to']) for x in audit['source_dependencies']['missing']], [('CODE-A', 'CODE-B')])
        self.assertEqual(audit['acceptance_claim'], 'not-established')
        self.assertNotIn('CODE-B', plan['impacted'])

    def test_unknown_source_analysis_broadens_useful_execution(self):
        self.source_project(unresolved=True)
        (self.root / 'a.js').write_text('module.exports = 2;\n')
        result = self.run_cli('unknown-import')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'unknown-import/plan.json').read_text())
        self.assertTrue(plan['source_audit_fallback'])
        self.assertEqual(plan['selected_tests'], ['TEST-A', 'TEST-B'])
        audit = json.loads((self.root / 'unknown-import/audit.json').read_text())
        self.assertTrue(audit['source_dependencies']['unknown'])

    def test_active_contradiction_blocks_acceptance_but_runs_tests(self):
        (self.root / 'brief.md').write_text('After retry, show the same card.\n')
        self.source_project(complete=True)
        (self.root / 'a.txt').write_text('changed')
        (self.root / 'active-spec.md').write_text('After retry, show the next pending card.\n')
        result = self.run_cli('contradiction', '--spec', 'active-spec.md', '--run')
        self.assertEqual(result.returncode, 1, result.stderr)
        plan = json.loads((self.root / 'contradiction/plan.json').read_text())
        self.assertEqual(plan['selected_tests'], ['TEST-A', 'TEST-B'])
        self.assertEqual(plan['acceptance_claim'], 'blocked-by-active-contradiction')
        receipt = json.loads((self.root / 'contradiction/receipt.json').read_text())
        self.assertEqual(receipt['test_result'], 'passed')
        self.assertEqual(receipt['result'], 'failed')
        self.assertEqual(len(receipt['tests']), 2)
        self.assertIn(str((self.root / 'active-spec.md').resolve()), receipt['inputs_before'])

    def test_complete_source_paths_keep_selective_scope(self):
        self.source_project(complete=True)
        (self.root / 'b.js').write_text("module.exports = require('./a.js') + 1;\n")
        result = self.run_cli('complete-import', '--run')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'complete-import/plan.json').read_text())
        self.assertFalse(plan['source_audit_fallback'])
        self.assertEqual(plan['selected_tests'], ['TEST-B'])
        self.assertEqual(plan['excluded_tests'], ['TEST-A'])

    def test_legacy_external_manifest_inputs_remain_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory)
            graph = json.loads((self.root / 'graph.json').read_text())
            for node in graph['nodes']:
                node['source'] = str((self.root / node['source']).resolve())
            (metadata / 'graph.json').write_text(json.dumps(graph))
            (metadata / 'brief.md').write_text('After retry, show the same card.\n')
            bindings = {'version': 1, 'authorities': {'intent': 'brief.md', 'implementation': str((self.root / 'app.js').resolve())}, 'dependency_edge_types': ['depends-on'], 'evidence': {'CODE-A': [str((self.root / 'app.js').resolve())]}}
            (metadata / 'bindings.json').write_text(json.dumps(bindings))
            (self.root / 'manifest.json').unlink()
            ssot.main(['snapshot', '--brief', str(metadata / 'brief.md'), '--graph', str(metadata / 'graph.json'), '--bindings', str(metadata / 'bindings.json'), '--scope', 'local-only', '--out', str(self.root / 'manifest.json')])
            (self.root / 'a.txt').write_text('changed')
            result = self.run_cli('external-metadata', '--run')
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads((self.root / 'external-metadata/plan.json').read_text())
            self.assertFalse(plan['source_audit_fallback'])
            receipt = json.loads((self.root / 'external-metadata/receipt.json').read_text())
            self.assertEqual(receipt['test_result'], 'passed')

    def test_unbound_importer_prevents_exclusion(self):
        (self.root / 'unbound.js').write_text("require('./app.js');\n")
        (self.root / 'a.txt').write_text('changed')
        result = self.run_cli('unbound-importer')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((self.root / 'unbound-importer/plan.json').read_text())
        self.assertTrue(plan['source_audit_fallback'])
        self.assertEqual(plan['excluded_tests'], [])


if __name__ == '__main__':
    unittest.main()
