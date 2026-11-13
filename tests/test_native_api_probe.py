import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace
import graph_sync
import native_api_probe as probe

FILE_KEY = 'Qn4Ght8gjyfLTFd7IFjur3'
PAGE_ID = '71:16342'
SELECTION = {
    'schema': probe.SELECTION_SCHEMA,
    'fileKey': FILE_KEY,
    'pageId': PAGE_ID,
    'nodes': [
        {'semantic_id': 'demo-grid', 'observed_node_id': '217:21672', 'observed_type': 'FRAME'},
        {'semantic_id': 'motion-dot', 'observed_node_id': '217:21695', 'observed_type': 'ELLIPSE'},
        {'semantic_id': 'shape-union', 'observed_node_id': '217:21680', 'observed_type': 'BOOLEAN_OPERATION'},
        {'semantic_id': 'motion-section', 'observed_node_id': '217:21693', 'observed_type': 'SECTION'},
        {'semantic_id': 'booking-main', 'observed_node_id': '231:21703', 'observed_type': 'COMPONENT'},
        {'semantic_id': 'booking-preview', 'observed_node_id': '231:21705', 'observed_type': 'INSTANCE'},
        {'semantic_id': 'booking-label', 'observed_node_id': '231:21704', 'observed_type': 'TEXT'},
        {'semantic_id': 'demo-cell', 'observed_node_id': '217:21673', 'observed_type': 'RECTANGLE'},
        {'semantic_id': 'booking-family', 'observed_node_id': '71:16343', 'observed_type': 'COMPONENT_SET'},
    ],
}


