"""Real CLI historical revival and rejection atomicity; no live Figma claim."""
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
class HistoricalRestore(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'workspace'
        self.assigned = self.root / 'assigned.json'
        self.assigned.write_text('{"id":"12345"}')
        workspace.init(self.path, self.assigned)
        self.page = self.root / 'index.html'
        self.record = self.root / 'record.json'
        self.source_a = '<h1>Source A</h1>'
        self.source_b = '<h1>Source B</h1>'
        self.write_source(self.source_a)
        self.admit('source', *self.input_args())
        self.original = self.task('source')
        self.original_bytes = self.bundle_bytes(self.original)
        self.edge = {'task_key': 'source', 'revision': self.original['revision'],
                     'relation': 'uses-output', 'artifact': 'code.js',
                     'artifact_sha256': self.original['artifact_hashes']['code.js']}
        edge_path = self.root / 'dependencies.json'
        edge_path.write_text(json.dumps([self.edge]))
        self.admit('consumer', '--depends-on', str(edge_path))
        self.write_source(self.source_b)
        self.admit('source', *self.input_args(), '--replace-expected', self.original['revision'])
        self.newer = self.task('source')
        self.assertNotEqual(self.newer['revision'], self.original['revision'])
        retained = workspace.current(self.path)['dependency_artifacts']
        self.assertEqual(retained, [self.original], 'fixture must retain authenticated exact A output')

    def write_source(self, text):
        self.page.write_text(text)
        self.record.write_text(json.dumps({'schema': input_effect.RESULT_SCHEMA,
            'channels': {'html': {'assets': []}},
            'sources': [{'path': 'index.html', 'sha256': input_effect.digest(self.page.read_bytes())}]}))

    def input_args(self):
        return ('--input-record', str(self.record), '--input-root', str(self.root))

    def cli_prepare(self, key, *extra):
        return subprocess.run([sys.executable, str(ROOT / 'tools/figma_workspace.py'),
            'prepare', '--workspace', str(self.path), '--key', key, '--title', key,
            '--kind', 'discover', *extra, '--', '--file-key', 'fixturefile', '--page-id', '12:1'],
            cwd=ROOT, capture_output=True, text=True)

    def admit(self, key, *extra):
        result = self.cli_prepare(key, *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def task(self, key):
        return next(row for row in workspace.current(self.path)['tasks'] if row['key'] == key)

    def bundle_bytes(self, row):
        bundle = workspace.task_artifacts(self.path, row)
        return {name: (bundle / name).read_bytes()
                for name in ('code.js', 'ui.html', 'manifest.json', 'input-record.json')}

    def snapshot(self):
        return {str(path.relative_to(self.path)): path.read_bytes()
                for path in self.path.rglob('*') if path.is_file()}

    def task_directories(self):
        return {path.name for path in (self.path / '.tasks').iterdir() if path.is_dir()}

    def restore(self):
        self.write_source(self.source_a)
        return self.cli_prepare('source', *self.input_args(),
                                '--replace-expected', self.newer['revision'])

    def assert_exact_revival(self):
        restored = self.task('source')
        self.assertEqual(restored, self.original,
                         'revival must reuse the authenticated retained row, not regenerate its identity')
        self.assertEqual(self.bundle_bytes(restored), self.original_bytes)
        self.assertEqual(self.task('consumer')['depends_on'], [self.edge])
        self.assertEqual(workspace.task_input_freshness(self.path, restored), {
            'taskKey': 'source', 'revision': self.original['revision'], 'status': 'current', 'changed': []})
        self.assertEqual(restored['input_root'], str(self.root.resolve()))

    def test_retained_revision_revives_exact_authenticated_bundle(self):
        before_directories = self.task_directories()
        result = self.restore()
        self.assertEqual(result.returncode, 0,
            'current source A must revive its retained output despite randomized generated session: ' + result.stderr)
        self.assertEqual(json.loads(result.stdout)['revision'], self.original['revision'])
        self.assert_exact_revival()
        self.assertEqual(self.task_directories(), before_directories,
                         'historical revival must not publish a duplicate task artifact directory')

    def test_rejected_revival_leaves_no_unreferenced_task_or_catalogue_change(self):
        before = self.snapshot()
        before_directories = self.task_directories()
        result = self.restore()
        if result.returncode == 0:
            self.assert_exact_revival()
            self.assertEqual(self.task_directories(), before_directories)
        else:
            after = self.snapshot()
            self.assertEqual(self.task('source'), self.newer, 'rejection must preserve active B')
            self.assertEqual({name: after.get(name) for name in before}, before,
                             'rejected publication changed existing catalogue or artifact bytes')
            self.assertEqual(self.task_directories(), before_directories,
                'rejected replacement left an unreferenced .tasks directory: ' + result.stderr)
            self.assertEqual(after, before, 'rejected metadata publication must leave the workspace unchanged')

    def test_historical_revival_keeps_current_input_and_expected_revision_guards(self):
        # A record is not current while B is on disk, even though A output is retained.
        self.write_source(self.source_a)
        self.page.write_text(self.source_b)
        before = self.snapshot()
        result = self.cli_prepare('source', *self.input_args(), '--replace-expected', self.newer['revision'])
        self.assertNotEqual(result.returncode, 0, 'retained output must not bypass source freshness')
        self.assertEqual(self.snapshot(), before)
        self.write_source(self.source_a)
        for extra in [('--replace-expected', self.newer['revision']),
                      ('--input-record', str(self.record), '--replace-expected', self.newer['revision']),
                      self.input_args() + ('--replace-expected', self.original['revision'])]:
            with self.subTest(arguments=extra):
                before = self.snapshot()
                result = self.cli_prepare('source', *extra)
                self.assertNotEqual(result.returncode, 0, 'revival must retain record/root and current replacement guard')
                self.assertEqual(self.snapshot(), before)

    def test_unreferenced_old_bundle_is_not_historical_authority(self):
        self.path = self.root / 'unreferenced-workspace'
        workspace.init(self.path, self.assigned)
        self.write_source(self.source_a)
        self.admit('source', *self.input_args())
        orphan_a = self.task('source')
        self.write_source(self.source_b)
        self.admit('source', *self.input_args(), '--replace-expected', orphan_a['revision'])
        active_b = self.task('source')
        history, _ = workspace.dependency_history(self.path)
        self.assertNotIn(orphan_a, history)
        self.assertTrue((self.path / orphan_a['artifact_dir']).is_dir())
        self.write_source(self.source_a)
        self.admit('source', *self.input_args(), '--replace-expected', active_b['revision'])
        regenerated_a = self.task('source')
        self.assertEqual(regenerated_a['revision'], orphan_a['revision'])
        self.assertNotEqual(regenerated_a['artifact_dir'], orphan_a['artifact_dir'],
            'an unpublished/unretained .tasks bundle must not become revival authority by filesystem scan')


if __name__ == '__main__':
    unittest.main()
