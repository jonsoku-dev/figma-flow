"""Independent publish/retire dependency oracle; no live Figma acceptance implied."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class DependencyPublication(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'workspace'
        assigned = self.root / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.path, assigned)
        self.prepare('source')
        self.source = workspace.current(self.path)['tasks'][0]
        self.edge = {'task_key': 'source', 'revision': self.source['revision'],
                     'relation': 'uses-output', 'artifact': 'code.js',
                     'artifact_sha256': self.source['artifact_hashes']['code.js']}
        self.prepare('consumer', depends_on=[self.edge])

    def prepare(self, key, title=None, **kwargs):
        return workspace.prepare(self.path, key, title or key, 'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'], infer_thread=False, **kwargs)

    def snapshot(self):
        return {str(path.relative_to(self.path)): path.read_bytes()
                for path in self.path.rglob('*') if path.is_file()}

    def retired(self):
        manifest = json.loads((self.path / 'manifest.json').read_text())
        code = (self.path / manifest['main']).read_text()
        match = re.search(r'^const FLOW_RETIRED = (.*);$', code, re.M)
        self.assertIsNotNone(match, 'generated runtime must publish safe retirement metadata')
        value = json.loads(match[1])
        self.assertTrue(all(set(row) == {'key', 'revision'} for row in value))
        return value

    def freshness(self, tasks, retired):
        runner = """import { dependencyFreshness } from './panel-ui/src/dependencyView.mjs';
const input = JSON.parse(process.argv[1]);
console.log(JSON.stringify(dependencyFreshness(input.tasks, input.retired)));"""
        result = subprocess.run(['node', '--input-type=module', '--eval', runner,
            json.dumps({'tasks': tasks, 'retired': retired})], cwd=ROOT,
            capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_real_retirement_preserves_edge_artifacts_and_projects_read_only_state(self):
        pinned = workspace.task_artifacts(self.path, self.source) / 'code.js'
        original = pinned.read_bytes()
        selected = self.root / 'retire.json'
        selected.write_text(json.dumps({'schema': 'figma-flow-workspace-retirement-v1',
            'tasks': [{'key': 'source', 'revision': self.source['revision']}]}))
        try:
            workspace.retire(self.path, selected)
        except Exception as error:
            self.fail(f'retirement must preserve admitted consumer edges: {type(error).__name__}: {error}')
        catalogue = workspace.current(self.path)
        self.assertEqual([row['key'] for row in catalogue['tasks']], ['consumer'])
        self.assertEqual(catalogue['tasks'][0]['depends_on'], [self.edge])
        self.assertEqual(pinned.read_bytes(), original)
        retired = self.retired()
        self.assertEqual(retired, [{'key': 'source', 'revision': self.source['revision']}])
        state = self.freshness(catalogue['tasks'], retired)
        self.assertEqual(state['labels'][0]['state'], 'retired')
        self.assertTrue(state['read_only'])
        self.assertEqual(state['execution'], 'unchanged')
        workspace.refresh(self.path)
        self.assertEqual(self.retired(), retired)
        orphan = copy.deepcopy(catalogue['tasks'])
        orphan[0]['depends_on'][0]['task_key'] = 'never-admitted'
        self.assertEqual(self.freshness(orphan, retired)['labels'][0]['state'], 'orphan')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            workspace.publish(self.path, {**catalogue, 'tasks': orphan})
        self.assertEqual(self.snapshot(), before)

    def test_malformed_json_edge_fields_raise_valueerror_before_publication(self):
        catalogue = workspace.current(self.path)
        for field in self.edge:
            for value in ([], {}, None, True, 7):
                with self.subTest(field=field, value=value):
                    changed = copy.deepcopy(catalogue)
                    changed['tasks'][1]['depends_on'][0][field] = value
                    before = self.snapshot()
                    try:
                        workspace.publish(self.path, changed)
                    except ValueError:
                        pass
                    except Exception as error:
                        self.fail(f'malformed {field} must raise ValueError before writes, got {type(error).__name__}')
                    else:
                        self.fail(f'malformed {field} must be rejected before writes')
                    self.assertEqual(self.snapshot(), before)

    def test_replacing_active_source_preserves_prior_revision_and_marks_stale(self):
        pinned = workspace.task_artifacts(self.path, self.source) / 'code.js'
        original = pinned.read_bytes()
        try:
            replacement = self.prepare('source', title='Revised source',
                replace_expected=self.source['revision'])
        except Exception as error:
            self.fail(f'active replacement must retain existing pinned edges as stale: {type(error).__name__}: {error}')
        tasks = workspace.current(self.path)['tasks']
        self.assertNotEqual(replacement['revision'], self.source['revision'])
        self.assertEqual(tasks[1]['depends_on'], [self.edge])
        self.assertEqual(pinned.read_bytes(), original)
        self.assertEqual(self.retired(), [])
        label = self.freshness(tasks, self.retired())['labels'][0]
        self.assertEqual(label['state'], 'stale')
        self.assertEqual(label['pinned_revision'], self.source['revision'])
        self.assertEqual(label['current_revision'], replacement['revision'])


if __name__ == '__main__':
    unittest.main()
