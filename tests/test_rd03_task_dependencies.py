"""Optional task dependencies are normalized before the signed catalogue.

Synthetic workspace tasks are not a live Figma panel observation.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace


def tasks():
    return [
        {'key': 'review', 'revision': 'a' * 64, 'project': 'desk', 'artifact_hashes': {'code.js': 'b' * 64, 'ui.html': 'c' * 64, 'manifest.json': 'd' * 64}},
        {'key': 'import-task', 'revision': 'e' * 64, 'project': 'desk', 'artifact_hashes': {'code.js': 'f' * 64, 'ui.html': '1' * 64, 'manifest.json': '2' * 64}},
        {'key': 'notes', 'revision': '3' * 64, 'project': 'desk', 'artifact_hashes': {'code.js': '4' * 64, 'ui.html': '5' * 64, 'manifest.json': '6' * 64}},
    ]


def edge(**changes):
    value = {'task_key': 'review', 'revision': 'a' * 64, 'relation': 'uses-output', 'artifact': 'code.js', 'artifact_sha256': 'b' * 64}
    value.update(changes)
    return value


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class TaskDependencyTests(unittest.TestCase):
    def test_declared_dependencies_normalize_without_cycles_or_inferred_edges(self):
        normalize = getattr(workspace, 'normalize_task_dependencies', None)
        self.assertTrue(callable(normalize), 'declared task dependencies must be normalized before publish')
        source = Path(workspace.__file__).read_text(encoding='utf-8')
        self.assertLess(source.index('def publish('), source.index('normalize_task_dependencies(catalogue'))

        normalized = normalize(tasks(), {'import-task': [edge()]})
        by_key = {task['key']: task for task in normalized}
        self.assertEqual(by_key['import-task']['depends_on'], [edge()])
        self.assertNotIn('depends_on', by_key['review'])
        self.assertNotIn('depends_on', by_key['notes'])
        self.assertFalse(any(item['task_key'] == 'notes' for task in normalized for item in task.get('depends_on', [])))

        for changes, message in (
            ({'task_key': 'missing'}, 'missing target'),
            ({'task_key': 'import-task', 'revision': 'e' * 64}, 'self edge'),
            ({'revision': '0' * 64}, 'dependency revision is not current'),
            ({'relation': 'causes'}, 'unsupported dependency relation'),
            ({'artifact': '../code.js'}, 'unregistered artifact'),
            ({'artifact_sha256': '9' * 64}, 'artifact hash mismatch'),
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, message):
                    normalize(tasks(), {'import-task': [edge(**changes)]})
        with self.assertRaisesRegex(ValueError, 'duplicate edge'):
            normalize(tasks(), {'import-task': [edge(), edge()]})
        cycled = tasks()
        cycled[0]['depends_on'] = [{'task_key': 'import-task', 'revision': 'e' * 64, 'relation': 'uses-output', 'artifact': 'code.js', 'artifact_sha256': 'f' * 64}]
        with self.assertRaisesRegex(ValueError, 'cycle'):
            normalize(cycled, {'import-task': [edge()]})

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'workspace'
        assigned = Path(temporary.name) / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(root, assigned)
        review = workspace.prepare(root, 'review', 'Review', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'], project='desk')
        stored = next(task for task in workspace.current(root)['tasks'] if task['key'] == 'review')
        dependency = {'task_key': 'review', 'revision': review['revision'], 'relation': 'uses-output', 'artifact': 'code.js', 'artifact_sha256': stored['artifact_hashes']['code.js']}
        prepared = workspace.prepare(root, 'import-task', 'Import', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'], project='desk', depends_on=[dependency])
        catalogue = workspace.current(root)
        imported = next(task for task in catalogue['tasks'] if task['key'] == 'import-task')
        self.assertEqual(imported['depends_on'], [dependency])
        self.assertNotEqual(prepared['revision'], review['revision'])
        self.assertNotIn('depends_on', next(task for task in catalogue['tasks'] if task['key'] == 'review'))
        imported['depends_on'] = [{'task_key': 'review', 'revision': review['revision'], 'relation': 'uses-output', 'artifact': 'code.js', 'artifact_sha256': stored['artifact_hashes']['code.js']}]
        review_task = next(task for task in catalogue['tasks'] if task['key'] == 'review')
        review_task['depends_on'] = [{'task_key': 'import-task', 'revision': imported['revision'], 'relation': 'uses-output', 'artifact': 'code.js', 'artifact_sha256': imported['artifact_hashes']['code.js']}]
        with self.assertRaisesRegex(ValueError, 'cycle'):
            workspace.publish(root, catalogue)
