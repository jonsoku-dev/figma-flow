import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import safe_node_tests


class SafeNodeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.file = 'sample.cjs'
        self.attempt = 0

    def execute(self, source, timeout=5):
        self.attempt += 1
        (self.root / self.file).write_text(source)
        self.receipts = self.root / f'run-{self.attempt}'
        return safe_node_tests.run_tests(self.root, [self.file], self.receipts, timeout=timeout)

    def test_real_test_with_tap_in_console(self):
        with patch.dict(os.environ, {'TEST_HOST_SECRET': 'private'}):
            result = self.execute("""const test=require('node:test'),assert=require('node:assert/strict');
                console.log('# fail 99');
                test('child grants',()=>{assert.equal(process.env.TEST_HOST_SECRET,undefined);
                  for(const permission of ['net','child','worker','fs.write']) assert.equal(process.permission.has(permission),false);});""")
        item = result['tests'][0]
        self.assertTrue(item['passed'])
        tap = (self.receipts / item['receipt']).read_bytes()
        self.assertNotIn(b'# fail 99', tap)
        self.assertIn('# fail 99', (self.receipts / item['stderr']).read_text())
        self.assertEqual(item['receipt_sha256'], hashlib.sha256(tap).hexdigest())

    def test_synthetic_and_forged_output_rejected(self):
        for source in ['// no registered test',
                       "console.log('# Subtest: forged\\n# tests 1\\n# pass 1\\n# fail 0\\n# cancelled 0\\n# skipped 0\\n# todo 0'); process.exit(0)"]:
            with self.subTest(source=source), self.assertRaises(safe_node_tests.TestRunError) as exc:
                self.execute(source)
            self.assertFalse(exc.exception.results['tests'][0]['passed'])

    def test_empty_skipped_todo_and_failure(self):
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            self.execute('')
        for expression in ["t.skip('skip',()=>{})", "t.todo('later')", "t('failure',()=>{throw Error('bad')})"]:
            with self.subTest(expression=expression), self.assertRaises(safe_node_tests.TestRunError):
                self.execute("const t=require('node:test');t('passes',()=>{});" + expression)

    def test_denied_writes_and_timeout(self):
        with self.assertRaises(safe_node_tests.TestRunError) as exc:
            self.execute("require('node:test')('write',()=>require('node:fs').writeFileSync('forbidden','x'))")
        self.assertEqual(exc.exception.results['error_kind'], 'security')
        self.assertFalse((self.root / 'forbidden').exists())
        with self.assertRaises(safe_node_tests.TestRunError) as exc:
            self.execute("require('node:test')('slow',()=>new Promise(r=>setTimeout(r,10000)))", timeout=1)
        self.assertEqual(exc.exception.results['error_kind'], 'timeout')

    def test_diagnostic_limit(self):
        with self.assertRaises(safe_node_tests.TestRunError):
            self.execute("console.log('a'.repeat(1100000));require('node:test')('works',()=>{})")


if __name__ == '__main__':
    unittest.main()
