"""Input-effect gates for the regression program.

These checks fail when a declared local input is omitted from the projection.
They do not claim a browser render, a visual review, or a Figma read.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/regression-program'
sys.path.insert(0, str(ROOT / 'tools'))
import input_effect


def load_catalog():
    spec = importlib.util.spec_from_file_location('regression_catalog', FIXTURE / 'catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_for(app, inputs, authority=None):
    return {
        'schema': input_effect.SCHEMA,
        'brief': f'{app}/brief.md',
        'facts': f'{app}/brief-facts.json',
        'authority': authority or f'{app}/authority.json',
        'expected_package_version': '0.1.0',
        'inputs': inputs,
    }


def decision(record, fact):
    found = [item for item in record['decisions'] if item['fact'] == fact]
    return found[0] if found else None


class InputEffectTests(unittest.TestCase):
    def setUp(self):
        self.expectations = json.loads((FIXTURE / 'expectations.json').read_text())

    def project(self, app, inputs, authority=None, root=FIXTURE):
        return input_effect.project(root, spec_for(app, inputs, authority))

    def linked_root(self, root):
        shutil.copytree(FIXTURE / 'atlas', root / 'atlas')
        shutil.copytree(FIXTURE / 'html/atlas/linked', root / 'html/atlas/linked')
        index = root / 'html/atlas/linked/index.html'
        index.write_text(index.read_text(encoding='utf-8').replace('</head>', '  <script src="app.js"></script>\n</head>'), encoding='utf-8')
        (root / 'html/atlas/linked/app.js').write_text('window.version = 1;', encoding='utf-8')

    def test_pinned_expectations_match_html_and_brief_bytes(self):
        for app, expected in self.expectations['apps'].items():
            html = (FIXTURE / 'html' / app / 'self-contained.html').read_text(encoding='utf-8')
            brief = (FIXTURE / app / 'brief.md').read_text(encoding='utf-8')
            self.assertIn(f'<title>{expected["html_title"]}</title>', html)
            self.assertIn(f'gap: {expected["html_gap"]}', html)
            self.assertIn(expected['brief_title'], brief)
            self.assertIn(expected['brief_gap'], brief)
            self.assertNotIn(expected['html_title'], brief)

    def test_removing_html_changes_the_pinned_title(self):
        for app, expected in self.expectations['apps'].items():
            included = self.project(app, {'html': f'html/{app}/self-contained.html'})
            removed = self.project(app, {})
            self.assertNotEqual(included['digest'], removed['digest'])
            self.assertEqual(decision(included, 'screen-title')['value'], expected['html_title'])
            self.assertEqual(decision(included, 'screen-title')['source'], 'html')
            self.assertEqual(decision(removed, 'screen-title')['value'], expected['brief_title'])
            self.assertEqual(decision(removed, 'screen-title')['source'], 'brief')
            self.assertIn(included['consumption']['html']['sha256'], json.dumps(included['digest_material']))
            self.assertNotIn('html', removed['consumption'])
            self.assertEqual(included['visual_quality'], 'unverified')

    def test_removing_url_drops_the_principle_without_claiming_a_render(self):
        for app, expected in self.expectations['apps'].items():
            included = self.project(app, {'url': f'url/{app}.snapshot.json'})
            removed = self.project(app, {})
            self.assertEqual(decision(included, 'reference-principle')['value'], expected['principle'])
            self.assertIsNone(decision(removed, 'reference-principle'))
            self.assertFalse(included['reference_complete'])
            self.assertFalse(included['channels']['url']['reference_complete'])
            self.assertIn('browser render', included['channels']['url']['observation_limit'])
            self.assertNotEqual(included['digest'], removed['digest'])

    def test_removing_design_system_drops_components_and_brand(self):
        for app, expected in self.expectations['apps'].items():
            included = self.project(app, {'design-system': 'design-system/design.json'})
            removed = self.project(app, {})
            chosen = decision(included, 'component-set')
            self.assertIn('button', chosen['value'])
            self.assertIn('dialog', chosen['value'])
            self.assertEqual(decision(included, 'brand-token')['value'], expected['brand'])
            self.assertIsNone(decision(removed, 'component-set'))
            self.assertEqual(included['channels']['design-system']['tsx_execution'], 'not-run')
            self.assertTrue(included['channels']['design-system']['runtime_checked'])
            self.assertNotEqual(included['digest'], removed['digest'])

    def test_mixed_inputs_change_when_each_source_is_removed(self):
        inputs = {
            'html': 'html/atlas/self-contained.html',
            'url': 'url/atlas.snapshot.json',
            'design-system': 'design-system/design.json',
        }
        full = self.project('atlas', inputs)
        self.assertEqual(full['status'], 'projected')
        for name in inputs:
            reduced = dict(inputs)
            reduced.pop(name)
            other = self.project('atlas', reduced)
            self.assertNotEqual(full['digest'], other['digest'])
            self.assertNotIn(name, other['consumption'])

    def test_unresolved_gap_is_visible_and_has_no_winner(self):
        record = self.project('atlas', {
            'html': 'html/atlas/self-contained.html',
            'design-system': 'design-system/design.json',
        }, authority='atlas/authority-unresolved.json')
        self.assertEqual(record['status'], 'blocked')
        blocked = next(item for item in record['blocked'] if item['fact'] == 'surface-gap')
        self.assertEqual(blocked['values']['html'], '12px')
        self.assertEqual(blocked['values']['design-system'], '8px')
        self.assertEqual(blocked['values']['brief'], '8px')
        self.assertIsNone(decision(record, 'surface-gap'))

    def test_explicit_priority_keeps_the_rejected_gap(self):
        record = self.project('atlas', {
            'html': 'html/atlas/self-contained.html',
            'design-system': 'design-system/design.json',
        })
        chosen = decision(record, 'surface-gap')
        self.assertEqual(chosen['source'], 'brief')
        self.assertEqual(chosen['value'], '8px')
        self.assertEqual(chosen['rejected']['html'], '12px')

    def test_material_instructions_do_not_become_authority(self):
        record = self.project('atlas', {'html': 'html/atlas/self-contained.html'})
        self.assertTrue(record['quarantine'])
        blob = json.dumps(record['decisions'], ensure_ascii=False)
        self.assertNotIn('ignore previous instructions', blob)
        self.assertNotIn('overwrite brief.md', blob)

    def test_linked_css_is_consumed_and_missing_assets_stay_404(self):
        record = self.project('atlas', {'html': 'html/atlas/linked/index.html'})
        assets = {item['ref']: item['status'] for item in record['channels']['html']['assets']}
        self.assertEqual(assets['page.css'], 'present')
        self.assertEqual(assets['mark.svg'], 'present')
        self.assertEqual(assets['photo.png'], '404')
        self.assertEqual(assets['fonts/Room.woff2'], '404')
        self.assertEqual(record['channels']['html']['facts']['surface-gap'], '12px')
        self.assertEqual(record['channels']['html']['render'], 'unverified')

    def test_real_photo_font_fixture_has_pinned_present_sources(self):
        fixture = FIXTURE / 'html/positive-assets'
        provenance = json.loads((fixture / 'sources.json').read_text(encoding='utf-8'))
        record = self.project('atlas', {'html': 'html/positive-assets/index.html'})
        self.assertTrue(all(asset['status'] == 'present' for asset in record['channels']['html']['assets']))
        sources = {item['path']: item['sha256'] for item in record['sources']}
        for kind in ('photo', 'font'):
            asset = provenance[kind]
            self.assertEqual(sources['html/positive-assets/' + asset['path']], asset['sha256'])
        self.assertTrue((fixture / provenance['photo']['path']).read_bytes().startswith(b'\xff\xd8\xff'))
        self.assertTrue((fixture / provenance['font']['path']).read_bytes().startswith(b'wOF2'))
        self.assertEqual(input_effect.freshness(record, FIXTURE)['status'], 'current')

    def test_linked_sources_are_part_of_freshness_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.linked_root(root)
            html = 'html/atlas/linked/index.html'
            assets = ('page.css', 'mark.svg', 'photo.png', 'fonts/Room.woff2', 'app.js')
            for asset in assets:
                with self.subTest(asset=asset):
                    path = root / 'html/atlas/linked' / asset
                    path.parent.mkdir(parents=True, exist_ok=True)
                    before = path.read_bytes() if path.is_file() else b'initial'
                    path.write_bytes(before)
                    record = self.project('atlas', {'html': html}, root=root)
                    self.assertEqual(input_effect.freshness(record, root)['status'], 'current')
                    path.write_bytes(before.replace(b'12px', b'28px') if asset == 'page.css' else before + b'changed')
                    self.assertEqual(input_effect.freshness(record, root)['changed'], [f'html/atlas/linked/{asset}'])
                    latest = self.project('atlas', {'html': html}, root=root)
                    self.assertNotEqual(latest['digest'], record['digest'])
                    if asset == 'page.css':
                        self.assertEqual(latest['channels']['html']['facts']['surface-gap'], '28px')

    def test_missing_direct_source_creation_and_deletion_are_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.linked_root(root)
            html = 'html/atlas/linked/index.html'
            photo = root / 'html/atlas/linked/photo.png'
            absent = self.project('atlas', {'html': html}, root=root)
            self.assertEqual(input_effect.freshness(absent, root)['status'], 'current')
            photo.write_bytes(b'created')
            self.assertEqual(input_effect.freshness(absent, root)['changed'], ['html/atlas/linked/photo.png'])
            present = self.project('atlas', {'html': html}, root=root)
            photo.unlink()
            self.assertEqual(input_effect.freshness(present, root)['changed'], ['html/atlas/linked/photo.png'])

    def test_local_reference_queries_and_fragments_track_underlying_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.linked_root(root)
            html = 'html/atlas/linked/index.html'
            index = root / html
            index.write_text(index.read_text(encoding='utf-8').replace('page.css"', 'page.css?v=1"').replace('mark.svg"', 'mark.svg#logo"').replace('app.js"', 'app%20bundle.js?v=1#module"'), encoding='utf-8')
            (index.parent / 'app.js').rename(index.parent / 'app bundle.js')
            record = self.project('atlas', {'html': html}, root=root)
            assets = {item['ref']: item for item in record['channels']['html']['assets']}
            sources = {item['path']: item['sha256'] for item in record['sources']}
            for ref, name in (('page.css?v=1', 'page.css'), ('mark.svg#logo', 'mark.svg'), ('app%20bundle.js?v=1#module', 'app bundle.js')):
                with self.subTest(ref=ref):
                    self.assertEqual(assets[ref]['status'], 'present')
                    self.assertEqual(sources[f'html/atlas/linked/{name}'], input_effect.digest((index.parent / name).read_bytes()))
            self.assertEqual(record['channels']['html']['facts'].get('surface-gap'), '12px')
            css = index.parent / 'page.css'
            css.write_text(css.read_text(encoding='utf-8').replace('12px', '28px'), encoding='utf-8')
            self.assertEqual(input_effect.freshness(record, root)['changed'], ['html/atlas/linked/page.css'])
            self.assertEqual(self.project('atlas', {'html': html}, root=root)['channels']['html']['facts']['surface-gap'], '28px')

    def test_encoded_local_references_cannot_escape_the_fixture(self):
        index = FIXTURE / 'html/atlas/linked/index.html'
        for ref in ('%2e%2e/outside.css', '%2Foutside.css', 'fonts%5Cfile.woff2', 'bad%00.js'):
            with self.subTest(ref=ref):
                asset = input_effect._relative_asset(index, FIXTURE, ref)
                self.assertEqual(asset['status'], 'rejected')
                self.assertNotIn('path', asset)
        for ref in ('https://example.com/app.js?v=1', '//example.com/app.js', 'data:text/javascript,1'):
            with self.subTest(ref=ref):
                self.assertEqual(input_effect._relative_asset(index, FIXTURE, ref)['status'], 'external-unverified')

    def test_legacy_result_requires_regeneration_and_optional_locate_stays_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.linked_root(root)
            record = self.project('atlas', {'html': 'html/atlas/linked/index.html'}, root=root)
            legacy = dict(record, schema='figma-flow-input-effect-result-v1')
            with self.assertRaisesRegex(ValueError, 'regenerate'):
                input_effect.freshness(legacy, root)
            with self.assertRaisesRegex(ValueError, 'not a file'):
                input_effect.locate(root, 'html/atlas/linked/missing.png')
            (root / 'html/atlas/linked/fonts').mkdir()
            directory = input_effect.locate(root, 'html/atlas/linked/fonts', require_file=False)
            self.assertTrue(directory.is_dir())
            self.assertFalse(input_effect.locate(root, 'html/atlas/linked/missing.png', require_file=False).exists())
            (root / 'html/atlas/linked/symlink.png').symlink_to(root / 'html/atlas/linked/mark.svg')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                input_effect.locate(root, 'html/atlas/linked/symlink.png', require_file=False)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                input_effect.locate(root, '../outside.png', require_file=False)

    def test_js_fixture_html_does_not_contain_the_runtime_phrase(self):
        for app, phrase in (('atlas', 'JS로 만든 승인 큐'), ('morrow', 'JS로 만든 상품 진열'), ('paper', 'JS로 만든 초고 본문')):
            html = (FIXTURE / 'html' / app / 'js/index.html').read_text(encoding='utf-8')
            script = (FIXTURE / 'html' / app / 'js/render.js').read_text(encoding='utf-8')
            self.assertNotIn(phrase, html)
            self.assertIn(phrase, script)

    def test_failure_snapshots_do_not_invent_a_body(self):
        for name in ('redirect', 'login-required', 'not-found', 'rate-limited'):
            record = self.project('atlas', {'url': f'url/controlled-{name}.snapshot.json'})
            channel = record['channels']['url']
            self.assertEqual(channel['principles'], [])
            self.assertFalse(channel['reference_complete'])
            self.assertIn(name if name != 'login-required' else 'login-required', channel['render_status'])
        material = self.project('atlas', {'url': 'url/material.snapshot.json'})
        self.assertEqual(material['channels']['url']['render_status'], 'js-required')
        self.assertFalse(material['reference_complete'])
        self.assertIsNone(decision(material, 'reference-principle'))

    def test_atlas_reference_conflict_keeps_exclusions(self):
        record = self.project('atlas', {'url': 'url/atlas.snapshot.json'})
        self.assertIn('carbon-xs-density', decision(record, 'excluded-principle')['value'])
        self.assertIn('material-drawer', decision(record, 'excluded-principle')['value'])
        self.assertEqual(decision(record, 'reference-principle')['value'], 'atlas-check-answers')

    def test_unsupported_axes_are_reported(self):
        record = self.project('atlas', {'design-system': 'design-system/design.json'})
        axes = {item['axis'] for item in record['channels']['design-system']['unsupported_axes']}
        self.assertEqual(axes, {'mode', 'brand-theme'})

    def test_symlink_escape_and_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURE / 'atlas', root / 'atlas')
            real = root / 'note.html'
            real.write_text('<title>노트</title><style>main{gap:12px}</style>', encoding='utf-8')
            (root / 'linked.html').symlink_to(real)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.project('atlas', {'html': 'linked.html'}, root=root)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                self.project('atlas', {'html': '../outside.html'}, root=root)
            record = self.project('atlas', {}, root=root)
            (root / 'out').mkdir()
            input_effect.write_record(root, record, 'out/result.json')
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                input_effect.write_record(root, record, 'out/result.json')

    def test_bad_tokens_are_rejected_and_a_changed_source_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURE / 'atlas', root / 'atlas')
            cyclic = {
                'version': 1,
                'tokens': {'color': {
                    'brand': {'$type': 'color', '$value': '{color.ink}'},
                    'ink': {'$type': 'color', '$value': '{color.brand}'},
                }},
            }
            (root / 'cyclic.json').write_text(json.dumps(cyclic), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'cyclic alias'):
                self.project('atlas', {'design-system': 'cyclic.json'}, root=root)
            (root / 'cyclic.json').write_text(json.dumps({'version': 2}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'version must be 1'):
                self.project('atlas', {'design-system': 'cyclic.json'}, root=root)
            record = self.project('atlas', {'html': 'atlas/../atlas/brief.md'.replace('atlas/../', '')}, root=root)
            target = root / 'atlas/brief.md'
            target.write_text(target.read_text(encoding='utf-8') + '\n', encoding='utf-8')
            fresh = input_effect.freshness(record, root)
            self.assertEqual(fresh['status'], 'stale')
            self.assertIn('atlas/brief.md', fresh['changed'])

    def test_catalog_routes_match_the_case_inventory(self):
        catalog = load_catalog()
        cases = json.loads((ROOT / 'specs/regression-program/cases.json').read_text())
        for case_app in cases['apps']:
            routes = catalog.APPS[case_app['id']]['routes']
            self.assertEqual([(item['id'], item['path']) for item in routes], [(item['id'], item['path']) for item in case_app['routes']])
            self.assertEqual(len(case_app['core_routes']), 5)


if __name__ == '__main__':
    unittest.main()
