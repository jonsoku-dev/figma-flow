"""Real CLI admission and read-only source freshness; no live Figma claim."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace
import input_effect


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class AssetAdmission(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'workspace'
        assigned = self.root / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.path, assigned)
        self.page = self.root / 'index.html'
        self.page.write_text('<h1>First source</h1>')
        self.record_path = self.root / 'record.json'
        self.write_record()

    def write_record(self):
        record = {'schema': input_effect.RESULT_SCHEMA,
            'channels': {'html': {'assets': []}},
            'sources': [{'path': 'index.html', 'sha256': input_effect.digest(self.page.read_bytes())}]}
        self.record_path.write_text(json.dumps(record))
        return record

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'tools/figma_workspace.py'), *args],
            capture_output=True, text=True, cwd=ROOT)

    def prepare(self, key, *extra):
        result = self.cli('prepare', '--workspace', str(self.path), '--key', key,
            '--title', key, '--kind', 'discover', *extra,
            '--', '--file-key', 'fixturefile', '--page-id', '12:1')
        self.assertEqual(result.returncode, 0,
            'real CLI must admit bounded explicit input records and dependencies: ' + result.stderr)
        return json.loads(result.stdout)

    def snapshot(self):
        return {str(path.relative_to(self.path)): path.read_bytes()
                for path in self.path.rglob('*') if path.is_file()}

    def test_cli_admits_record_root_edges_and_preserves_them_through_replay(self):
        first = self.prepare('source', '--input-record', str(self.record_path), '--input-root', str(self.root))
        helper = getattr(workspace, 'task_input_freshness', None)
        self.assertTrue(callable(helper), 'workspace must expose read-only input freshness')
        source = workspace.current(self.path)['tasks'][0]
        expected = {'taskKey': 'source', 'revision': first['revision'], 'status': 'current', 'changed': []}
        before = self.snapshot()
        self.assertEqual(helper(self.path, source), expected)
        self.assertEqual(before, self.snapshot())
        public = workspace.public_task_metadata(source)
        self.assertNotIn(str(self.root), json.dumps(public))
        edge = {'task_key': 'source', 'revision': first['revision'], 'relation': 'uses-output',
                'artifact': 'code.js', 'artifact_sha256': source['artifact_hashes']['code.js']}
        edge_path = self.root / 'dependencies.json'
        edge_path.write_text(json.dumps([edge]))
        self.prepare('consumer', '--depends-on', str(edge_path))
        replay = self.cli('replay', '--workspace', str(self.path), '--key', 'source',
            '--expected-revision', first['revision'])
        self.assertEqual(replay.returncode, 0, replay.stderr)
        source = workspace.current(self.path)['tasks'][0]
        self.assertIn('input_record', source, 'replay must retain exact record admission')
        self.assertEqual(helper(self.path, source)['status'], 'current')
        self.page.write_text('<h1>Changed source</h1>')
        before = self.snapshot()
        stale = helper(self.path, source)
        self.assertEqual(stale, {**expected, 'revision': source['revision'], 'status': 'stale', 'changed': ['index.html']})
        self.assertEqual(before, self.snapshot())
        replay = self.cli('replay', '--workspace', str(self.path), '--key', 'source',
            '--expected-revision', source['revision'])
        self.assertNotEqual(replay.returncode, 0, 'stale source must block replay')
        self.assertEqual(before, self.snapshot())
        self.write_record()
        newer = self.prepare('source', '--input-record', str(self.record_path), '--input-root', str(self.root),
            '--replace-expected', source['revision'])
        self.assertNotEqual(newer['revision'], source['revision'])
        tasks = workspace.current(self.path)['tasks']
        self.assertEqual(tasks[1]['depends_on'], [edge])
        self.assertEqual(helper(self.path, tasks[0])['status'], 'current')

    def test_api_legacy_record_without_explicit_root_is_unverified(self):
        workspace.prepare(self.path, 'legacy', 'legacy', 'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'],
            input_record=self.write_record(), infer_thread=False)
        helper = getattr(workspace, 'task_input_freshness', None)
        self.assertTrue(callable(helper), 'workspace must expose read-only input freshness')
        task = workspace.current(self.path)['tasks'][0]
        self.assertEqual(helper(self.path, task), {'taskKey': 'legacy',
            'revision': task['revision'], 'status': 'unverified', 'changed': []})


if __name__ == '__main__':
    unittest.main()
