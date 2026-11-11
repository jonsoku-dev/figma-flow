"""Publication safety tests; synthetic claims do not imply live Figma proof."""
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_control as control
import figma_workspace as workspace
import test_figma_workspace as fixtures


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class PublishGuardTests(unittest.TestCase):
    setUp = fixtures.WorkspaceTests.setUp
    prepare = fixtures.WorkspaceTests.prepare

    def claim(self):
        prepared = self.prepare()
        control.enable(self.path, 49198)
        request = control.enqueue(self.path, 'read-test', 'read', 'fixturefile', '12:1', prepared['revision'], 120)
        claim = control.poll(self.path, {'session_id': 'synthetic-session', 'file_key': 'fixturefile', 'page_id': '12:1'})['operation']
        self.assertEqual(claim['id'], request['id'])
        return request

    def snapshot(self):
        return {str(path.relative_to(self.path)): path.read_bytes() if path.is_file() else None
                for path in self.path.rglob('*')}

    def refresh(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
            result = workspace.main(['refresh', '--workspace', str(self.path)])
        return result, error.getvalue()

    def test_claim_blocks_prepare_refresh_and_init_publication_without_writes(self):
        self.claim()
        before = self.snapshot()
        message = 'wait for current native run to finish; inspect status'
        with self.assertRaisesRegex(ValueError, message):
            self.prepare(key='independent-task')
        self.assertEqual(self.snapshot(), before)
        code, error = self.refresh()
        self.assertEqual(code, 2)
        self.assertIn(message, error)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(ValueError, message):
            workspace.init(self.path, self.identity, chat_port=49199)
        self.assertEqual(self.snapshot(), before)

    def test_claim_blocks_after_deadline_until_status_marks_uncertain(self):
        request = self.claim()
        before = self.snapshot()
        with patch.object(control.time, 'time', return_value=request['deadline'] + 1):
            self.assertEqual(self.refresh()[0], 2)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(control.status(self.path)['state'], 'uncertain')
        self.assertEqual(self.refresh()[0], 0)
        self.assertFalse(self.prepare(key='recovery-read')['unchanged'])

    def test_terminal_and_pending_history_allow_publication(self):
        request = self.claim()
        path = self.path / '.control' / 'requests' / (request['id'] + '.json')
        for state in ('ok', 'error', 'uncertain', 'expired', 'pending'):
            with self.subTest(state=state):
                value = workspace.read(path, private=True, limit=32768)
                value['state'] = state
                workspace.atomic(path, workspace.encode(value))
                self.assertEqual(self.refresh()[0], 0)
                self.assertFalse(self.prepare(key='task-' + state)['unchanged'])

    def test_claim_allows_unchanged_prepare_and_init_without_publication(self):
        self.claim()
        before = self.snapshot()
        self.assertTrue(self.prepare()['unchanged'])
        workspace.init(self.path, self.identity)
        self.assertEqual(self.snapshot(), before)

    def test_claim_is_checked_even_without_current_request_pointer(self):
        self.claim()
        (self.path / '.control' / 'active.json').unlink()
        before = self.snapshot()
        self.assertEqual(self.refresh()[0], 2)
        self.assertEqual(self.snapshot(), before)

    def test_no_control_workspace_needs_no_configuration(self):
        self.assertEqual(self.refresh()[0], 0)
        self.assertFalse(self.prepare()['unchanged'])
        self.assertFalse((self.path / '.control').exists())
        self.assertFalse((self.path / 'control.json').exists())


if __name__ == '__main__':
    unittest.main()
