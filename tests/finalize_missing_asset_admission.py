"""Normal producer records pin absent assets without weakening root admission."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace
import input_effect


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class MissingAssetAdmission(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'workspace'
        assigned = self.root / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(self.path, assigned)
        (self.root / 'brief.md').write_text('Booking app')
        (self.root / 'facts.json').write_text('{"service_name":"Booking"}')
        (self.root / 'authority.json').write_text(json.dumps({'facts': {'service_name': {'priority': ['brief']}}}))
        (self.root / 'index.html').write_text('<link rel="stylesheet" href="app.css"><img src="photo.png" alt="Photo">')
        (self.root / 'app.css').write_text('@font-face{font-family:Body;src:url(font.woff2)}')
        (self.root / 'font.woff2').write_bytes(b'wOF2' + bytes(44))
        self.spec = {'schema': input_effect.SCHEMA, 'brief': 'brief.md', 'facts': 'facts.json',
                     'authority': 'authority.json', 'inputs': {'html': 'index.html'}}
        self.record = input_effect.project(self.root, self.spec)

    def prepare(self, record, key='missing-photo', **kwargs):
        return workspace.prepare(self.path, key, key, 'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'], infer_thread=False,
            input_record=record, input_root=self.root, **kwargs)

    def test_normal_missing_asset_admission_and_refresh(self):
        missing = next(row for row in self.record['sources'] if row['path'] == 'photo.png')
        self.assertIn('sha256', missing)
        self.assertIsNone(missing['sha256'])
        self.assertEqual(input_effect.freshness(self.record, self.root)['status'], 'current')
        try:
            admitted = self.prepare(self.record)
        except ValueError as error:
            self.fail('normal producer record must admit an explicitly absent asset: ' + str(error))
        task = workspace.current(self.path)['tasks'][0]
        self.assertEqual(workspace.task_input_freshness(self.path, task)['status'], 'current')
        public = workspace.public_task_metadata(task)
        photo = next(row for row in public['input_summary'] if row['ref'].endswith('photo.png'))
        self.assertEqual(photo['status'], '404')
        (self.root / 'photo.png').write_bytes(b'image-fixture')
        self.assertEqual(workspace.task_input_freshness(self.path, task)['status'], 'stale')
        with self.assertRaises(ValueError):
            self.prepare(self.record, replace_expected=admitted['revision'])
        fresh = input_effect.project(self.root, self.spec)
        self.prepare(fresh, replace_expected=admitted['revision'])
        self.assertEqual(workspace.task_input_freshness(self.path, workspace.current(self.path)['tasks'][0])['status'], 'current')
        (self.root / 'font.woff2').write_bytes(b'changed-font')
        with self.assertRaises(ValueError):
            self.prepare(fresh, key='changed-bytes')

    def test_rejects_forged_or_unsafe_source_pins(self):
        for value in [None, '', 'a' * 63, 'g' * 64, 42, [], {}]:
            with self.subTest(present_hash=value):
                record = copy.deepcopy(self.record)
                record['sources'][0]['sha256'] = value
                with self.assertRaises(ValueError):
                    self.prepare(record)
        record = copy.deepcopy(self.record)
        del record['sources'][-1]['sha256']
        with self.assertRaises(ValueError):
            self.prepare(record)
        for path in ['../outside.png', '/outside.png']:
            with self.subTest(path=path):
                record = copy.deepcopy(self.record)
                record['sources'].append({'path': path, 'sha256': None})
                with self.assertRaises(ValueError):
                    self.prepare(record)
        (self.root / 'photo.png').symlink_to(self.root / 'font.woff2')
        with self.assertRaises(ValueError):
            self.prepare(self.record)


if __name__ == '__main__':
    unittest.main()
