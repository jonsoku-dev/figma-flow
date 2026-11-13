import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import api_priority
import native_api_probe
from review_api_coverage import observed_member_evidence


class ApiPriorityTest(unittest.TestCase):
    def test_inventory_keeps_every_exact_audit_key_and_real_graph_status(self):
        audit = json.loads(api_priority.AUDIT.read_text())
        graph = json.loads(api_priority.OBSERVATIONS.read_text())
        inventory = api_priority.build(audit, graph)
        self.assertEqual(len(inventory['rows']), len(audit['members']))
        self.assertEqual({row['api_member_id'] for row in inventory['rows']},
                         {row['key'] for row in audit['members']})
        observed = set(observed_member_evidence(audit, graph))
        self.assertEqual(inventory['source']['observed_graph_member_ids'], len(observed))
        self.assertEqual(inventory['source']['unobserved_members'], 1255)
        for row in inventory['rows']:
            self.assertTrue(row['priority_reasons'])
            self.assertIn('receiver_types', row)
            if row['api_member_id'] in observed:
                self.assertEqual(row['evidence_status'], 'observed-in-observation-graph')
                self.assertTrue(row['observation_evidence'])
        self.assertTrue(all(row['evidence_status'] != 'success' for row in inventory['rows']))
        text_case = next(row for row in inventory['rows'] if row['name'] == 'textCase')
        self.assertIn('TEXT', text_case['receiver_types'])
        css_method = next(row for row in inventory['rows'] if row['name'] == 'getCSSAsync')
        self.assertEqual(css_method['feasibility'], 'read-only-method')
        self.assertEqual(css_method['method_requirement'], 'read-only-static-allowlist')

    def test_feasible_queue_filters_unobserved_rows(self):
        inventory = api_priority.build()
        rows = api_priority.queue(inventory, limit=40, feasible_only=True)
        self.assertLessEqual(len(rows), 40)
        self.assertTrue(all(row['evidence_status'] not in ('observed', 'observed-in-observation-graph')
                            and row['feasibility'] in ('read-only-property', 'read-only-method', 'owned-disposable-method')
                            for row in rows))
        self.assertEqual(rows, sorted(rows, key=lambda row: (-row['priority_score'], row['api_member_id'])))
        all_unobserved = api_priority.queue(inventory, limit=10000)
        self.assertEqual(len(all_unobserved), 1255)
        self.assertTrue(any(row['feasibility'] in ('type-only', 'receiver-unresolved')
                            for row in all_unobserved))

    def test_group_and_vector_targets_are_exact_receiver_candidates(self):
        selection = {'schema': native_api_probe.SELECTION_SCHEMA,
            'fileKey': 'QN4Ght8gjyfLTFd7IFjur3', 'pageId': '71:16342', 'nodes': [
                {'semantic_id': 'mask-group', 'observed_node_id': '217:21692', 'observed_type': 'GROUP'},
                {'semantic_id': 'grid-frame', 'observed_node_id': '217:21672', 'observed_type': 'FRAME'}]}
        plan = native_api_probe.prepare(selection, file_key=selection['fileKey'], page_id=selection['pageId'])
        catalog = native_api_probe.load_catalog()
        audit = json.loads(native_api_probe.AUDIT_PATH.read_text())
        audit_rows = native_api_probe._audit_rows(catalog, audit)
        vector_fields = {row['property'] for row in native_api_probe.candidates_for_type(catalog, audit_rows, 'VECTOR')}
        self.assertTrue({'strokeAlign', 'strokeCap', 'strokeJoin', 'dashPattern',
                         'absoluteTransform', 'relativeTransform'} <= vector_fields)
        self.assertIn('GROUP', plan['nodeTypeInterfaces'])
        self.assertTrue(all(row['receiver_type'] in ('GROUP', 'FRAME')
                            for rows in plan['candidatesByType'].values() for row in rows))

    def test_unlinked_observed_member_node_does_not_count(self):
        audit = json.loads(api_priority.AUDIT.read_text())
        graph = json.loads(api_priority.OBSERVATIONS.read_text())
        before = api_priority.build(audit, graph)
        linked = set(observed_member_evidence(audit, graph))
        unlinked_row = next(row for row in audit['members'] if row['key'] not in linked
                            and row['release_status']['candidate']['status'] != 'observed')
        graph['nodes'].append({'id': unlinked_row['key'], 'type': 'figma', 'status': 'observed',
            'title': unlinked_row['owner'] + '.' + unlinked_row['name']})
        after = api_priority.build(audit, graph)
        self.assertEqual(after['source']['observed_graph_member_ids'], before['source']['observed_graph_member_ids'])
        row = next(item for item in after['rows'] if item['api_member_id'] == unlinked_row['key'])
        self.assertEqual(row['release_status'], 'unresolved')
        self.assertEqual(row['observation_evidence'], [])
        self.assertEqual(after['source']['unobserved_members'], 1255)

    def test_overlay_requires_linked_fresh_timestamped_success_receipt(self):
        audit = json.loads(api_priority.AUDIT.read_text())
        candidate = next(row for row in audit['members']
                         if row['release_status']['candidate']['status'] == 'unresolved')
        base = {'version': 1, 'id': 'priority-empty-base', 'nodes': [], 'edges': []}
        stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        evidence = {'id': 'OBS-new-batch', 'type': 'test', 'status': 'observed', 'source': 'native-readback',
                    'observed_at': stamp, 'receipt_sha256': 'a' * 64, 'getter_counts': {'success': 1}}
        member = {'id': candidate['key'], 'type': 'figma', 'status': 'observed',
                  'title': candidate['owner'] + '.' + candidate['name']}
        overlay = {'version': 1, 'id': 'priority-overlay', 'nodes': [evidence, member],
                   'edges': [{'from': evidence['id'], 'to': member['id'], 'type': 'observed member'}]}
        result = api_priority.build(audit, base, overlays=[overlay])
        row = next(item for item in result['rows'] if item['api_member_id'] == candidate['key'])
        self.assertEqual(row['evidence_status'], 'observed-in-observation-graph')
        self.assertEqual(row['observation_evidence'][0]['observed_at'], stamp)
        invalid = json.loads(json.dumps(overlay))
        invalid['nodes'][0].pop('observed_at')
        with self.assertRaisesRegex(ValueError, 'timestamped receipt'):
            api_priority.build(audit, base, overlays=[invalid])
        future = json.loads(json.dumps(overlay))
        future['nodes'][0]['observed_at'] = '2099-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'timestamped receipt'):
            api_priority.build(audit, base, overlays=[future])
        dangling = {'version': 1, 'id': 'bad-shape', 'nodes': [],
                    'edges': [{'from': 'missing', 'to': 'member:bad', 'type': 'observed member'}]}
        with self.assertRaisesRegex(ValueError, 'edge'):
            api_priority.build(audit, dangling)
        duplicate = {'version': 1, 'id': 'duplicate-node', 'nodes': [
            {'id': 'same', 'type': 'test'}, {'id': 'same', 'type': 'figma'}], 'edges': []}
        with self.assertRaisesRegex(ValueError, 'Duplicate observation node'):
            api_priority.build(audit, duplicate)


if __name__ == '__main__':
    unittest.main()
