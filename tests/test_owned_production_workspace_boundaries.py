"""Regression checks for the owned production workspace URL scan and serve snapshot boundaries."""
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples' / 'owned-production-workspace'
sys.path.insert(0, str(ROOT / 'tools'))

import owned_production_workspace as workspace  # noqa: E402


def copy_fixture(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    base = Path(tmp.name)
    root = base / 'examples' / 'owned-production-workspace'
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
    return base, root


def repin(root, rel):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        if entry['path'] == rel:
            entry['sha256'] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


def problems_after(root):
    try:
        workspace.verify(root)
    except workspace.WorkspaceError as error:
        return error.problems
    return []


class SchemeRelativeUrlTest(unittest.TestCase):
    def test_rejects_scheme_relative_and_escaped_external_urls(self):
        cases = (
            ('graph.json', lambda text: text.replace('"Design handoff operations"', '"See //cdn.example.test/asset.js"')),
            ('renderer.js', lambda text: text + 'location.assign("//cdn.example.test/x");\n'),
            ('graph.json', lambda text: text.replace('"Design handoff operations"', '"See https:\\/\\/cdn.example.test\\/kit"')),
            ('graph.json', lambda text: text.replace('"Design handoff operations"', '"See \\/\\/cdn.example.test\\/kit"')),
        )
        for rel, change in cases:
            with self.subTest(rel=rel, change=change):
                _, root = copy_fixture(self)
                path = root / rel
                changed = change(path.read_text(encoding='utf-8'))
                self.assertNotEqual(changed, path.read_text(encoding='utf-8'))
                path.write_text(changed, encoding='utf-8')
                repin(root, rel)
                problems = problems_after(root)
                self.assertTrue(any('external URL' in problem and rel in problem for problem in problems),
                                f'scheme-relative or escaped external URL accepted in {rel}: {problems}')

    def test_keeps_namespace_loopback_query_and_relative_references(self):
        self.assertEqual(problems_after(FIXTURE), [])
        for text in (
            '<svg xmlns="http://www.w3.org/2000/svg"/>',
            '{"svg": "<svg xmlns=\\"http://www.w3.org/2000/svg\\">"}',
            '"http://127.0.0.1:8893/index.html#/review?package=pkg-field-input"',
            '"http://localhost:8893/index.html?view=1"',
            '"//127.0.0.1:8893/index.html"',
            "fetch('./graph.json'); href: '#/queue/empty?package=pkg-selection'",
            "const ROUTE = /^#\\/([a-z-]+)(?:\\/([a-z-]+))?$/;",
            '// a line comment about the renderer\nconst x = 1; // trailing comment',
            'media/queue-empty.svg ../../LICENSE',
        ):
            with self.subTest(text=text):
                self.assertEqual(workspace.scan_text('sample.js', text), [])


class ServeSnapshotTest(unittest.TestCase):
    def test_serves_the_manifest_snapshot_that_verify_approved(self):
        base, root = copy_fixture(self)
        original = workspace._read_manifest
        calls = []

        def unreviewed_write():
            if 'written' in calls:
                return
            calls.append('written')
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            with (root / 'styles.css').open('a', encoding='utf-8') as handle:
                handle.write('.unreviewed { display: none; }\n')
            for entry in manifest['files']:
                if entry['path'] == 'README.md':
                    entry['serve'] = True
                if entry['path'] == 'styles.css':
                    entry['sha256'] = hashlib.sha256((root / 'styles.css').read_bytes()).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

        def read_after_verification(path):
            calls.append('read')
            if calls.count('read') > 1:
                unreviewed_write()
            return original(path)

        workspace._read_manifest = read_after_verification
        self.addCleanup(setattr, workspace, '_read_manifest', original)
        server, receipt = workspace.make_server(root, '127.0.0.1', 0, base / 'served.jsonl')
        unreviewed_write()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def status(path):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                response.read()
                return response.status
            finally:
                connection.close()

        served = {item['path'] for item in receipt['inputs']['files'] if item['serve']}
        self.assertNotIn('README.md', served)
        self.assertEqual(status('/index.html'), 200)
        self.assertEqual(status('/README.md'), 404, 'serve must use the verified manifest snapshot')
        self.assertEqual(status('/styles.css'), 409, 'serve must keep the verified digest for styles.css')


if __name__ == '__main__':
    unittest.main()
