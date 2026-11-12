"""Pin a prepared dependency fixture apart from a legacy catalogue.

Synthetic fixtures are not a live Figma panel observation.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace


ROOT = Path(__file__).resolve().parents[1]


class TaskDependencyFixtureTests(unittest.TestCase):
    def test_legacy_catalogue_stays_independent_of_the_declared_edge(self):
        load = getattr(workspace, 'load_task_dependency_fixtures', None)
        self.assertTrue(callable(load), 'prepared dependency fixtures must stay explicit')
        loaded = load(ROOT)
        self.assertTrue(all('depends_on' not in task for task in loaded['legacy']))
        declared = {task['key']: task for task in loaded['declared']}
        self.assertEqual(declared['import-task']['depends_on'], [{
            'task_key': 'review',
            'revision': 'a' * 64,
            'relation': 'uses-output',
            'artifact': 'code.js',
            'artifact_sha256': 'b' * 64,
        }])
        self.assertNotIn('depends_on', declared['review'])
        self.assertNotIn('depends_on', declared['notes'])
        self.assertFalse(any(edge['task_key'] == 'notes' for task in loaded['declared'] for edge in task.get('depends_on', [])))
        raw = json.loads((ROOT / 'tests/fixtures/rd03/legacy-tasks.json').read_text(encoding='utf-8'))
        self.assertEqual(raw['schema'], 'figma-flow-task-fixture-v1')
        self.assertEqual([task['key'] for task in raw['tasks']], ['review', 'import-task', 'notes'])
