"""Focused checks for local CSS dependency collection."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/regression-program'
sys.path.insert(0, str(ROOT / 'tools'))
import input_effect


def spec():
    return {
        'schema': input_effect.SCHEMA,
        'brief': 'atlas/brief.md',
        'facts': 'atlas/brief-facts.json',
        'authority': 'atlas/authority.json',
        'expected_package_version': '0.1.0',
        'inputs': {'html': 'html/index.html'},
    }


class CssDependencyParserTests(unittest.TestCase):
    def root(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        shutil.copytree(FIXTURE / 'atlas', root / 'atlas')
        return tmp, root

    def project(self, root, html):
        page = root / 'html/index.html'
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(html, encoding='utf-8')
        return input_effect.project(root, spec())

    def test_html_styles_and_nested_imports_capture_real_urls_and_ignore_fake_markup(self):
        tmp, root = self.root()
        with tmp:
            css = root / 'html/styles/site.css'
            nested = root / 'html/styles/nested/theme.css'
            nested.parent.mkdir(parents=True)
            css.write_text('@import "nested/theme.css"; /* url(fake.png) */ .x { content: "url(fake2.png)"; }', encoding='utf-8')
            nested.write_text('@import url("../site.css"); @font-face { src: url(../../font.woff2); }', encoding='utf-8')
            (root / 'html/font.woff2').write_bytes(b'font')
            (root / 'html/photo.png').write_bytes(b'image')
            (root / 'html/inline.png').write_bytes(b'inline')
            (root / 'html/hover.png').write_bytes(b'hover')
            html = '''<!-- <img src="comment.png"> -->
                <script>const fake = '<img src="script.png">';</script>
                <link rel="stylesheet" href="styles/site.css">
                <style>.hero { background: url("photo.png"); }</style>
                <div style="mask: url(inline.png)"></div>
                <div style="background: url('hover.png')"></div>'''
            record = self.project(root, html)
            source_paths = {item['path'] for item in record['sources']}
            self.assertTrue({'html/styles/site.css', 'html/styles/nested/theme.css', 'html/font.woff2', 'html/photo.png', 'html/inline.png', 'html/hover.png'} <= source_paths)
            self.assertFalse(any('fake' in path or 'comment.png' in path or 'script.png' in path for path in source_paths))
            self.assertEqual(len(source_paths), len(record['sources']))
            self.assertEqual(sum(asset['ref'] == 'photo.png' for asset in record['channels']['html']['assets']), 1)

    def test_inline_import_and_extensionless_stylesheet_import_capture_descendants(self):
        tmp, root = self.root()
        with tmp:
            (root / 'html/css').mkdir(parents=True)
            (root / 'html/css/site').write_text('@import "nested"; .x { gap: 12px; }', encoding='utf-8')
            (root / 'html/css/nested').write_text('@font-face { src: url(../font.woff2); } .x { gap: 28px; }', encoding='utf-8')
            (root / 'html/inline-theme').write_text('@import "inline-fonts";', encoding='utf-8')
            (root / 'html/inline-fonts').write_text('@font-face { src: url(fonts/inline.woff2); }', encoding='utf-8')
            (root / 'html/font.woff2').write_bytes(b'linked font')
            (root / 'html/fonts').mkdir()
            (root / 'html/fonts/inline.woff2').write_bytes(b'inline font')
            html = '<link rel="stylesheet" href="css/site"><style>@import "inline-theme";</style>'
            record = self.project(root, html)
            sources = {item['path'] for item in record['sources']}
            self.assertTrue({'html/css/site', 'html/css/nested', 'html/font.woff2', 'html/inline-theme', 'html/inline-fonts', 'html/fonts/inline.woff2'} <= sources)
            self.assertEqual(record['channels']['html']['facts']['surface-gap'], '12px')

    def test_imported_stylesheet_inherits_parent_encoding(self):
        tmp, root = self.root()
        with tmp:
            (root / 'html').mkdir()
            (root / 'html/site.css').write_bytes(b'@charset "iso-8859-1"; @import "theme"; .x { gap: 12px; }')
            (root / 'html/theme').write_bytes(b'.x { background: url("caf\xe9.png"); }')
            (root / 'html/caf\xe9.png').write_bytes(b'image')
            record = self.project(root, '<link rel="stylesheet" type="text/css" href="site.css">')
            self.assertIn('html/caf\xe9.png', {item['path'] for item in record['sources']})

    def test_direct_layout_facts_include_direct_css_but_not_imported_css(self):
        tmp, root = self.root()
        with tmp:
            (root / 'html').mkdir()
            (root / 'html/site').write_text('@import "theme"; .x { gap: 12px; }', encoding='utf-8')
            (root / 'html/theme').write_text('.x { gap: 28px; }', encoding='utf-8')
            record = self.project(root, '<link href="site" rel="stylesheet">')
            self.assertEqual(record['channels']['html']['facts']['surface-gap'], '12px')

    def test_nested_function_urls_escaped_url_names_and_unterminated_style(self):
        tmp, root = self.root()
        with tmp:
            (root / 'html').mkdir()
            for name in ('photo.png', 'fallback.svg', 'escaped image.png', 'eof.png'):
                (root / 'html' / name).write_bytes(b'asset')
            html = '''<style>
                .hero { background-image: image-set(url('photo.png') 1x); }
                .mask { mask: var(--mask, url('fallback.svg')); }
                .escaped { background: u\\72l("escaped\\20 image.png"); }
                .eof { background: url(eof.png); }'''
            record = self.project(root, html)
            sources = {item['path'] for item in record['sources']}
            self.assertTrue({'html/photo.png', 'html/fallback.svg', 'html/escaped image.png', 'html/eof.png'} <= sources)

    def test_encoded_and_safe_parent_paths_and_css_encoding(self):
        tmp, root = self.root()
        with tmp:
            (root / 'html').mkdir()
            page = root / 'html/index.html'
            (root / 'shared.png').write_bytes(b'image')
            (root / 'space photo.png').write_bytes(b'image')
            (root / 'fonts').mkdir()
            (root / 'fonts/Room.woff2').write_bytes(b'font')
            css = root / 'html/site.css'
            css.write_bytes(b'@charset "iso-8859-1"; .x { content: "caf\xe9"; background: url(../shared.png); mask: url(../space%20photo.png); src: url("../fonts/Room.woff2"); }')
            record = self.project(root, '<link rel="stylesheet" href="site.css">')
            sources = {item['path'] for item in record['sources']}
            self.assertIn('shared.png', sources)
            self.assertIn('space photo.png', sources)
            self.assertIn('fonts/Room.woff2', sources)
            self.assertEqual(input_effect._relative_asset(page, root, '../shared.png')['status'], 'present')
            for ref in ('../../../../outside.css', '%2Foutside.css', 'x%5Cfile.png', 'bad%00.png'):
                self.assertEqual(input_effect._relative_asset(css, root, ref)['status'], 'rejected')

    def test_absent_dependencies_and_creation_deletion_are_stale(self):
        tmp, root = self.root()
        with tmp:
            record = self.project(root, '<style>.x { background: url("later.png") }</style>')
            path = root / 'html/later.png'
            self.assertEqual(input_effect.freshness(record, root)['status'], 'current')
            path.write_bytes(b'image')
            self.assertEqual(input_effect.freshness(record, root)['changed'], ['html/later.png'])
            present = self.project(root, '<style>.x { background: url("later.png") }</style>')
            path.unlink()
            self.assertEqual(input_effect.freshness(present, root)['changed'], ['html/later.png'])

    def test_missing_css_parser_is_actionable_and_brief_only_still_works(self):
        tmp, root = self.root()
        with tmp, mock.patch.dict(sys.modules, {'tinycss2': None}):
            with self.assertRaisesRegex(ValueError, 'tinycss2.*requirements-optional'):
                self.project(root, '<style>.x { color: red }</style>')
            brief_only = dict(spec(), inputs={})
            self.assertEqual(input_effect.project(root, brief_only)['status'], 'projected')

    def test_symlink_css_dependency_is_rejected(self):
        tmp, root = self.root()
        with tmp:
            (root / 'html').mkdir()
            external = root.parent / (root.name + '-external.png')
            external.write_bytes(b'image')
            (root / 'html/link.png').symlink_to(external)
            record = self.project(root, '<style>.x { background: url("link.png") }</style>')
            self.assertNotIn('html/link.png', {item['path'] for item in record['sources']})
            external.unlink()


if __name__ == '__main__':
    unittest.main()
