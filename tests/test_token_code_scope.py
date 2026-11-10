import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import os

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
from token_code_scope import analyze, apply_plan, apply_changes, digest


class TokenCodeScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        shutil.copytree(BASE / 'examples/review-cards', self.root)
        self.before = json.loads((self.root / 'design.json').read_text())
        self.after = copy.deepcopy(self.before)
        self.after['tokens']['palette']['blue']['$value'] = '#112233'

    def tearDown(self):
        self.temp.cleanup()

    def test_consumers_and_guarded_apply(self):
        css = self.root / 'app/style.css'
        css.write_text(css.read_text() + '\n/* preserved comment */\n\n  .primary:hover { background: #123456; }\n')
        untouched = css.read_bytes()
        expected_line = css.read_text().splitlines().index('  .primary:hover { background: #123456; }') + 1
        report = analyze(self.root, self.before, self.after)
        uses = report['observed_consumers']
        self.assertTrue(any(u['class'] == 'button--secondary' and u['screen_ids'] == ['SCR-CARDS-REVIEW'] for u in uses))
        self.assertTrue(any(o['selector'] == '.primary:hover' and o['value'] == '#123456' and o['line'] == expected_line for o in report['possible_overrides']))
        self.assertEqual([p['path'] for p in report['plan']], ['app/tokens.css'])
        apply_plan(self.root, report['plan'])
        self.assertEqual((self.root / 'app/style.css').read_bytes(), untouched)
        self.assertEqual(analyze(self.root, self.before, self.after)['plan'], [])
        with self.assertRaisesRegex(ValueError, 'stale'):
            apply_plan(self.root, report['plan'])

    def test_js_class_has_typed_graph_candidate(self):
        after = copy.deepcopy(self.before)
        after['tokens']['palette']['pale']['$value'] = '#aabbcc'
        report = analyze(self.root, self.before, after)
        entry = next(u for u in report['observed_consumers'] if u['source'] == 'app/rules/list.js' and u['class'] == 'card--default')
        self.assertIn('CODE-CARDS-LIST', entry['code_ids'])
        self.assertIn(['SCR-CARDS-LIST', 'STATE-CARDS-LIST', 'CODE-CARDS-LIST'], entry['candidate_screen_traces'])

    def test_missing_runtime_use_is_gap(self):
        html = self.root / 'app/index.html'
        html.write_text(html.read_text().replace('button--secondary', 'other'))
        report = analyze(self.root, self.before, self.after)
        self.assertTrue(any('button--secondary' in gap for gap in report['gaps']))

    def test_preflight_and_rollback(self):
        paths = ['design.json', 'app/tokens.css']
        originals = [(self.root / p).read_bytes() for p in paths]
        changes = [{'path': p, 'preimage_sha256': digest(content), 'content': 'replacement'} for p, content in zip(paths, originals)]
        real_replace = os.replace
        def fail_second(src, dst):
            if Path(dst).resolve() == (self.root / paths[1]).resolve():
                raise OSError('injected failure')
            return real_replace(src, dst)
        with patch('token_code_scope.os.replace', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'injected failure'):
                apply_changes(self.root, changes)
        self.assertEqual([(self.root / p).read_bytes() for p in paths], originals)
        os.link(self.root / paths[1], self.root / 'hardlink')
        with self.assertRaisesRegex(ValueError, 'regular file'):
            apply_changes(self.root, changes)
        self.assertEqual((self.root / paths[0]).read_bytes(), originals[0])

    def test_comments_and_strings_not_consumers(self):
        html = self.root / 'app/index.html'
        html.write_text(html.read_text().replace('button--secondary', 'other'))
        js = self.root / 'app/rules/list.js'
        js.write_text(js.read_text() + "\n// x.className = 'button--secondary';\nconst s = \"x.className = 'button--secondary'\";\n")
        css = self.root / 'app/style.css'
        css.write_text(css.read_text() + '\n/* .primary:hover { background: red; } */\n')
        report = analyze(self.root, self.before, self.after)
        self.assertFalse(any(u['class'] == 'button--secondary' for u in report['observed_consumers']))
        self.assertFalse(any(o['value'] == 'red' for o in report['possible_overrides']))

    def test_untracked_runtime_and_selectors_report_unknown(self):
        (self.root / 'app/extra.ts').write_text("const shade = 'var(--color-brand)';")
        css = self.root / 'app/style.css'
        css.write_text(css.read_text() + '\n#special { color: var(--color-brand); }\n')
        html = self.root / 'app/index.html'
        html.write_text(html.read_text().replace('<body>', '<body><div style="color:var(--color-brand)"></div>'))
        report = analyze(self.root, self.before, self.after)
        self.assertTrue(any(x['source'] == 'app/extra.ts' and 'not bound' in x['reason'] for x in report['unknowns']))
        self.assertTrue(any(x.get('selector') == '#special' and 'no class' in x['reason'] for x in report['unknowns']))
        self.assertTrue(any(x['source'] == 'app/index.html' and 'inline style' in x['reason'] for x in report['unknowns']))

    def test_missing_generated_binding_blocks_change(self):
        path = self.root / 'bindings.json'
        bindings = json.loads(path.read_text())
        bindings['evidence']['CODE-CARDS-APP'].remove('app/tokens.css')
        path.write_text(json.dumps(bindings))
        with self.assertRaisesRegex(ValueError, 'not bound'):
            analyze(self.root, self.before, self.after)

    def test_css_drift_never_overwritten(self):
        css = self.root / 'app/tokens.css'
        css.write_text(css.read_text() + '/* user edit */\n')
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            analyze(self.root, self.before, self.after, apply=True)
        self.assertIn('user edit', css.read_text())
        components = self.root / 'app/components.css'
        components.write_text(components.read_text() + '/* custom */\n')
        report = analyze(self.root, self.before, self.before)
        self.assertTrue(any('components.css' in g for g in report['gaps']))


if __name__ == '__main__':
    unittest.main()
