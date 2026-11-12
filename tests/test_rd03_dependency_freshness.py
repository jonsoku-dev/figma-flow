"""Stale, retired, and orphan dependencies stay visible and read-only.

Synthetic catalogue rows are not a live Figma panel observation.
"""
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
import { dependencyFreshness } from './panel-ui/src/dependencyView.mjs';
const input = JSON.parse(process.argv[1]);
const before = JSON.stringify(input.tasks);
const retiredBefore = JSON.stringify(input.retired);
let view;
try {
  view = dependencyFreshness(input.tasks, input.retired);
} catch (error) {
  process.stderr.write(String(error && error.message));
  process.exit(2);
}
if (JSON.stringify(input.tasks) !== before || JSON.stringify(input.retired) !== retiredBefore) {
  process.stderr.write('dependency freshness mutated tasks');
  process.exit(3);
}
process.stdout.write(JSON.stringify(view));
"""


def sample():
    review_old, review_new, imported = 'a' * 64, 'c' * 64, 'e' * 64
    return [
        {'key': 'review', 'title': 'Review', 'revision': review_new, 'project': 'desk', 'status': 'finished'},
        {'key': 'import-task', 'title': 'Import', 'revision': imported, 'project': 'desk', 'status': 'finished', 'depends_on': [{
            'task_key': 'review', 'revision': review_old, 'relation': 'uses-output', 'artifact': 'code.js',
            'artifact_sha256': 'b' * 64, 'secret': 'nope',
        }]},
        {'key': 'notes', 'title': 'Notes', 'revision': '3' * 64, 'project': 'desk', 'status': 'finished', 'depends_on': [
            {'task_key': 'import-task', 'revision': imported, 'relation': 'uses-output', 'artifact': 'ui.html', 'artifact_sha256': '1' * 64},
            {'task_key': 'review', 'revision': review_new, 'relation': 'nearby', 'artifact': 'code.js', 'artifact_sha256': 'b' * 64},
        ]},
        {'key': 'draft', 'title': 'Draft', 'revision': '9' * 64, 'project': 'desk', 'depends_on': [{
            'task_key': 'gone', 'revision': 'd' * 64, 'relation': 'uses-output', 'artifact': 'manifest.json', 'artifact_sha256': 'f' * 64,
        }]},
        {'key': 'history', 'title': 'History', 'revision': '8' * 64, 'project': 'desk', 'depends_on': [{
            'task_key': 'archive', 'revision': '7' * 64, 'relation': 'uses-output', 'artifact': 'code.js', 'artifact_sha256': '4' * 64,
        }]},
    ], [{'key': 'archive', 'revision': '7' * 64}]


class DependencyFreshnessTests(unittest.TestCase):
    def test_stale_retired_and_orphan_dependencies_stay_read_only(self):
        module = ROOT / 'panel-ui/src/dependencyView.mjs'
        source = module.read_text(encoding='utf-8') if module.is_file() else ''
        self.assertIn('export function dependencyFreshness', source, 'stale retired and orphan dependencies must stay read only')
        start = source.index('export function dependencyFreshness')
        self.assertNotIn('controlExecute', source[start:])
        self.assertNotIn('prepare(', source[start:])
        self.assertNotIn('publish(', source[start:])
        self.assertNotIn('retire(', source[start:])

        tasks, retired = sample()
        completed = subprocess.run(
            ['node', '--input-type=module', '--eval', RUNNER, json.dumps({'tasks': tasks, 'retired': retired})],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        view = json.loads(completed.stdout)
        review_old, review_new, imported = 'a' * 64, 'c' * 64, 'e' * 64
        self.assertEqual(set(view), {'read_only', 'labels', 'execution'})
        self.assertEqual(view['read_only'], True)
        self.assertEqual(view['execution'], 'unchanged')
        self.assertEqual(view['labels'], [
            {'task_key': 'import-task', 'dependency': 'review', 'state': 'stale', 'pinned_revision': review_old, 'current_revision': review_new, 'read_only': True},
            {'task_key': 'notes', 'dependency': 'import-task', 'state': 'current', 'pinned_revision': imported, 'current_revision': imported, 'read_only': True},
            {'task_key': 'draft', 'dependency': 'gone', 'state': 'orphan', 'pinned_revision': 'd' * 64, 'current_revision': None, 'read_only': True},
            {'task_key': 'history', 'dependency': 'archive', 'state': 'retired', 'pinned_revision': '7' * 64, 'current_revision': '7' * 64, 'read_only': True},
        ])
        self.assertNotIn('nope', json.dumps(view))
        self.assertNotIn('nearby', json.dumps(view))
        self.assertTrue(all(task.get('status', 'finished') == 'finished' for task in tasks))

        ui = (ROOT / 'panel-ui/src/Workspace.jsx').read_text(encoding='utf-8')
        block = ui[ui.index('function DependencyText'):ui.index('export default function Workspace')]
        self.assertIn('dependencyFreshness(', block)
        self.assertIn('workspace-dependency-state', block)
        self.assertIn('오래됨', block)
        self.assertIn('은퇴', block)
        self.assertIn('대상 없음', block)
        self.assertNotIn('sendMessage', block)
        self.assertNotIn('workspace-open', block)
        bundle = (ROOT / 'figma-bridge/assets/panels.js').read_text(encoding='utf-8')
        self.assertIn('workspace-dependency-state', bundle)
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-03-task-dependencies/tasks.md').read_text(encoding='utf-8')
        self.assertIn('dependencyFreshness', tasks_doc)
        self.assertIn('자동 실행', tasks_doc)
