"""Run the public CLI against a private workspace and its real loopback server."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_figma_control as fixtures


class RunRejectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ControlTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.start_server()

    def run_cli(self, *extra):
        return subprocess.run(
            [sys.executable, '-B', fixtures.control.__file__, *self.fixture.run_args('--no-wait', *extra)],
            capture_output=True, text=True, timeout=30,
        )

    def reject(self, *extra):
        before = self.fixture.snapshot()
        result = self.run_cli(*extra)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.fixture.snapshot(), before)
        for private in (str(self.fixture.root), fixtures.control.config(self.fixture.root)['token'],
                        'fixturefile', self.fixture.prepared['revision']):
            self.assertNotIn(private, result.stderr)
        return result.stderr

    def test_busy_file_offers_scoped_status(self):
        first = self.run_cli()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)['state'], 'pending')
        self.assertEqual(first.stderr, '')
        message = self.reject()
        self.assertIn('already active', message, 'busy file must identify the active operation')
        self.assertIn('status --workspace', message)
        self.assertIn('--file-key', message)

    def test_stale_write_offers_revision_lookup(self):
        message = self.reject('--operation', 'apply', '--expected-revision', 'f' * 64)
        self.assertIn('figma_workspace.py list', message)
        self.assertIn('--expected-revision', message)

    def test_uncertain_write_requires_readback(self):
        self.fixture.uncertain_mutation()
        message = self.reject('--operation', 'apply', '--key', 'mutation',
                              '--expected-revision', self.fixture.mutating['revision'])
        self.assertIn('uncertain', message)
        self.assertIn('read', message)
        self.assertIn('status --workspace', message)

    def test_unclassified_private_error_stays_redacted(self):
        path = self.fixture.root / 'active-private-path-marker'
        result = self.run_cli('--workspace', str(path))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn(str(path), result.stderr)
        self.assertIn('rejected', result.stderr)


if __name__ == '__main__':
    unittest.main()
