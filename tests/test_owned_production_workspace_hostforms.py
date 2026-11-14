"""Regression checks for external URL authority forms in owned production workspace text."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples' / 'owned-production-workspace'
sys.path.insert(0, str(ROOT / 'tools'))

import owned_production_workspace as workspace  # noqa: E402

ANCHOR = '"Design handoff operations"'


def verify_problems(test, rel, change):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = Path(tmp.name) / 'examples' / 'owned-production-workspace'
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
    path = root / rel
    before = path.read_text(encoding='utf-8')
    after = change(before)
    test.assertNotEqual(after, before)
    path.write_text(after, encoding='utf-8')
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        if entry['path'] == rel:
            entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    try:
        workspace.verify(root)
    except workspace.WorkspaceError as error:
        return error.problems
    return []


class AuthorityCompatibilityTest(unittest.TestCase):
    def test_comments_namespace_and_loopback_stay_allowed(self):
        self.assertEqual(verify_problems(self, 'renderer.js', lambda text: text + (
            '// TODO keep the gate order\n//TODO\n//FIXME later\nmount; // trailing note\n'
            '/* block note about //cdn/path */\n')), [])
        for text in (
            '<svg xmlns="http://www.w3.org/2000/svg"/>',
            '{"svg": "<svg xmlns=\\"http://www.w3.org/2000/svg\\">"}',
            '"http://127.0.0.1:8893/index.html#/review?package=pkg-field-input"',
            '"http://localhost:8893/?view=1#top"',
            '"//127.0.0.1:8893/index.html"',
            '"//localhost/index.html"',
            "fetch('./graph.json'); const route = '#/queue/empty?package=pkg-selection';",
        ):
            with self.subTest(text=text):
                self.assertEqual(workspace.scan_text('sample.js', text), [])


class AuthorityRejectionTest(unittest.TestCase):
    def test_rejects_every_external_authority_form_in_strings(self):
        graph_forms = (
            '"See //cdn/path"',
            '"See \\/\\/cdn\\/path"',
            '"See \\u002f\\u002fcdn/path"',
            '"See //[2001:db8::1]/path"',
            '"See //[2001:db8::1]:8443/path"',
            '"See //user:pass@cdn/path"',
            '"See //user:pass@127.0.0.1/path"',
            '"See //cdn.example.test./path"',
            '"See //[::1]/path"',
            '"//cdn"',
        )
        renderer_forms = (
            'location.assign("//cdn/path");\n',
            "location.assign('//user:pass@cdn/path');\n",
            'const target = `//[2001:db8::1]:8443/x`;\n',
            'const bare = "//cdn";\n',
        )
        cases = [('graph.json', form, lambda text, form=form: text.replace(ANCHOR, form, 1)) for form in graph_forms]
        cases += [('renderer.js', form, lambda text, form=form: text + form) for form in renderer_forms]
        for rel, form, change in cases:
            with self.subTest(rel=rel, form=form):
                problems = verify_problems(self, rel, change)
                self.assertTrue(any(problem.startswith(f'external URL in {rel}') for problem in problems),
                                f'external authority accepted in {rel}: {form} -> {problems}')


if __name__ == '__main__':
    unittest.main()
