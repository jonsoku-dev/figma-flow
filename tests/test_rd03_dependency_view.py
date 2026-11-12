"""Selected task view lists one explicit dependency step and the same text.

Synthetic catalogue rows are not a live Figma panel observation.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace


ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
import { dependencyView } from './panel-ui/src/dependencyView.mjs';
const input = JSON.parse(process.argv[1]);
const before = JSON.stringify(input.tasks);
let view;
try {
  view = dependencyView(input.tasks, input.selected);
} catch (error) {
  process.stderr.write(String(error && error.message));
  process.exit(2);
}
if (JSON.stringify(input.tasks) !== before) {
  process.stderr.write('dependency view mutated tasks');
  process.exit(3);
}
process.stdout.write(JSON.stringify(view));
"""


def sample():
    review, imported = 'a' * 64, 'e' * 64
    return [
        {'key': 'review', 'title': 'Review', 'revision': review, 'project': 'desk'},
        {'key': 'import-task', 'title': 'Import', 'revision': imported, 'project': 'desk', 'depends_on': [{
            'task_key': 'review', 'revision': review, 'relation': 'uses-output', 'artifact': 'code.js',
            'artifact_sha256': 'b' * 64, 'secret': 'nope',
        }]},
        {'key': 'notes', 'title': 'Notes', 'revision': '3' * 64, 'project': 'desk', 'depends_on': [
            {'task_key': 'import-task', 'revision': imported, 'relation': 'uses-output', 'artifact': 'ui.html', 'artifact_sha256': '1' * 64},
            {'task_key': 'review', 'revision': review, 'relation': 'nearby', 'artifact': 'code.js', 'artifact_sha256': 'b' * 64},
        ]},
        {'key': 'alone', 'title': 'Alone', 'revision': '9' * 64, 'project': 'desk'},
    ]


class DependencyViewTests(unittest.TestCase):
    def run_view(self, tasks, selected):
        return subprocess.run(
            ['node', '--input-type=module', '--eval', RUNNER, json.dumps({'tasks': tasks, 'selected': selected})],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def view(self, tasks, selected):
        completed = self.run_view(tasks, selected)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_selected_node_lists_one_step_and_the_same_text(self):
        module = ROOT / 'panel-ui/src/dependencyView.mjs'
        source = module.read_text(encoding='utf-8') if module.is_file() else ''
        self.assertIn('export function dependencyView', source, 'selected dependency view must list predecessors and successors')
        self.assertNotIn('controlExecute', source)
        self.assertNotIn('mutation(', source)
        self.assertIn('연결된 선행·후속이 없습니다', source)

        tasks = sample()
        review, imported = 'a' * 64, 'e' * 64
        selected = self.view(tasks, 'import-task')
        self.assertEqual(set(selected), {'selected', 'predecessors', 'successors', 'text'})
        self.assertEqual(selected['selected'], 'import-task')
        self.assertEqual(selected['predecessors'], [{
            'role': 'predecessor', 'key': 'review', 'title': 'Review', 'relation': 'uses-output',
            'artifact': 'code.js', 'artifact_sha256': 'b' * 64,
            'pinned_revision': review, 'current_revision': review,
        }])
        self.assertEqual(selected['successors'], [{
            'role': 'successor', 'key': 'notes', 'title': 'Notes', 'relation': 'uses-output',
            'artifact': 'ui.html', 'artifact_sha256': '1' * 64,
            'pinned_revision': imported, 'current_revision': imported,
        }])
        self.assertEqual(selected['text'], [
            f'선행 Review review 현재 {review} 고정 {review} uses-output code.js {"b" * 64}',
            f'후속 Notes notes 현재 {imported} 고정 {imported} uses-output ui.html {"1" * 64}',
        ])
        self.assertNotIn('nope', json.dumps(selected))

        upstream = self.view(tasks, 'review')
        self.assertEqual(upstream['predecessors'], [])
        self.assertEqual([item['key'] for item in upstream['successors']], ['import-task'])
        self.assertNotIn('Notes', '\n'.join(upstream['text']))
        self.assertNotIn('nearby', '\n'.join(upstream['text']))
        self.assertEqual(upstream['successors'][0]['pinned_revision'], review)
        self.assertEqual(upstream['successors'][0]['current_revision'], review)

        alone = self.view(tasks, 'alone')
        self.assertEqual(alone['predecessors'], [])
        self.assertEqual(alone['successors'], [])
        self.assertEqual(alone['text'], ['연결된 선행·후속이 없습니다'])

        missing = self.run_view(tasks, 'missing')
        self.assertEqual(missing.returncode, 2)
        self.assertIn('unknown selected task', missing.stderr)

        publish = Path(workspace.__file__).read_text(encoding='utf-8')
        self.assertIn('metadata = public_task_metadata(task)', publish)
        meta = workspace.public_task_metadata({
            'key': 'import-task', 'title': 'Import', 'project': 'desk', 'kind': 'discover',
            'fileKey': None, 'pageId': None, 'threadId': None, 'revision': imported, 'handoff': None,
            'depends_on': [{
                'task_key': 'review', 'revision': review, 'relation': 'uses-output', 'artifact': 'code.js',
                'artifact_sha256': 'b' * 64, 'secret': 'nope',
            }],
        })
        self.assertEqual(meta['depends_on'], [{
            'task_key': 'review', 'revision': review, 'relation': 'uses-output', 'artifact': 'code.js',
            'artifact_sha256': 'b' * 64,
        }])
        self.assertNotIn('nope', json.dumps(meta))
        plain = workspace.public_task_metadata({'key': 'review', 'title': 'Review', 'project': 'desk', 'kind': 'review', 'revision': review})
        self.assertNotIn('depends_on', plain)

        host = (ROOT / 'figma-bridge/workspace_host.js').read_text(encoding='utf-8')
        start = host.index('function workspaceDependencyEdges')
        helper = host[start:host.index('figma.ui.onmessage', start)]
        self.assertNotIn('controlExecute', helper)
        self.assertNotIn('mutation', helper)
        self.assertIn('depends_on: dependsOn', host)

        ui = (ROOT / 'panel-ui/src/Workspace.jsx').read_text(encoding='utf-8')
        block = ui[ui.index('function DependencyText'):ui.index('export default function Workspace')]
        self.assertNotIn('sendMessage', block)
        self.assertNotIn('workspace-open', block)
        self.assertIn('workspace-dependency-text', block)
        self.assertIn('workspace-dependency-view', block)
        self.assertIn('view.text.map', block)
        self.assertIn('dependencyView(', block)
        bundle = (ROOT / 'figma-bridge/assets/panels.js').read_text(encoding='utf-8')
        self.assertIn('workspace-dependency-text', bundle)
        self.assertIn('workspace-dependency-view', bundle)
        css = (ROOT / 'panel-ui/src/styles/workspace.css').read_text(encoding='utf-8')
        shipped = (ROOT / 'figma-bridge/assets/panels.css').read_text(encoding='utf-8')
        self.assertIn('.workspace-dependency-graph', css)
        self.assertIn('max-width: 320px', css)
        self.assertIn('workspace-dependency-text', shipped)
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-03-task-dependencies/tasks.md').read_text(encoding='utf-8')
        self.assertIn('dependencyView', tasks_doc)
        self.assertIn('native mutation', tasks_doc)
