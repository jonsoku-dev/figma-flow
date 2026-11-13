import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_sdk_project as sdk


class SDKProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name).resolve()
        self.project = self.parent / 'plugin'

    def tearDown(self):
        self.temp.cleanup()

    def test_no_fabricated_id_and_pinned_source(self):
        sdk.initialize(self.project, 'figma')
        manifest = json.loads((self.project / 'manifest.template.json').read_text())
        self.assertNotIn('id', manifest)
        self.assertFalse((self.project / 'manifest.json').exists())
        self.assertEqual(manifest['editorType'], ['figma'])
        self.assertEqual(manifest['networkAccess'], {'allowedDomains': ['none']})
        self.assertNotIn('permissions', manifest)
        for name in sdk.verify_source()['files']:
            self.assertEqual((self.project / 'vendor' / name).read_bytes(), (sdk.LIBRARY / name).read_bytes())
        self.assertEqual(json.loads((self.project / 'package.json').read_text())['devDependencies'], {'typescript': '5.9.3'})

    def test_existing_path_and_symlink_are_preserved(self):
        self.project.mkdir()
        sentinel = self.project / 'manifest.json'
        sentinel.write_text('registered workspace')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            sdk.initialize(self.project, 'figma')
        self.assertEqual(sentinel.read_text(), 'registered workspace')
        alias = self.parent / 'alias'
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            sdk.initialize(alias / 'new', 'figma')
        self.assertFalse((self.project / 'new').exists())

    def test_modes_and_id_are_explicit(self):
        for editor in ('dev', 'figjam', 'slides', 'buzz', 'not-an-editor'):
            with self.assertRaisesRegex(ValueError, 'supported editor'):
                sdk.initialize(self.project, editor)
        with self.assertRaisesRegex(ValueError, 'Figma Design/default'):
            sdk.initialize(self.project, 'figma', mode='codegen')
        with self.assertRaisesRegex(ValueError, 'numeric ID'):
            sdk.initialize(self.project, 'figma', plugin_id='fake-id')
        sdk.initialize(self.project, 'figma', plugin_id='123456789')
        manifest = json.loads((self.project / 'manifest.json').read_text())
        self.assertEqual(manifest['id'], '123456789')
        self.assertEqual(manifest['editorType'], ['figma'])
        self.assertNotIn('capabilities', manifest)
        self.assertIn("figma.editorType !== 'figma'", (self.project / 'src/code.ts').read_text())

    def test_parent_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'traversal'):
            sdk.initialize(self.parent / '..' / 'unexpected-plugin', 'figma')

    def test_recipe_copies_reviewable_source_and_requires_matching_editor(self):
        recipes = self.parent / 'recipes'
        recipes.mkdir()
        code = "figma.closePlugin('Reviewed local recipe');\n"
        (recipes / 'example.ts').write_text(code)
        (recipes / 'helpers.js').write_text('function reviewedHelper() { return 1; }\n')
        (recipes / 'manifest.json').write_text(json.dumps({'recipes': [
            {'id': 'example', 'entry': 'example.ts', 'editorType': 'other', 'mode': 'default', 'runtimeHelpers': 'helpers.js'}]}))
        with patch.object(sdk, 'RECIPES', recipes):
            with self.assertRaisesRegex(ValueError, 'editor/mode differs'):
                sdk.initialize(self.project, 'figma', recipe='example')
            (recipes / 'manifest.json').write_text(json.dumps({'recipes': [
                {'id': 'example', 'entry': 'example.ts', 'editorType': 'figma', 'mode': 'default', 'runtimeHelpers': 'helpers.js'}]}))
            sdk.initialize(self.project, 'figma', recipe='example')
        self.assertEqual((self.project / 'src/code.ts').read_text(), code)
        self.assertTrue(json.loads((self.project / 'tsconfig.json').read_text())['compilerOptions']['allowJs'])
        (self.project / 'vendor/recipe-runtime.js').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Pinned recipe helpers changed'):
            sdk.compile_project(self.project)

    def test_build_rejects_symlink_output_without_writing(self):
        sdk.initialize(self.project, 'figma')
        outside = self.parent / 'outside.js'
        outside.write_text('preserve')
        (self.project / 'dist').mkdir()
        (self.project / 'dist/code.js').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'Symlink not allowed'):
            sdk.compile_project(self.project, build=True)
        self.assertEqual(outside.read_text(), 'preserve')

    @unittest.skipUnless(os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'), 'Set FIGMA_SDK_TEST_TYPESCRIPT to pinned lib/tsc.js for real compilation')
    def test_real_compiler_all_editors_and_rejects_invalid_api(self):
        compiler = os.environ['FIGMA_SDK_TEST_TYPESCRIPT']
        self.assertEqual(sdk.EDITORS, ('figma',))
        for editor in sdk.EDITORS:
            project = self.parent / editor
            sdk.initialize(project, editor)
            sdk.compile_project(project, build=True, typescript=compiler)
            self.assertTrue((project / 'dist/code.js').is_file())
            self.assertNotIn('declare const', (project / 'dist/code.js').read_text())
        invalid = self.parent / 'figma'
        (invalid / 'src/code.ts').write_text('figma.thisMemberDoesNotExist();\n')
        with self.assertRaisesRegex(ValueError, 'compilation failed'):
            sdk.compile_project(invalid, typescript=compiler)
        (invalid / 'vendor/plugin-api.d.ts').write_text('interface PluginAPI {}\n')
        with self.assertRaisesRegex(ValueError, 'Pinned typings changed'):
            sdk.compile_project(invalid, typescript=compiler)


if __name__ == '__main__':
    unittest.main()
