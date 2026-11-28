import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import graph_governance as gate


class ContractConfigTests(unittest.TestCase):
    def test_named_contract_uses_private_config_and_preserves_tap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = root / 'tests'
            tests.mkdir()
            parent = root / 'parent-config'
            parent.mkdir(mode=0o700)
            trace = root / 'child.json'
            script = tests / 'contract.cjs'
            with patch.dict(os.environ, XDG_CONFIG_HOME=str(parent)):
                for expected in ('passed', 'incomplete'):
                    script.write_text("const fs = require('node:fs'); require('node:test')('named case', () => {"
                                      "const p = process.env.XDG_CONFIG_HOME;"
                                      f"fs.writeFileSync({json.dumps(str(trace))}, JSON.stringify([p, fs.statSync(p).mode & 0o777]));"
                                      + ("throw Error('synthetic failure');" if expected == 'incomplete' else "")
                                      + "});")
                    proof = gate.contract_proof(root, {'tests/contract.cjs': ['named case']})
                    self.assertEqual(proof['status'], expected)
                    child, mode = json.loads(trace.read_bytes())
                    self.assertNotEqual(Path(child), parent, 'named Node contract must isolate child XDG')
                    self.assertEqual(mode, 0o700)
                    self.assertFalse(Path(child).exists())
                    self.assertEqual(list(parent.iterdir()), [])


class PanelGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = gate.read_json(ROOT / gate.POLICY)
        cls.graph = gate.bind_graph(gate.read_json(ROOT / gate.GRAPH), cls.policy)
        cls.observed = gate.observe(ROOT, cls.graph, cls.policy)

    def structure(self, graph, observed):
        return gate.structure(graph, self.policy['panelBoundaries'], observed)

    def test_runtime_agreement_separates_bindings_and_usage(self):
        bindings, findings = self.structure(self.graph, self.observed)
        self.assertTrue(bindings)
        self.assertTrue(all(row['status'] == 'bound' for row in bindings))
        self.assertTrue(any(row['status'] == 'agrees' and row['rule'] == 'declared-relationship' and
                            row['evidence'][0]['line'] > 0 for row in findings))
        self.assertTrue(all(row['status'] == 'agrees' for row in findings))
        self.assertTrue(any(row['status'] == 'used' for row in self.observed['usage']))
        self.assertEqual([], gate.usage_findings(self.graph, self.observed))

    def test_required_adapter_import_cannot_be_replaced_with_reexport_or_dynamic_import(self):
        observation = copy.deepcopy(self.observed)
        for edge in observation['edges']:
            if edge.get('specifier') == './reviewTransport.mjs':
                edge['mode'] = 'dynamic'
                edge['type'] = 'REEXPORTS'
        findings = self.structure(self.graph, observation)[1]
        self.assertTrue(any(row['status'] == 'missing' and row.get('target') == 'panel-review-view'
                            for row in findings))

    def test_forbidden_glob_unbound_module_and_unresolved_call_target(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'].extend([
            {'id': 'all-views', 'kind': 'implementation', 'paths': ['panel-ui/src/**/ReviewPanel.jsx'], 'status': 'active'},
            {'id': 'missing-view', 'kind': 'implementation', 'paths': ['panel-ui/src/missing.jsx'], 'status': 'active'},
            {'id': 'future-view', 'kind': 'implementation', 'paths': ['panel-ui/src/future.jsx'], 'status': 'planned'},
        ])
        graph['relations'].extend([
            {'from': 'all-views', 'to': 'panel-review-transport', 'type': 'IMPORTS', 'state': 'forbidden'},
            {'from': 'panel-review-transport', 'to': 'missing-view', 'type': 'CALLS', 'state': 'required'},
            {'from': 'future-view', 'to': 'panel-review-transport', 'type': 'IMPORTS', 'state': 'required'},
        ])
        findings = self.structure(graph, self.observed)[1]
        self.assertIn(('all-views', 'prohibited'), [(row.get('target'), row['status']) for row in findings])
        self.assertIn(('missing-view', 'unbound'), [(row.get('target'), row['status']) for row in findings])
        self.assertTrue(any(row['status'] == 'unknown' and row['rule'] == 'relation-target-resolution' for row in findings))
        self.assertFalse(any(row.get('target') == 'future-view' for row in findings))

    def test_new_unused_candidate_and_unknown_require_distinct_actions(self):
        observation = {
            'nodes': [{'path': 'a', 'sha256': 'a' * 64}, {'path': 'b', 'sha256': 'b' * 64},
                      {'path': 'external', 'sha256': 'e' * 64}],
            'usage': [{'path': 'a', 'status': 'unused-candidate'},
                      {'path': 'b', 'status': 'unknown'},
                      {'path': 'external', 'status': 'external',
                       'evidence': {'path': ['external'], 'modes': [], 'consumer': 'report.py'}}],
            'edges': [],
            'externalEvidence': [{'path': 'external', 'consumer': 'report.py', 'certainty': 'extracted'}],
        }
        rows = gate.usage_findings(self.graph, observation)
        self.assertEqual([('a', 'needs-review'), ('b', 'unknown')], [(row['path'], row['status']) for row in rows])
        graph = {**self.graph, 'dispositions': [
            {'path': 'a', 'sha256': 'a' * 64, 'reason': 'external documentation example',
             'approval': 'maintainer example', 'reviewCondition': 'when the source changes'}
        ]}
        self.assertEqual(['b'], [row['path'] for row in gate.usage_findings(graph, observation)])
        observation['nodes'][0]['sha256'] = 'c' * 64
        self.assertEqual(['unused-module', 'usage-evidence', 'stale-disposition'],
                         [row['rule'] for row in gate.usage_findings(graph, observation)])

    def test_an_import_without_use_does_not_satisfy_the_required_call(self):
        observation = copy.deepcopy(self.observed)
        observation['edges'] = [edge for edge in observation['edges'] if edge.get('targetSymbol') != 'postDraftReceipt']
        self.assertTrue(any(row['relation']['type'] == 'CALLS' and row['status'] == 'missing'
                            for row in self.structure(self.graph, observation)[1] if 'relation' in row))

    def test_usage_receipt_rejects_omitted_duplicate_and_unknown_results(self):
        cases = [
            [],
            [*self.observed['usage'], self.observed['usage'][0]],
            [{**row, 'status': 'indeterminate'} for row in self.observed['usage']],
            [{key: value for key, value in row.items() if key != 'evidence'} for row in self.observed['usage']],
            [{**row, 'evidence': {'path': [row['path']], 'modes': []}} for row in self.observed['usage']],
        ]
        for usage in cases:
            with self.subTest(count=len(usage)), self.assertRaises(ValueError):
                gate.usage_findings(self.graph, {**self.observed, 'usage': usage})

    def test_contract_case_cannot_move_to_a_different_file(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / 'original.cjs').write_text("require('node:test')('leftover check', () => {});")
            (root / 'other.cjs').write_text("require('node:test')('required proof', () => {});")
            report = gate.contract_proof(root, {'original.cjs': ['required proof'], 'other.cjs': ['required proof']})
            self.assertEqual('incomplete', report['status'])
            self.assertEqual(['required proof'], report['suites']['original.cjs']['missingCases'])
            self.assertEqual('passed', report['suites']['other.cjs']['status'])

    def test_guide_review_binds_real_text_and_declared_policy(self):
        self.assertEqual([], gate.doc_findings(ROOT, self.graph, self.policy))
        policy = copy.deepcopy(self.policy)
        policy['panelBoundaries']['blockedPackages'].append('fixture')
        findings = gate.doc_findings(ROOT, self.graph, policy)
        self.assertEqual('needs-review', findings[0]['status'])
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            guide = self.graph['guideReview']
            for name in ('path', 'receipt'):
                relative = guide[name]
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes((ROOT / relative).read_bytes())
            (root / 'panel-ui').mkdir()
            (root / 'panel-ui/package.json').write_bytes((ROOT / 'panel-ui/package.json').read_bytes())
            (root / guide['path']).write_text('Hypothetical unfinished edit')
            self.assertEqual('needs-review', gate.doc_findings(root, self.graph, self.policy)[0]['status'])

    def test_required_stages_and_tap_cannot_omit_or_skip_evidence(self):
        stages = {stage: {'status': 'passed', 'evidence': {'present': True}} for stage in gate.STAGES}
        self.assertEqual('passed', gate.aggregate(stages))
        for stage in gate.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual('incomplete', gate.aggregate(
                    {key: result for key, result in stages.items() if key != stage}))
                self.assertEqual('incomplete', gate.aggregate(
                    {**stages, stage: {'status': 'passed', 'evidence': {}}}))
        tap = '\n'.join(['# tests 1', '# pass 1', '# fail 0', '# skipped 0', '# cancelled 0', '# todo 0'])
        self.assertEqual('passed', gate.tap_proof(tap, 0)['status'])
        self.assertEqual('incomplete', gate.tap_proof(tap.replace('# skipped 0', '# skipped 1'), 0)['status'])
        self.assertEqual('incomplete', gate.tap_proof('no report', 0)['status'])
        self.assertEqual(['required case'], gate.tap_proof(tap, 0, ['required case'])['missingCases'])
        self.assertEqual('failed', gate.tap_proof(tap, 1)['status'])


if __name__ == '__main__':
    unittest.main()
