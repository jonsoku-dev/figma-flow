"""RD-06 partial evidence at real consumer entrypoints, using synthetic API hosts."""
import json
from pathlib import Path
import subprocess
import unittest

import test_graph_sync as graph_fixture
import test_figma_control as control_fixture

control, workspace = control_fixture.control, control_fixture.workspace


class PartialConsumers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads(subprocess.check_output(
            ['node', str(Path(__file__).with_suffix('.cjs')), '--summary'], text=True))
        assert cls.summary['coverage']['fields'] == ['width', 'height']
        assert cls.summary['coverage']['complete'] is False

    def test_normal_import_apply_rejects_summary_without_touching_canonical_files(self):
        fixture = graph_fixture.GraphSyncTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.web.write_text('existing web projection\n')
        pairing_path = fixture.directory / 'pairing.json'
        pairing_path.write_text(json.dumps(fixture.pairing))
        before = {path: path.read_bytes() for path in (fixture.path, fixture.web, pairing_path)}
        output = fixture.directory / 'partial-import'
        from graph_sync import import_values
        # Summary deliberately omits variables: the normal importer must fail before publication.
        with self.assertRaisesRegex(KeyError, 'variables'):
            import_values(fixture.path, fixture.pairing, self.summary, fixture.web, output, True)
        self.assertFalse(output.exists())
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(json.loads(pairing_path.read_text()), fixture.pairing)

    def test_partial_recovery_stays_uncertain_until_fresh_same_scope_full_read(self):
        fixture = control_fixture.ControlTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = fixture.uncertain_mutation()
        receipt = fixture.root / '.control/receipts' / (original['id'] + '.json')
        receipt_before = receipt.read_bytes()
        sources = {path: path.read_bytes() for path in
                   (fixture.directory / 'graph.json', fixture.directory / 'native.json')}
        request = fixture.enqueue()
        row = next(row for row in workspace.current(fixture.root)['tasks'] if row['key'] == 'discovery')
        self.assertFalse(control.recovery_read(request, row, self.summary, original))
        fixture.result(fixture.claim(), readback_json=json.dumps(self.summary))
        self.assertEqual(control.status(fixture.root)['uncertain_operations'][0]['id'], original['id'])
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            fixture.mutation()
        self.assertEqual(receipt.read_bytes(), receipt_before)
        self.assertEqual({path: path.read_bytes() for path in sources}, sources)

        fresh = fixture.enqueue()
        full = fixture.discovery_readback()
        self.assertTrue(control.recovery_read(fresh, row, json.loads(full), original))
        fixture.result(fixture.claim(), readback_json=full)
        self.assertEqual(control.status(fixture.root)['reconciles'], [original['id']])
        self.assertEqual(control.status(fixture.root)['uncertain_operations'], [])
        self.assertEqual(receipt.read_bytes(), receipt_before)
        self.assertEqual({path: path.read_bytes() for path in sources}, sources)


if __name__ == '__main__':
    unittest.main(defaultTest='PartialConsumers')
