import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_alignment
import relay_view


class FigmaAlignmentTests(unittest.TestCase):
    def test_geometry_options_are_bounded_and_exclude_text(self):
        self.assertEqual(relay_view.validate_options('selection-info', {
            'geometry_node_ids': ['1:2', '1:3']}), {'include_text': False, 'geometry_node_ids': ['1:2', '1:3']})
        with self.assertRaisesRegex(ValueError, 'cannot include text'):
            relay_view.validate_options('selection-info', {
                'include_text': True, 'geometry_node_ids': ['1:2']})
        for ids in ([], ['1:2', '1:2'], ['bad'], ['1:2'] * 21):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, 'unique exact'):
                relay_view.validate_options('selection-info', {'geometry_node_ids': ids})

    def test_explicit_absolute_edges_and_missing_statuses(self):
        receipt = {'schema': 'figma-flow-viewer-result-v1', 'operation': 'selection-info',
                   'fileKey': 'file', 'pageId': '1:1',
                   'geometry': {'coordinate_space': 'page-absolute-axis-aligned', 'nodes': [
                       {'id': '1:2', 'status': 'observed', 'rotation': 0,
                        'absoluteBoundingBox': {'x': 100, 'y': 50, 'width': 40, 'height': 20}},
                       {'id': '1:3', 'status': 'observed', 'rotation': 0,
                        'absoluteBoundingBox': {'x': 104, 'y': 75, 'width': 20, 'height': 10}},
                       {'id': '1:6', 'status': 'observed', 'rotation': 0,
                        'absoluteBoundingBox': {'x': 148, 'y': 20, 'width': 10, 'height': 10}},
                       {'id': '1:4', 'status': 'unmeasurable', 'absoluteBoundingBox': None},
                       {'id': '1:5', 'status': 'missing'}]}}
        result = figma_alignment.compare(receipt, 'file', '1:1', '1:2', ['1:3', '1:6', '1:4', '1:5'],
                                         'x', 'start', 'start', 4)
        self.assertEqual([row['status'] for row in result['results']], ['aligned', 'drift', 'unmeasurable_target', 'missing_target'])
        self.assertEqual(result['results'][0]['delta'], 4)
        self.assertEqual(result['results'][0]['deviation'], 4)
        self.assertEqual(result['results'][1]['delta'], 48)
        self.assertEqual(result['results'][1]['expected_offset'], 0)
        gap = figma_alignment.compare(receipt, 'file', '1:1', '1:2', ['1:6'],
                                      'x', 'end', 'start', 0.25, 8)
        self.assertEqual(gap['status'], 'aligned')
        self.assertEqual(gap['results'][0]['delta'], 8)
        self.assertEqual(gap['results'][0]['deviation'], 0)
        self.assertEqual(result['results'][0]['anchor_id'], '1:2')
        self.assertEqual(result['results'][0]['target_id'], '1:3')

    def test_legacy_discovery_fixture_uses_absolute_bounding_boxes(self):
        path = ROOT / '.figma-flow/booking-remediation/native/final-full.json'
        if not path.exists():
            self.skipTest('known local discovery fixture is unavailable')
        receipt = figma_alignment.load_receipt(path)
        result = figma_alignment.compare(receipt, 'QN4Ght8gjyfLTFd7IFjur3', '71:16342',
                                         '231:21703', ['231:21705', '231:21707'],
                                         'x', 'start', 'start', 0)
        self.assertEqual([row['delta'] for row in result['results']], [0, 0])
        self.assertEqual([row['status'] for row in result['results']], ['aligned_axis_aligned_bounds'] * 2)
        self.assertIsNone(result['results'][0]['rotated'])
        self.assertEqual(len(result['receipt_sha256']), 64)
        self.assertNotIn('receipt_path', result)

    def test_cli_rejects_wrong_scope(self):
        receipt = {'schema': 'figma-flow-viewer-result-v1', 'operation': 'selection-info',
                   'fileKey': 'file', 'pageId': '1:1', 'geometry': {'nodes': []}}
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'receipt.json'
            path.write_text(json.dumps(receipt))
            result = subprocess.run([sys.executable, str(ROOT / 'tools/figma_alignment.py'), 'check',
                                     '--receipt', str(path), '--file-key', 'wrong', '--page-id', '1:1',
                                     '--anchor-id', '1:2', '--target-id', '1:3', '--axis', 'x',
                                     '--anchor-edge', 'start', '--target-edge', 'start', '--tolerance', '0'],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('does not match', result.stderr)

    def test_import_rejects_duplicate_ids_and_boolean_coordinates(self):
        receipt = {'schema': 'figma-flow-viewer-result-v1', 'operation': 'selection-info',
                   'fileKey': 'file', 'pageId': '1:1', 'geometry': {'nodes': [
                       {'id': '1:2', 'status': 'observed', 'absoluteBoundingBox':
                        {'x': 1, 'y': 2, 'width': 10, 'height': 10}},
                       {'id': '1:2', 'status': 'observed', 'absoluteBoundingBox':
                        {'x': 1, 'y': 2, 'width': 10, 'height': 10}}]}}
        with self.assertRaisesRegex(ValueError, 'duplicate node IDs'):
            figma_alignment.compare(receipt, 'file', '1:1', '1:2', ['1:3'], 'x', 'start', 'start', 0)
        receipt['geometry']['nodes'] = [
            {'id': '1:2', 'status': 'observed', 'absoluteBoundingBox':
             {'x': True, 'y': 2, 'width': 10, 'height': 10}},
            {'id': '1:3', 'status': 'observed', 'absoluteBoundingBox':
             {'x': 1, 'y': 2, 'width': 10, 'height': 10}}]
        report = figma_alignment.compare(receipt, 'file', '1:1', '1:2', ['1:3'], 'x', 'start', 'start', 0)
        self.assertEqual(report['status'], 'unverified')
        self.assertEqual(report['results'][0]['status'], 'unmeasurable_anchor')


if __name__ == '__main__':
    unittest.main()
