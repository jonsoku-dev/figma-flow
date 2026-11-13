"""Widget scaffolding and compilation are separate from native acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_widget_project as widget


class WidgetProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'widget'

    def tearDown(self):
        self.temp.cleanup()

    def test_separate_widget_manifest_without_fabricated_id_and_pinned_sources(self):
        result = widget.initialize(self.project)
        self.assertEqual(result['runtime'], 'not-executed')
        manifest = json.loads((self.project / 'manifest.template.json').read_text())
        self.assertNotIn('id', manifest)
        self.assertFalse((self.project / 'manifest.json').exists())
        self.assertTrue(manifest['containsWidget'])
        self.assertEqual(manifest['widgetApi'], '1.0.0')
        self.assertEqual(manifest['editorType'], ['figma', 'figjam'])
        self.assertEqual(manifest['networkAccess'], {'allowedDomains': ['none']})
        self.assertNotIn('enablePrivatePluginApi', manifest)
        for folder, library, source in [('widget', widget.LIBRARY, widget.verify_source()),
                                         ('plugin', widget.plugin_api.LIBRARY, widget.plugin_api.verify_source())]:
            for name in source['files']:
                self.assertEqual((self.project / 'vendor' / folder / name).read_bytes(), (library / name).read_bytes())
        self.assertIn('useSyncedState<number>', (self.project / 'src/code.tsx').read_text())
        self.assertIn('AutoLayout', (self.project / 'src/code.tsx').read_text())

    def test_id_existing_directory_and_symlinks(self):
        with self.assertRaisesRegex(ValueError, 'numeric widget ID'):
            widget.initialize(self.project, 'not-issued')
        widget.initialize(self.project, '123456789')
        self.assertEqual(json.loads((self.project / 'manifest.json').read_text())['id'], '123456789')
        before = (self.project / 'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            widget.initialize(self.project)
        self.assertEqual((self.project / 'manifest.json').read_bytes(), before)
        alias = self.root / 'alias'
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            widget.initialize(alias / 'new')

    def test_search_is_offline_and_links_exact_pinned_source(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            result = widget.search('useSyncedState', 0)
        self.assertGreater(result['total'], 0)
        self.assertTrue(any('useSyncedState<T>' in row['text'] or 'useSyncedState<' in row['text']
                            for row in result['rows']))
        for row in result['rows']:
            self.assertIn(widget.verify_source()['ref'], row['source_url'])
            self.assertEqual((widget.LIBRARY / row['file']).read_text().splitlines()[row['line'] - 1], row['text'])

    def test_changed_typings_and_symlink_output_are_rejected(self):
        widget.initialize(self.project)
        source = self.project / 'vendor/widget/widget-api.d.ts'
        original = source.read_bytes()
        source.write_text('interface WidgetAPI {}')
        with self.assertRaisesRegex(ValueError, 'Pinned widget source changed'):
            widget.compile_project(self.project)
        source.write_bytes(original)
        outside = self.root / 'outside.js'
        outside.write_text('preserve')
        (self.project / 'dist').mkdir()
        (self.project / 'dist/code.js').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'Symlink not allowed'):
            widget.compile_project(self.project, build=True)
        self.assertEqual(outside.read_text(), 'preserve')

    def test_cli_verify_search_without_site_packages(self):
        for args in [('verify',), ('search', 'AutoLayout', '--limit', '2')]:
            result = subprocess.run([sys.executable, '-S', str(ROOT / 'tools/figma_widget_project.py'), *args],
                                    capture_output=True, text=True, check=True)
            self.assertIsInstance(json.loads(result.stdout), dict)

    @unittest.skipUnless(os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'), 'Set FIGMA_SDK_TEST_TYPESCRIPT to trusted 5.9.3 lib/tsc.js')
    def test_real_compiler_counter_and_invalid_widget_api(self):
        compiler = os.environ['FIGMA_SDK_TEST_TYPESCRIPT']
        widget.initialize(self.project)
        self.assertEqual(widget.compile_project(self.project, typescript=compiler)['status'], 'typechecked')
        widget.compile_project(self.project, build=True, typescript=compiler)
        code = (self.project / 'dist/code.js').read_text()
        self.assertIn('figma.widget.h(AutoLayout', code)
        self.assertNotIn('declare const', code)
        # The documented npm scripts use this same tsconfig, independent of our CLI flags.
        subprocess.run(['node', compiler, '-p', str(self.project), '--noEmit'], check=True)
        script = '''const vm=require('node:vm'),assert=require('node:assert/strict');
let registered, count=0;
const widget={register(fn){registered=fn;},AutoLayout:'AutoLayout',Text:'Text',
  h(type,props,...children){return {type,props,children};},
  useSyncedState(key,initial){assert.equal(key,'count');assert.equal(initial,0);
    return [count,update=>{count=typeof update==='function'?update(count):update;}];}};
vm.runInNewContext(SOURCE,{figma:{widget}});
const first=registered();assert.equal(first.type,'AutoLayout');
first.props.onClick();first.props.onClick();assert.equal(count,2);
const second=registered();assert.equal(second.children[1].children[0],2);
'''.replace('SOURCE', json.dumps(code))
        subprocess.run(['node'], input=script, text=True, check=True)
        (self.project / 'src/code.tsx').write_text('figma.widget.noSuchWidgetMember();\n')
        with self.assertRaisesRegex(ValueError, 'compilation failed'):
            widget.compile_project(self.project, typescript=compiler)


if __name__ == '__main__':
    unittest.main()
