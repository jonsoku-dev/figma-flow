"""Tests for fixed native value paths and privacy-safe evidence normalization."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'skills/figma-flow/scripts'))
import api_priority
import native_value_paths as values
from graph import validate_graph
from review_api_coverage import observed_member_evidence


class NativeValuePathTests(unittest.TestCase):
    def test_catalog_uses_exact_pinned_types_and_fixed_routes(self):
        catalog = values.load_api_catalog()
        policy = json.loads(values.POLICY.read_bytes())
        values._validate_catalog(catalog, policy)
        graph, report = values.build_graph()
        errors, _warnings = validate_graph(graph)
        self.assertEqual(errors, [])
        self.assertEqual(report['declaration_ref'], catalog['source']['ref'])
        self.assertEqual(report['candidate_members'], len(report['candidates']))
        self.assertGreater(report['union_branches'], 0)
        self.assertIn('GRID', next(branch for route in policy['routes'] if route['id'] == 'layout-grid-rows-columns'
                                   for union in route['unions'].values() for branch in union['branches']
                                   if branch['tag'] == 'GRID')['tag'])

    def test_catalog_rejects_an_unpinned_member_and_unknown_union_tag(self):
        catalog = values.load_api_catalog()
        policy = json.loads(values.POLICY.read_bytes())
        invalid_member = deepcopy(policy)
        invalid_member['routes'][0]['owners']['Reaction'].append('arbitraryGetter')
        with self.assertRaisesRegex(ValueError, 'pinned PropertySignature'):
            values._validate_catalog(catalog, invalid_member)
        invalid_tag = deepcopy(policy)
        invalid_tag['routes'][0]['unions']['Transition']['branches'][0]['tag'] = 'ARBITRARY'
        with self.assertRaisesRegex(ValueError, 'does not declare discriminant'):
            values._validate_catalog(catalog, invalid_tag)

    def test_prior_success_exclusion_does_not_count_the_same_member_twice(self):
        _graph, report = values.build_graph()
        candidate = next(row for row in report['candidates'] if row['owner'] == 'NoiseEffectBase' and row['name'] == 'density')
        receipt = {'schema': 'figma-flow-service-inspection-receipt-v1', 'graph_sha256': 'a' * 64,
                   'observed_at': '2026-11-14T00:00:00Z', 'specimen_id': 'local-only', 'reused': True,
                   'observations': [{'id': candidate['member_id'], 'status': 'success', 'shape': 'number'}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'service.json'
            path.write_text(json.dumps(receipt))
            _next_graph, updated = values.build_graph(receipts=[path])
        self.assertEqual(updated['candidate_members'], report['candidate_members'] - 1)
        self.assertIn(candidate['member_id'], {row['member_id'] for row in updated['already_observed']})

    def _synthetic_receipt(self, plan, policy, member):
        unions = {}
        for route in policy['routes']:
            for name, spec in route['unions'].items():
                unions[name] = {'observed': []}
        scenarios = [{'route': route['id'], 'status': 'created', 'assignments_attempted': 1,
                      'assignments_succeeded': 1, 'assignments_failed': 0, 'readback_objects': 1}
                     for route in policy['routes']]
        return {'schema': 'figma-flow-native-value-observation-v2',
                'graph_sha256': plan['graph_sha256'], 'policy_sha256': plan['policy_sha256'],
                'api_source_ref': plan['api_source_ref'], 'observed_at': datetime.now(timezone.utc).isoformat(),
                'getter_counts': {'success': 1, 'unavailable': 0, 'runtime_error': 0, 'unsupported': 0},
                'scenarios': scenarios,
                'observations': [{'member_id': member['member_id'], 'owner': member['owner'],
                    'name': member['name'], 'route': member['route'], 'status': 'success',
                    'value': {'value': 0.25}}],
                'union_coverage': unions}

    def test_normalized_observation_graph_survives_default_overlay_join(self):
        graph, report = values.build_graph()
        policy = json.loads(values.POLICY.read_bytes())
        member = next(row for row in report['candidates'] if row['owner'] == 'NoiseEffectBase' and row['name'] == 'density')
        plan = {'graph_sha256': report['graph_sha256'], 'policy_sha256': report['policy_sha256'],
                'api_source_ref': report['declaration_ref'], 'candidate_members': report['candidates']}
        receipt = self._synthetic_receipt(plan, policy, member)
        with tempfile.TemporaryDirectory() as folder:
            receipt_path = Path(folder) / 'receipt.json'
            plan_path = Path(folder) / 'plan.json'
            receipt_path.write_text(json.dumps(receipt))
            plan_path.write_text(json.dumps(plan))
            overlay, result = values.build_observation_graph(receipt_path, plan_path)
        audit = json.loads(values.API_AUDIT.read_bytes())
        member_evidence = observed_member_evidence(audit, overlay, require_receipts=True)
        self.assertIn(member['member_id'], member_evidence)
        combined = api_priority.build(overlays=[overlay], include_public_overlays=True)
        row = next(item for item in combined['rows'] if item['api_member_id'] == member['member_id'])
        self.assertEqual(row['evidence_status'], 'observed-in-observation-graph')
        self.assertEqual(result['successful_fields'], 1)
        self.assertEqual(result['new_audited_members'], 1)

    def test_normalizer_rejects_user_identifiers_and_raw_text(self):
        graph, report = values.build_graph()
        policy = json.loads(values.POLICY.read_bytes())
        member = next(row for row in report['candidates'] if row['owner'] == 'NoiseEffectBase' and row['name'] == 'density')
        plan = {'graph_sha256': report['graph_sha256'], 'policy_sha256': report['policy_sha256'],
                'api_source_ref': report['declaration_ref'], 'candidate_members': report['candidates']}
        receipt = self._synthetic_receipt(plan, policy, member)
        with tempfile.TemporaryDirectory() as folder:
            receipt_path = Path(folder) / 'receipt.json'
            plan_path = Path(folder) / 'plan.json'
            plan_path.write_text(json.dumps(plan))
            receipt['fileKey'] = 'private-key'
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'unapproved fields'):
                values.build_observation_graph(receipt_path, plan_path)
            receipt.pop('fileKey')
            receipt['observations'][0]['value'] = 'PRIVATE USER TEXT'
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'enum|identifiers|text'):
                values.build_observation_graph(receipt_path, plan_path)

    def test_public_live_value_overlay_matches_the_pinned_audit(self):
        overlay_path = ROOT / 'specs/design-inspection/value-observations.json'
        overlay = json.loads(overlay_path.read_bytes())
        audit = json.loads(values.API_AUDIT.read_bytes())
        evidence = observed_member_evidence(audit, overlay, require_receipts=True)
        priority = api_priority.build(include_public_overlays=True)
        observed = {row['api_member_id'] for row in priority['rows']
                    if row['evidence_status'] in ('observed', 'observed-in-observation-graph')}
        self.assertTrue(evidence)
        self.assertTrue(set(evidence) <= observed)
        self.assertEqual(overlay['nodes'][0]['source'], '../../docs/design-runtime-verification.md')

    def test_private_runner_reuses_exact_scope_without_printing_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.figma-flow') as folder:
            root = Path(folder)
            scope = {'schema': 'figma-flow-native-value-path-plan-v1', 'file': 'private-file',
                     'page': '88:1', 'plugin_id': '123456'}
            scope_path = root / 'scope.json'
            scope_path.write_text(json.dumps(scope))
            audit = json.loads(values.API_AUDIT.read_bytes())
            plugin_member = next(row['key'] for row in audit['members']
                                 if row['owner'] == 'VariablesAPI' and row['name'] == 'getLocalVariableCollectionsAsync')
            service = {'schema': 'figma-flow-service-inspection-receipt-v1', 'graph_sha256': 'c' * 64,
                       'observations': [{'id': plugin_member, 'status': 'success', 'shape': 'array'}]}
            service_path = root / 'service.json'
            service_path.write_text(json.dumps(service))
            destination = root / 'private-bundle'
            result = values.prepare(destination, service_receipt=service_path, scope_plan=scope_path)
            plan = json.loads((destination / 'plan.json').read_bytes())
            self.assertEqual((plan['file'], plan['page'], plan['plugin_id']), ('private-file', '88:1', '123456'))
            self.assertEqual(plan['capabilities']['getLocalVariableCollectionsAsync'], True)
            self.assertEqual(Path(result['output']), destination)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
            self.assertEqual((destination / 'code.js').stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads((destination / 'manifest.json').read_bytes())['networkAccess']['allowedDomains'], ['none'])


if __name__ == '__main__':
    unittest.main()