class NativeApiProbeTest(unittest.TestCase):
    def test_audit_candidates_are_bounded_paged_and_receiver_specific(self):
        plans = [probe.prepare(SELECTION, file_key=FILE_KEY, page_id=PAGE_ID, candidate_offset=offset)
                 for offset in (0, 16, 32)]
        planned = [row['budget']['planned_getters'] for row in plans]
        self.assertTrue(all(count <= len(SELECTION['nodes']) * probe.MAX_CANDIDATES_PER_TYPE
                            for count in planned))
        self.assertEqual(sum(planned), sum(len(rows) for rows in plans[0]['eligibleByType'].values()))
        first = plans[0]
        all_rows = [row for rows in first['eligibleByType'].values() for row in rows]
        self.assertGreater(len(all_rows), 0)
        self.assertTrue(all(scores == sorted(scores, reverse=True) for scores in
                            [[row['priority_score'] for row in rows]
                             for rows in first['eligibleByType'].values()]))
        self.assertTrue(all(row['priority_score'] > 0 and row['priority_reasons']
                            and row['role_matches'] for row in all_rows))
        self.assertTrue(all(row['audit_status'] == 'unresolved'
                            and row['receiver_type'] in probe.SAFE_TYPES
                            for row in all_rows))
        self.assertTrue(all((probe.SAFE_FIELDS if row['access'] == 'property' else probe.SAFE_METHODS)
                            [row['property']][1] == row['value_kind'] for row in all_rows))
        self.assertEqual(first['fieldPolicySha256'], hashlib.sha256(
            json.dumps(first['fieldPolicy'], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        self.assertEqual(first['nodeTypeInterfaces']['COMPONENT_SET'], 'ComponentSetNode')
        catalog = probe.load_catalog()
        audit_rows = probe._audit_rows(catalog, json.loads(probe.AUDIT_PATH.read_text()))
        frame_fields = {row['property'] for row in probe.candidates_for_type(catalog, audit_rows, 'FRAME')}
        rectangle_fields = {row['property'] for row in probe.candidates_for_type(catalog, audit_rows, 'RECTANGLE')}
        text_fields = {row['property'] for row in probe.candidates_for_type(catalog, audit_rows, 'TEXT')}
        self.assertNotIn('topLeftRadius', frame_fields)
        self.assertIn('topLeftRadius', rectangle_fields)
        self.assertIn('maxLines', text_fields)
        self.assertEqual(set(),
                         {row['property'] for row in plans[0]['eligibleByType']['TEXT']
                          if row['access'] == 'method'})
        vector_fields = {row['property'] for row in probe.candidates_for_type(
            probe.load_catalog(), probe._audit_rows(probe.load_catalog(), json.loads(probe.AUDIT_PATH.read_text())), 'VECTOR')}
        self.assertTrue({'strokeAlign', 'strokeCap', 'strokeJoin', 'dashPattern',
                         'absoluteTransform', 'relativeTransform'} <= vector_fields)

    def test_explicit_recheck_uses_only_observed_exact_keys_on_admitted_receivers(self):
        audit = json.loads((ROOT / 'library/figma-api/audit/members.json').read_bytes())
        row = next(r for r in audit['members'] if r['owner'] == 'BaseNodeMixin' and r['name'] == 'getCSSAsync')
        selection = {**SELECTION, 'recheck_member_ids': [row['key']]}
        admitted, config = probe.normalize_selection(selection, file_key=FILE_KEY, page_id=PAGE_ID)
        self.assertEqual(admitted['recheck_member_ids'], [row['key']])
        self.assertEqual({item['api_member_id'] for group in config['candidatesByType'].values()
                          for item in group}, {row['key']})
        for invalid in ([row['key'], row['key']], ['member:' + '0' * 64], []):
            with self.assertRaises(ValueError):
                probe.prepare({**SELECTION, 'recheck_member_ids': invalid}, file_key=FILE_KEY, page_id=PAGE_ID)

    def test_prior_statuses_require_timestamp_and_matching_hashes(self):
        baseline = probe.prepare(SELECTION, file_key=FILE_KEY, page_id=PAGE_ID)
        catalog = probe.load_catalog()
        audit_rows = probe._audit_rows(catalog, json.loads(probe.AUDIT_PATH.read_text()))
        member = probe.candidates_for_type(catalog, audit_rows, 'FRAME')[0]
        receipt = {'schema': probe.READBACK_SCHEMA, 'fileKey': FILE_KEY, 'pageId': PAGE_ID,
            'observed_at': '2026-11-13T15:33:24.219Z', 'api_probe': {
                'schema': 'figma-flow-native-api-probe-v1', 'auditRelease': baseline['auditRelease'],
                'apiSource': baseline['apiSource'], 'auditSha256': baseline['auditSha256'],
                'fieldPolicySha256': baseline['fieldPolicySha256'],
                'selectionSha256': baseline['selectionSha256'],
                'observations': [{'semantic_id': 'demo-grid', 'observed_node_id': '217:21672',
                    'api_member_id': member['api_member_id'], 'status': 'success', 'value': 'discarded'}]}}
        next_batch = probe.prepare(SELECTION, file_key=FILE_KEY, page_id=PAGE_ID,
                                   candidate_offset=16, previous_readback=receipt)
        self.assertTrue(next_batch['previous']['comparable'])
        changed = json.loads(json.dumps(receipt))
        changed['api_probe']['fieldPolicySha256'] = '0' * 64
        incomparable = probe.prepare(SELECTION, file_key=FILE_KEY, page_id=PAGE_ID,
                                     previous_readback=changed)
        self.assertFalse(incomparable['previous']['comparable'])
        self.assertEqual(incomparable['previous']['statuses'], [])
        invalid = json.loads(json.dumps(receipt))
        invalid['observed_at'] = 'not-a-receipt-time'
        with self.assertRaisesRegex(ValueError, 'actual receipt timestamp'):
            probe.prepare(SELECTION, file_key=FILE_KEY, page_id=PAGE_ID, previous_readback=invalid)

    def test_candidate_names_cannot_come_from_selection_and_runtime_uses_one_policy(self):
        spoofed = json.loads(json.dumps(SELECTION))
        spoofed['candidatesByType'] = {'FRAME': [{'property': 'name'}]}
        with self.assertRaisesRegex(ValueError, 'selection-v1'):
            probe.prepare(spoofed, file_key=FILE_KEY, page_id=PAGE_ID)
        source = (ROOT / 'figma-bridge/native_api_probe.js').read_text()
        self.assertNotIn('NATIVE_API_PROBE_FIELDS', source)
        self.assertNotIn('NATIVE_API_PROBE_KINDS', source)
        self.assertIn('config.fieldPolicy?.[candidate?.property]', source)
        self.assertIn('fieldPolicy.allowed_receivers.includes(target.observed_type)', source)
        self.assertIn('candidate?.audit_status !== \'unresolved\'', source)
        self.assertIn('NATIVE_API_PROBE_METHODS[candidate.property]', source)
        self.assertNotIn('node[candidate.property](', source)

    def test_documented_read_methods_use_static_calls_and_safe_projection(self):
        plan = probe.prepare(SELECTION, file_key=FILE_KEY, page_id=PAGE_ID)
        catalog = probe.load_catalog()
        audit_rows = probe._audit_rows(catalog, json.loads(probe.AUDIT_PATH.read_text()))
        methods = {row['property'] for row in probe.candidates_for_type(catalog, audit_rows, 'TEXT')
                   if row['access'] == 'method'}
        self.assertEqual(methods, {'getCSSAsync', 'getRangeFontName', 'getRangeFontSize', 'getRangeFontWeight', 'getRangeFills'})
        method_rows = [row for row in probe.candidates_for_type(catalog, audit_rows, 'TEXT')
                       if row['access'] == 'method']
        plan['eligibleByType']['TEXT'].extend(method_rows)
        plan['candidatesByType']['TEXT'].extend(method_rows)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            config_path = Path(temporary) / 'config.json'
            config_path.write_text(json.dumps(plan))
            subprocess.run(['node', str(ROOT / 'tests/helpers/native_api_probe_methods.cjs'),
                            str(config_path), str(ROOT / 'figma-bridge/native_api_probe.js')], check=True)

    def test_workspace_admission_pins_selection_and_builds_public_read_only_task(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary).resolve()
            selection_path = root / 'selection.json'
            selection_path.write_text(json.dumps(SELECTION))
            args, options, pins = figma_workspace.arguments('discover', [
                '--file-key', FILE_KEY, '--page-id', PAGE_ID, '--api-probe', str(selection_path)])
            self.assertIn('--api-probe', options)
            self.assertIn('--api-probe', pins)

            direct = root / 'direct'
            graph_sync.discovery_bundle(FILE_KEY, PAGE_ID, [], direct, api_probe_path=str(selection_path))
            direct_manifest = json.loads((direct / 'manifest.json').read_text())
            direct_source = (direct / 'code.js').read_text()
            self.assertNotIn('enablePrivatePluginApi', direct_manifest)
            for excluded in ['page.findAll', 'readNativeSemantics', 'figma.variables', 'figma.getLocalTextStyles']:
                self.assertNotIn(excluded, direct_source)
            self.assertEqual(direct_source.count('figma.getNodeByIdAsync'), 1)
            subprocess.run(['node', '--check', str(direct / 'code.js')], check=True)
            self.assertIn("summary-read').hidden = !discovery || !!config.api_probe", (direct / 'ui.html').read_text())

            id_path = root / 'assigned-id.json'
            id_path.write_text(json.dumps({'id': '123456789'}))
            workspace = root / 'workspace'
            figma_workspace.init(workspace, id_path)
            admitted = figma_workspace.prepare(workspace, 'api-probe-0', 'Native API probe batch 0',
                'discover', ['--file-key', FILE_KEY, '--page-id', PAGE_ID, '--api-probe', str(selection_path)],
                infer_thread=False)
            task = next(row for row in figma_workspace.current(workspace)['tasks'] if row['key'] == 'api-probe-0')
            bundle = figma_workspace.task_artifacts(workspace, task)
            manifest = json.loads((bundle / 'manifest.json').read_text())
            self.assertEqual(manifest['id'], '123456789')
            self.assertNotIn('enablePrivatePluginApi', manifest)
            self.assertEqual(task['input_pins']['--api-probe'], pins['--api-probe'])
            self.assertEqual(admitted['key'], task['key'])


if __name__ == '__main__':
    unittest.main()
