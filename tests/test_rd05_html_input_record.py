"""One HTML task keeps a hash-pinned input record and a safe summary.

The summary is not a browser or Figma render of the assets.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace
import input_effect


THREAD = '12345678-abcd-4abc-9abc-123456789abc'


def record():
    return {
        'schema': 'figma-flow-input-effect-result-v3',
        'channels': {'html': {'assets': [
            {'ref': 'fonts/body.woff2', 'status': 'present', 'kind': 'font', 'source': 'css/type.css'},
            {'ref': 'photos/missing.png', 'status': '404', 'kind': 'image', 'source': 'index.html'},
            {'ref': '../secret', 'status': 'rejected', 'kind': 'image', 'source': 'index.html'},
            {'ref': 'https://fonts.example/font.woff2?user=ada#frag', 'status': 'external-unverified', 'kind': 'font', 'source': 'css/type.css'},
            {'ref': '/Users/jongseoklee/secret.png', 'status': 'rejected', 'kind': 'image', 'source': '/Users/jongseoklee/page.html'},
        ]}},
        'sources': [{'path': 'index.html', 'sha256': 'a' * 64}],
    }


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class HtmlInputRecordTests(unittest.TestCase):
    def test_html_task_pins_the_record_and_hides_private_paths(self):
        summarize = getattr(input_effect, 'summarize_input_record', None)
        self.assertTrue(callable(summarize), 'html task input record must keep its hash and a safe summary')
        pinned = summarize(record())
        self.assertEqual(pinned['sha256'], input_effect.digest(input_effect.canonical(record()).encode()))
        self.assertEqual(len(pinned['sha256']), 64)
        text = json.dumps(pinned['summary'])
        self.assertNotIn('/Users/jongseoklee', text)
        self.assertNotIn('user=ada', text)
        self.assertNotIn('#frag', text)
        self.assertEqual([row['status'] for row in pinned['summary']], ['present', '404', 'rejected', 'external-unverified', 'rejected'])
        self.assertEqual(pinned['summary'][3]['ref'], 'https://fonts.example/font.woff2')
        self.assertTrue(all(len(row['digest']) == 12 and set(row) == {'ref', 'kind', 'status', 'source', 'digest'} for row in pinned['summary']))

        root = Path(tempfile.mkdtemp())
        identity = root / 'assigned.json'
        identity.write_text('{"id":"12345"}')
        path = root / 'workspace'
        workspace.init(path, identity)
        args = ['--file-key', 'fixturefile', '--page-id', '12:1']
        plain = workspace.prepare(path, 'read-test', 'Read', 'discover', args, thread_id=THREAD, infer_thread=False)
        plain_task = next(row for row in workspace.current(path)['tasks'] if row['key'] == 'read-test')
        self.assertNotIn('input_record', plain_task)
        stored = workspace.prepare(path, 'html-task', 'HTML', 'discover', args, thread_id=THREAD, infer_thread=False, input_record=record())
        task = next(row for row in workspace.current(path)['tasks'] if row['key'] == 'html-task')
        self.assertEqual(task['input_record'], {'artifact': 'input-record.json', 'sha256': pinned['sha256']})
        self.assertNotEqual(stored['revision'], plain['revision'])
        artifact = workspace.task_artifacts(path, task) / 'input-record.json'
        self.assertEqual(input_effect.digest(artifact.read_bytes()), pinned['sha256'])
        self.assertIn('/Users/jongseoklee', artifact.read_text(encoding='utf-8'))
        self.assertNotIn('/Users/jongseoklee', json.dumps(task['input_summary']))
        self.assertEqual(task['input_summary'], pinned['summary'])
        tasks_doc = (Path(__file__).resolve().parents[1] / 'docs/development-roadmap/RD-05-asset-inventory/tasks.md').read_text(encoding='utf-8')
        self.assertIn('summarize_input_record', tasks_doc)
