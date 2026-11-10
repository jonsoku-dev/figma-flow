import importlib.util
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'tools/audit_dependencies.py'
spec = importlib.util.spec_from_file_location('audit_dependencies', MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DependencyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.graph = {'nodes': [{'id': x, 'type': t} for x, t in [('CODE-A', 'code'), ('CODE-B', 'code'), ('TEST-A', 'test'), ('SCR-A', 'screen')]], 'edges': []}
        self.bindings = {'evidence': {'CODE-A': ['a.js'], 'CODE-B': ['b.js'], 'TEST-A': ['test.js']}, 'dependency_edge_types': ['depends-on']}
        (self.root / 'a.js').write_text('export const x = 1;')
        (self.root / 'b.js').write_text("import {x} from './a.js';")
        (self.root / 'test.js').write_text('// no imports')

    def edge(self, a, b, kind='depends-on'):
        self.graph['edges'].append({'from': a, 'to': b, 'type': kind})

    def run_audit(self):
        return audit.audit(self.root, self.graph, self.bindings)

    def test_removed_import_path_and_indirect_path(self):
        result = self.run_audit()
        self.assertEqual(result['status'], 'missing')
        self.assertEqual((result['missing'][0]['from'], result['missing'][0]['to'], result['missing'][0]['line']), ('CODE-A', 'CODE-B', 1))
        self.edge('CODE-A', 'TEST-A')
        self.edge('TEST-A', 'CODE-B')
        self.assertEqual(self.run_audit()['status'], 'clear')

    def test_coverage_separate_from_navigation(self):
        (self.root / 'b.js').write_text('')
        self.edge('SCR-A', 'CODE-A', 'implemented by')
        self.edge('CODE-A', 'TEST-A', 'checked by')
        result = self.run_audit()
        self.assertEqual([(x['from'], x['to'], x['kind']) for x in result['candidates']], [('CODE-A', 'TEST-A', 'coverage')])
        self.edge('CODE-A', 'TEST-A')
        self.assertEqual(self.run_audit()['status'], 'clear')

    def test_comments_strings_and_unresolved(self):
        (self.root / 'b.js').write_text('const a = "require(\'./a.js\')"; // import "./a.js"\n/* require("./a.js") */\nimport(name);')
        result = self.run_audit()
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['missing'])
        self.assertEqual(result['unknown'][0]['line'], 3)

    def test_regex_division_template_and_shadowed_require(self):
        (self.root / 'b.js').write_text(r"const pattern = /require\('a'\)/; const x = 6 / 2; const y = `text ${1 + 2}`;")
        self.assertEqual(self.run_audit()['status'], 'clear')
        (self.root / 'b.js').write_text("function run(require) { require('./a.js'); }")
        result = self.run_audit()
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['missing'])

    def test_dynamic_template_import_and_source_only_owner(self):
        self.bindings['evidence'].pop('CODE-A')
        self.graph['nodes'][0]['source'] = 'a.js'
        self.assertEqual(self.run_audit()['missing'][0]['from'], 'CODE-A')
        (self.root / 'b.js').write_text("import(`./${name}.js`)")
        self.assertEqual(self.run_audit()['status'], 'unknown')

    def test_unbound_and_unsupported_sources_are_unknown(self):
        (self.root / 'extra.js').write_text("import './a.js'")
        self.assertTrue(any('no code/test binding' in x['reason'] for x in self.run_audit()['unknown']))
        (self.root / 'extra.js').unlink()
        (self.root / 'component.ts').write_text('const x: number = 1;')
        self.bindings['evidence']['CODE-B'] = ['component.ts']
        self.assertTrue(any('not supported' in x['reason'] for x in self.run_audit()['unknown']))

    def test_removed_card_module_edges_are_found_from_bundled_sources(self):
        cards = MODULE.parents[1] / 'examples/review-cards'
        graph = json.loads((cards / 'graph.json').read_text())
        bindings = json.loads((cards / 'bindings.json').read_text())
        self.assertEqual(audit.audit(cards, graph, bindings)['status'], 'clear')
        graph['edges'] = [e for e in graph['edges'] if not (
            e['type'] == 'depends-on' and e['to'] == 'CODE-CARDS-APP' and e['from'].startswith('CODE-CARDS-'))]
        result = audit.audit(cards, graph, bindings)
        self.assertEqual(len(result['missing']), 7)
        self.assertTrue(all(x['kind'] == 'source-import' and x['path'] == 'app/index.html' for x in result['missing']))
        self.assertEqual(result['unknown'], [])
        self.assertEqual(result['scanned_files'], sorted(result['scanned_hashes']))
        for name, digest in result['scanned_hashes'].items():
            self.assertEqual(digest, hashlib.sha256((cards / name).read_bytes()).hexdigest())

    def test_css_imports_and_unknown_conditions(self):
        self.bindings['evidence']['CODE-A'] = ['base.css']
        self.bindings['evidence']['CODE-B'] = ['page.css']
        (self.root / 'base.css').write_text('body { color: red }')
        (self.root / 'page.css').write_text(
            '/* @import "fake.css"; */\n@import /* comment */ "base.css";\n'
            "@import url('base.css');\n@import url(base.css);\n"
            '@import "base.css" screen and (min-width: 1px);\n'
            'p { content: "@import \\"fake.css\\";"; }')
        result = self.run_audit()
        self.assertEqual([x['line'] for x in result['missing']], [2, 3, 4])
        self.assertTrue(any('conditional' in x['reason'] for x in result['unknown']))
        self.assertEqual(result['missing'][0]['from'], 'CODE-A')
        self.edge('CODE-A', 'CODE-B')
        self.assertEqual(self.run_audit()['status'], 'unknown')

    def test_import_after_charset_preserves_line_and_target(self):
        refs, unknown = audit.parse_css('@charset "UTF-8";\n/* heading */\n@import url("theme.css");')
        self.assertEqual(refs, [('theme.css', 3, 'css-import')])
        self.assertEqual(unknown, [])

    def test_css_unsupported_or_malformed_never_proves_import(self):
        for text in ('/* unterminated; @import "base.css";',
                     'p { content: "unterminated; @import \"base.css\";',
                     '@media screen { @import "base.css"; }',
                     'p {} @import "base.css";',
                     '@import url(var(--path));',
                     '@import "base.css" layer(foo);'):
            with self.subTest(text=text):
                refs, unknown = audit.parse_css(text)
                self.assertFalse(refs)
                self.assertTrue(unknown)

    def test_css_import_on_temporary_review_cards_copy(self):
        cards = MODULE.parents[1] / 'examples/review-cards'
        target = self.root / 'cards'
        shutil.copytree(cards, target)
        graph = json.loads((target / 'graph.json').read_text())
        bindings = json.loads((target / 'bindings.json').read_text())
        css = next(path for path in target.rglob('*.css'))
        imported = css.parent / 'audit-import.css'
        imported.write_text('body { color: red }')
        css.write_text('@import "audit-import.css";\n' + css.read_text())
        graph['nodes'].append({'id': 'CODE-CSS-IMPORT', 'type': 'code'})
        bindings['evidence']['CODE-CSS-IMPORT'] = [str(imported.relative_to(target))]
        result = audit.audit(target, graph, bindings)
        self.assertTrue(any(x['from'] == 'CODE-CSS-IMPORT' and
                            x['target_path'] == str(imported.relative_to(target))
                            for x in result['missing']))

    def test_html_asset_and_ambiguous_bindings(self):
        (self.root / 'index.html').write_text('<script type="module" src="./a.js"></script>')
        self.bindings['evidence']['CODE-B'] = ['index.html']
        self.bindings['evidence']['TEST-A'].append('index.html')
        result = self.run_audit()
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(len(result['candidates']), 2)
        self.assertFalse(result['missing'])


if __name__ == '__main__':
    unittest.main()
