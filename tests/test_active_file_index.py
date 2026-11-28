"""Exercise persisted multi-file queue state and admission at the public CLI boundary."""
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_figma_control as fixtures

control = fixtures.control
workspace = fixtures.workspace


class ActiveFileIndexTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ControlTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.directory = control.state_dir(self.fixture.root)
        self.now = time.time()
        self.mapping = {}

    def record(self, key, state, *, due=False, operation='read'):
        number = len(self.mapping) + 1
        oid = f'{number:032x}'
        request = dict(schema=control.SCHEMA, id=oid, key='discovery', file_key=key, page_id='12:1',
                       revision=self.fixture.prepared['revision'], state=state, operation=operation,
                       created_at=self.now - 100 + number,
                       deadline=self.now + (-1 if due else 3600))
        control.save(self.directory, request)
        self.mapping[key] = oid
        return oid

    def publish(self):
        control._write_active_map(self.directory, self.mapping, list(self.mapping.values())[-1])

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', control.__file__, *args], text=True,
                              capture_output=True, timeout=30)

    def test_existing_large_writer_output_survives_restart(self):
        for size in (22, 128):
            self.mapping.clear()
            for n in range(64):
                key = f'{n:0{size}x}'
                oid = self.record(key, 'pending' if n == 63 else 'ok')
            self.publish()
            self.assertGreater((self.directory/'active.json').stat().st_size, 4096)
            check = self.cli('status', '--workspace', str(self.fixture.root), '--file-key', key)
            self.assertEqual(check.returncode, 0, '64 persisted legal keys must survive CLI restart')
            status = json.loads(check.stdout)
            self.assertEqual(status['id'], oid)
            self.assertEqual([r['id'] for r in status['active_operations']], [oid])
            self.assertEqual(control._live_metrics_state(self.fixture.root)['active_operation_state'], 'pending')

    def test_live_slots_block_before_any_new_request_is_saved(self):
        self.fixture.start_server()
        for n in range(64):
            self.record(f'F{n:02}', 'claimed' if n % 2 else 'pending')
        self.publish()
        control.uncertainties(self.directory)
        before = self.fixture.snapshot()
        result = self.cli(*self.fixture.run_args('--no-wait'))
        self.assertEqual(result.returncode, 2, 'saturation must reject before saving the new request')
        self.assertEqual(result.stdout, '')
        self.assertIn('64', result.stderr)
        self.assertIn('status', result.stderr)
        self.assertEqual(self.fixture.snapshot(), before)
        with self.assertRaisesRegex(ValueError, 'already active'):
            self.fixture.enqueue(file_key='F00')

    def test_only_terminal_slot_is_reused_and_receipts_remain(self):
        for n in range(64):
            self.record(f'F{n:02}', 'ok' if n == 62 else 'pending')
        self.publish()
        old = self.mapping['F62']
        receipt = self.directory/'receipts'/(old+'.json')
        original = receipt.read_bytes()
        admitted = self.fixture.enqueue()
        latest, indexed = control._read_active_map(self.directory)
        self.assertEqual(latest, admitted['id'])
        self.assertEqual(indexed, {**{k:v for k,v in self.mapping.items() if k!='F62'},
                                   'fixturefile': admitted['id']})
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual(control.status(self.fixture.root, old)['state'], 'ok')

    def test_read_only_observers_agree_without_persisting_expiry(self):
        self.record('FileOne', 'ok')
        pending = self.record('FileTwo', 'pending')
        expired = self.record('FileThree', 'claimed', due=True, operation='apply')
        self.publish()
        before = self.fixture.snapshot()
        self.assertEqual([r['id'] for r in control._peek_active_operations(self.fixture.root)], [pending])
        self.assertEqual(control._live_metrics_state(self.fixture.root)['active_operation_state'], 'pending',
                         'health must report the live file after a terminal entry')
        self.assertEqual(self.fixture.snapshot(), before)
        status = control.status(self.fixture.root, file_key='FileThree')
        self.assertEqual(status['state'], 'uncertain')
        self.assertIn(expired, [r['id'] for r in status['uncertain_operations']])
        self.assertTrue((self.directory/'receipts'/(expired+'.json')).is_file())

    def test_pressure_preserves_uncertain_write_protection(self):
        for n in range(64):
            self.record(f'F{n:02}', 'claimed', due=n == 17, operation='apply')
        self.publish()
        old = self.mapping['F17']
        self.fixture.enqueue()
        self.assertNotIn('F17', control._read_active_map(self.directory)[1])
        self.assertEqual(control.status(self.fixture.root, old)['state'], 'uncertain')
        self.assertIn(old, control.uncertainties_for_file(self.directory, 'F17'))
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.fixture.enqueue(file_key='F17', operation='apply')

    def test_legacy_pointer_retains_old_file_on_admission(self):
        oid = self.record('legacyFile', 'pending')
        workspace.atomic(self.directory/'active.json', workspace.encode({'id':oid}))
        before = self.fixture.snapshot()
        self.assertEqual([r['id'] for r in control._peek_active_operations(self.fixture.root)], [oid])
        self.assertEqual(self.fixture.snapshot(), before)
        new = self.fixture.enqueue()
        self.assertEqual(control._read_active_map(self.directory),
                         (new['id'], {'legacyFile':oid,'fixturefile':new['id']}))


if __name__ == '__main__':
    unittest.main()
