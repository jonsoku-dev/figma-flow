import copy
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'tools'))
import policy_impact


class PolicyImpactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = json.loads((ROOT / 'apps/little-hands/design/graph.json').read_text())
        self.before = self.root / 'before.json'
        self.current = self.root / 'current.json'
        previous = copy.deepcopy(self.source)
        removed = {'TEST-006-cutoff', 'code-cancellation-policy'}
        previous['nodes'] = [node for node in previous['nodes'] if node['id'] not in removed]
        previous['edges'] = [edge for edge in previous['edges'] if edge['from'] not in removed and edge['to'] not in removed and edge['type'] != 'requires review']
        next(node for node in previous['nodes'] if node['id'] == 'REQ-006')['detail'] = '에이전트 제품 해석. 현재 구현 사실과 실제 인수 결과를 구분한다.'
        for edge in previous['edges']:
            edge.pop('rationale', None)
        self.before.write_text(json.dumps(previous), encoding='utf-8')
        changed = copy.deepcopy(self.source)
        next(node for node in changed['nodes'] if node['id'] == 'REQ-006')['detail'] += ' 정책 변경 예시.'
        self.current.write_text(json.dumps(changed), encoding='utf-8')

    def test_reports_explicit_policy_screens_and_linked_test_only(self):
        report = policy_impact.build_report(self.before, self.current, 'REQ-006',
            source_root=ROOT / 'apps/little-hands/design')
        self.assertEqual({item['id'] for item in report['directScreens']}, {
            'screen-confirmed', 'screen-waitlisted', 'screen-cancelconfirm', 'screen-cancelled'})
        self.assertEqual({item['id'] for item in report['tests']}, {'TEST-006', 'TEST-006-cutoff'})
        self.assertTrue({'cancel', 'confirm-cancel', 'reschedule'} <= {item['webAction'] for item in report['actions']})
        self.assertNotIn('logout', {item['webAction'] for item in report['actions']})
        self.assertNotIn('screen-login', {item['id'] for item in report['directScreens']})
        self.assertEqual(report['reviewDecision'], 'pending')
        self.assertIn('정책 변경 전', policy_impact.render_html(report))
        evidence = {item['id']: item for item in report['businessEvidence']}
        self.assertTrue(evidence['code-cancellation-policy']['symbolFound'])
        self.assertEqual(len(evidence['code-cancellation-policy']['symbolSha256']), 64)
        self.assertEqual(len(report['businessEvidenceSha256']), 64)
        self.assertFalse(report['strictLocal']['passed'])
        self.assertTrue(report['strictLocal']['failures'])
        self.assertEqual(evidence['TEST-006-cutoff']['freshness'], 'source-present-unverified')
        transitions = {item['id']: item for item in report['freshnessChanges']}
        self.assertEqual(transitions['TEST-006-cutoff']['before'], 'untracked')
        self.assertEqual(transitions['TEST-006-cutoff']['current'], 'source-present-unverified')
        self.assertIn('REQ-006', {item['id'] for item in report['graphFreshness']})
        self.assertEqual(report['graphDiff']['policyNodeChanges'][0]['id'], 'REQ-006')
        self.assertTrue(any(edge['to'] == 'action-state-cancelconfirm-cancel-confirm'
                            for edge in report['graphDiff']['policyEdgeChanges']['added']))

    def test_missing_reason_blocks_screen_inclusion(self):
        graph = copy.deepcopy(self.source)
        edge = next(e for e in graph['edges'] if e.get('from') == 'REQ-006' and e.get('to') == 'screen-confirmed')
        edge.pop('rationale')
        self.current.write_text(json.dumps(graph), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'missing rationale'):
            policy_impact.build_report(self.before, self.current, 'REQ-006',
                source_root=ROOT / 'apps/little-hands/design')
