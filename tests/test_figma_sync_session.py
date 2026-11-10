from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import unittest
import subprocess
import sys
from unittest.mock import patch

import test_apply_figma_change as workflow
from figma_sync_session import SyncSession
import apply_figma_change


class SessionTest(unittest.TestCase):
    setUp = workflow.ChangeWorkflowTest.setUp
    changes = workflow.ChangeWorkflowTest.changes

    def session(self, **kwargs):
        return SyncSession(self.app, self.resolved, 'main:page', self.root / 'state', **kwargs)

    def snapshot(self, after=False):
        return json.loads((self.after if after else self.before).read_text())

    def test_baseline_apply_restart_noop_and_chain(self):
        first = self.session().sync(self.snapshot())
        self.assertEqual(first['status'], 'baseline')
        result = self.session().sync(self.snapshot(True))
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(result['changed_tokens'], ['palette.blue'])
        self.assertIn('app/tokens.css', result['files'])
        inventory = sorted(str(path) for path in (self.root / 'state').rglob('*'))
        for _ in range(3):
            self.assertEqual(self.session().sync(self.snapshot(True))['status'], 'unchanged')
        self.assertEqual(inventory, sorted(str(path) for path in (self.root / 'state').rglob('*')))
        self.assertEqual(self.session().sync(self.snapshot())['status'], 'applied')
        self.assertEqual(os.stat(result['report']).st_mode & 0o077, 0)

    def test_first_snapshot_must_match_local_baseline(self):
        before = (self.app / 'design.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale baseline'):
            self.session().sync(self.snapshot(True))
        self.assertEqual(before, (self.app / 'design.json').read_bytes())
        self.assertFalse((self.root / 'state' / 'pending.json').exists())
        self.assertEqual(self.session().sync(self.snapshot())['status'], 'baseline')

    def test_prior_bootstrap_exact_bytes_and_direct_apply(self):
        self.changes('legacy', True)
        result = self.session(prior_sync=self.root / 'legacy').sync(self.snapshot())
        self.assertEqual(result['status'], 'applied')
        self.assertEqual((self.root / 'state/bootstrap.json').read_bytes(), self.after.read_bytes())
        self.assertEqual(self.session().sync(self.snapshot())['status'], 'unchanged')

    def test_stale_css_rejected_even_on_noop(self):
        self.session().sync(self.snapshot())
        css = self.app / 'app/tokens.css'
        css.write_text(css.read_text() + '/* user */')
        with self.assertRaisesRegex(ValueError, 'generated CSS'):
            self.session().sync(self.snapshot())
        self.assertTrue(css.read_text().endswith('/* user */'))

    def test_identity_and_chain_tampering_rejected(self):
        baseline = self.session().sync(self.snapshot())
        with self.assertRaisesRegex(ValueError, 'Session project'):
            SyncSession(self.app, self.resolved, 'other', self.root/'state').sync(self.snapshot())
        (Path(baseline['report'])/'token-plan/assets/tokens.css').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'corrupt prior-sync'):
            self.session().sync(self.snapshot())

    def test_interruption_after_apply_before_pointer_recovers_once(self):
        self.session().sync(self.snapshot())
        with patch.object(SyncSession, '_finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.session().sync(self.snapshot(True))
        with patch.object(apply_figma_change, 'run', side_effect=AssertionError('must not reapply')):
            self.assertEqual(self.session().sync(self.snapshot(True))['status'], 'applied')
        self.assertEqual(self.session().sync(self.snapshot(True))['status'], 'unchanged')

    def test_missing_receipt_after_project_writes_recovers(self):
        self.session().sync(self.snapshot())
        with patch.object(SyncSession, '_finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.session().sync(self.snapshot(True))
        pending = json.loads((self.root/'state/pending.json').read_text())
        (Path(pending['slot'])/'applied/result.json').unlink()
        self.assertEqual(self.session().sync(self.snapshot(True))['status'], 'applied')

    def test_partial_writes_never_revert_local_work(self):
        self.session().sync(self.snapshot())
        with patch.object(SyncSession, '_finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.session().sync(self.snapshot(True))
        css = self.app/'app/tokens.css'
        css.write_text('my concurrent work')
        with self.assertRaisesRegex(ValueError, 'partial writes or local edits'):
            self.session().sync(self.snapshot())
        self.assertEqual(css.read_text(), 'my concurrent work')

    def test_concurrent_same_click_serializes(self):
        self.session().sync(self.snapshot())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.session().sync(self.snapshot(True)), range(2)))
        self.assertEqual(sorted(result['status'] for result in results), ['applied', 'unchanged'])

    def test_stale_native_timestamp_rejected_and_noop_bounded(self):
        first = self.snapshot()
        first['exported_at'] = '2026-11-08T10:00:00.000Z'
        self.session().sync(first)
        newer = self.snapshot(True)
        newer['exported_at'] = '2026-11-08T10:01:00.000Z'
        self.session().sync(newer)
        with self.assertRaisesRegex(ValueError, 'older'):
            self.session().sync(first)
        count = len(list((self.root/'state').rglob('*')))
        for minute in range(2, 5):
            newer['exported_at'] = f'2026-11-08T10:0{minute}:00.000Z'
            self.assertEqual(self.session().sync(newer)['status'], 'unchanged')
        self.assertEqual(count, len(list((self.root/'state').rglob('*'))))

    def test_bad_bootstrap_and_unsafe_state_rejected(self):
        self.changes('legacy', True)
        self.after.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.session(prior_sync=self.root/'legacy').sync(self.snapshot())
        with self.assertRaisesRegex(ValueError, 'outside'):
            SyncSession(self.app, self.resolved, 'main:page', self.app/'state')

    def test_process_exit_before_project_write_retries(self):
        self.session().sync(self.snapshot())
        script = """
import os, sys
sys.path.insert(0, sys.argv[1])
import apply_figma_change
from figma_sync_session import SyncSession
import json
apply_figma_change.code.apply_changes = lambda *args: os._exit(17)
SyncSession(sys.argv[2], sys.argv[3], 'main:page', sys.argv[4]).sync(json.load(open(sys.argv[5])))
"""
        result = subprocess.run([sys.executable, '-c', script, str(workflow.ROOT/'tools'),
                                 str(self.app), str(self.resolved), str(self.root/'state'), str(self.after)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertTrue((self.root/'state/pending.json').exists())
        self.assertEqual(self.session().sync(self.snapshot(True))['status'], 'applied')
        self.assertFalse((self.root/'state/pending.json').exists())

    def test_corrupt_journal_slot_cannot_touch_outside_directory(self):
        self.session().sync(self.snapshot())
        outside = self.root/'run-outside'
        outside.mkdir(mode=0o700)
        marker = outside/'keep.txt'
        marker.write_text('keep')
        session = self.session()
        journal = self.root/'state/pending.json'
        link = self.root/'state/run-link'
        link.symlink_to(outside, target_is_directory=True)
        nested = self.root/'state/run-parent'
        nested.mkdir(mode=0o700)
        child = nested/'run-child'
        child.mkdir(mode=0o700)
        for slot in (outside, link, child, self.root/'state'):
            with self.subTest(slot=str(slot)):
                journal.write_text(json.dumps({'identity': session._identity(), 'slot': str(slot),
                                               'before': session._hashes(), 'baseline': False}))
                with self.assertRaisesRegex(ValueError, 'owned private run'):
                    session.sync(self.snapshot())
                self.assertEqual(marker.read_text(), 'keep')
                self.assertEqual(outside.stat().st_mode & 0o777, 0o700)
                self.assertTrue(journal.exists())

    def test_recovery_preserves_existing_receipt_input_pins(self):
        self.session().sync(self.snapshot())
        with patch.object(SyncSession, '_finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.session().sync(self.snapshot(True))
        pending = json.loads((self.root/'state/pending.json').read_text())
        receipt_path = Path(pending['slot'])/'applied/result.json'
        original = json.loads(receipt_path.read_text())
        self.assertIn('inputs', original)
        self.session().sync(self.snapshot(True))
        self.assertEqual(json.loads(receipt_path.read_text()), original)

    def test_recovery_rejects_existing_receipt_pin_drift(self):
        self.session().sync(self.snapshot())
        with patch.object(SyncSession, '_finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.session().sync(self.snapshot(True))
        pending = json.loads((self.root/'state/pending.json').read_text())
        receipt_path = Path(pending['slot'])/'applied/result.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['inputs']['resolved'] = '0' * 64
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'receipt pins differ'):
            self.session().sync(self.snapshot(True))
        self.assertEqual(json.loads(receipt_path.read_text()), receipt)

    def test_last_comparison_fresh_state_has_no_baseline(self):
        self.assertIsNone(self.session().last_comparison())
        self.assertFalse((self.root/'state/state.json').exists())
        self.assertFalse(list((self.root/'state').glob('run-*')))

    def test_last_comparison_restores_baseline_and_applied_after_restart(self):
        baseline = self.session().sync(self.snapshot())
        self.assertEqual(self.session().last_comparison(), (self.snapshot(), baseline))
        applied = self.session().sync(self.snapshot(True))
        contents = {str(path): path.read_bytes() for path in self.app.rglob('*') if path.is_file()}
        inventory = sorted(str(path) for path in (self.root/'state').rglob('*'))
        with patch.object(apply_figma_change, 'run', side_effect=AssertionError('read must not apply')):
            self.assertEqual(self.session().last_comparison(), (self.snapshot(True), applied))
        self.assertEqual(contents, {str(path): path.read_bytes() for path in self.app.rglob('*') if path.is_file()})
        self.assertEqual(inventory, sorted(str(path) for path in (self.root/'state').rglob('*')))

    def test_last_comparison_recovers_interrupted_committed_snapshot(self):
        self.session().sync(self.snapshot())
        with patch.object(SyncSession, '_finish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.session().sync(self.snapshot(True))
        with patch.object(apply_figma_change, 'run', side_effect=AssertionError('read must not apply')):
            snapshot, result = self.session().last_comparison()
        self.assertEqual(snapshot, self.snapshot(True))
        self.assertEqual(result['status'], 'applied')
        self.assertFalse((self.root/'state/pending.json').exists())

    def test_last_comparison_omits_external_bootstrap_until_paired_commit(self):
        self.changes('legacy', True)
        self.assertEqual(self.session(prior_sync=self.root/'legacy').sync(self.snapshot(True))['status'], 'unchanged')
        self.assertIsNone(self.session().last_comparison())
        result = self.session().sync(self.snapshot())
        self.assertEqual(self.session().last_comparison(), (self.snapshot(), result))

    def test_last_comparison_rejects_identity_and_css_drift(self):
        self.session().sync(self.snapshot())
        with self.assertRaisesRegex(ValueError, 'Session project'):
            SyncSession(self.app, self.resolved, 'other', self.root/'state').last_comparison()
        css = self.app/'app/tokens.css'
        css.write_text(css.read_text() + '/* user */')
        with self.assertRaisesRegex(ValueError, 'generated CSS'):
            self.session().last_comparison()
