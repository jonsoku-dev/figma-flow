import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import workspace_recipes as recipes


class WorkspaceRecipeTest(unittest.TestCase):
    def test_only_static_design_actions_are_in_menu(self):
        entries = recipes.menu()[1]['menu']
        self.assertEqual({entry['command'] for entry in entries}, {
            'flow-recipe:design-shapes', 'flow-recipe:design-grid', 'flow-recipe:design-motion',
            'flow-recipe:design-component-properties'})
        self.assertEqual(set(recipes.bundled_actions()), set(recipes.ACTIONS))

    def test_changed_source_or_javascript_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve() / 'recipes'
            shutil.copytree(recipes.LIBRARY, folder)
            with patch.object(recipes, 'LIBRARY', folder):
                target = folder / 'bundled/design-grid.js'
                target.write_text(target.read_text() + '\nthrow Error("tampered");')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    recipes.dispatch_source()

    def test_runtime_publication_uses_pins_while_explicit_ci_checks_only_helper_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / 'figma-bridge').mkdir()
            helpers = (recipes.LIBRARY / 'component-properties.helpers.js').read_text()
            production = root / 'figma-bridge/code.js'
            production.write_text(helpers + '\nfunction unrelatedImporter() { return 1; }\n')
            with patch.object(recipes, 'ROOT', root):
                recipes.verify_production_helpers()
                production.write_text(production.read_text().replace('return 1;', 'return 2;'))
                recipes.verify_production_helpers()
                source = production.read_text()
                offset = source.index('{', source.index('function metadata(')) + 1
                production.write_text(source[:offset] + '/* helper drift */' + source[offset:])
                self.assertEqual(set(recipes.bundled_actions()), set(recipes.ACTIONS))
                with self.assertRaisesRegex(ValueError, 'Required production helpers changed'):
                    recipes.verify_production_helpers()

    def test_inventory_npm_install_outputs_do_not_change_native_runtime_identity(self):
        import figma_workspace as workspace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bridge = root / 'figma-bridge'
            bridge.mkdir()
            for name in workspace.runtime_module_names():
                (bridge / name).write_text('// runtime module\n')
            (root / 'tools').mkdir()
            (root / 'tools/compiler.py').write_text('# generator\n')
            library = root / 'library/figma-api'
            library.mkdir(parents=True)
            (library / 'package.json').write_text('{"devDependencies":{"typescript":"5.9.3"}}')
            generator = library / 'generate.cjs'
            generator.write_text('// AST generator\n')
            recipe = root / 'library/figma-recipes'
            (recipe / 'bundled').mkdir(parents=True)
            (recipe / 'design-grid.ts').write_text('// authored recipe\n')
            (recipe / 'bundled/design-grid.js').write_text('// compiled recipe\n')
            with patch.object(workspace, 'ROOT', root):
                before = workspace.trusted_sources()
                installed = library / 'node_modules/typescript/lib'
                installed.mkdir(parents=True)
                (installed / 'tsc.js').write_text('// installed compiler\n')
                (library / 'package-lock.json').write_text('{"lockfileVersion":3}')
                cache = library / '.cache'
                cache.mkdir()
                (cache / 'tool.json').write_text('{"mutable":true}')
                self.assertEqual(workspace.trusted_sources(), before)
                for path in [generator, recipe / 'design-grid.ts', recipe / 'bundled/design-grid.js']:
                    original = path.read_text()
                    path.write_text(original + '// actual input changed\n')
                    self.assertNotEqual(workspace.trusted_sources(), before)
                    path.write_text(original)

    @unittest.skipUnless(os.environ.get('FIGMA_SDK_TEST_TYPESCRIPT'), 'Set FIGMA_SDK_TEST_TYPESCRIPT for independent bundle regeneration')
    def test_bundled_javascript_matches_real_pinned_compiler(self):
        import figma_sdk_project as sdk
        with tempfile.TemporaryDirectory() as temporary:
            for key in recipes.ACTIONS:
                project = Path(temporary).resolve() / key
                sdk.initialize(project, 'figma', recipe=key)
                sdk.compile_project(project, build=True, typescript=os.environ['FIGMA_SDK_TEST_TYPESCRIPT'])
                self.assertEqual((project / 'dist/code.js').read_bytes(),
                                 (recipes.LIBRARY / 'bundled' / (key + '.js')).read_bytes())

    def test_native_dispatch_requires_confirmation_and_never_enters_task_host(self):
        source = recipes.dispatch_source()
        script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = SOURCE;
async function harness(command, editor='figma', mode='default', confirm=false) {
  let writes=0, host=0, shown=0, closes=0;
  const figma={command,editorType:editor,mode,ui:{},
    showUI(html){shown++;assert.match(html,/Add example to current page/);},
    closePlugin(){closes++;},
    currentPage:{id:'1:2',selection:[],children:[],appendChild(){}},
    createPage(){throw Error('Recipes must preserve the current page');},
    createFrame(){writes++;return {resize(){},appendChild(){}};},createRectangle(){return {resize(){}};},
    viewport:{scrollAndZoomIntoView(){}},
  };
  const context=vm.createContext({figma,probe:{startHost(){host++;}}});
  vm.runInContext(source+'\nif(!workspaceRecipeDispatch()){probe.startHost();}',context);
  assert.equal(writes,0);
  if(confirm){
    figma.ui.onmessage({type:'apply',recipe:'design-grid',code:'arbitrary'});
    figma.ui.onmessage({type:'workspace-recipe-run',recipe:'design-motion'});
    assert.equal(writes,0);
    figma.ui.onmessage({type:'workspace-recipe-run',recipe:'design-grid'});
    figma.ui.onmessage({type:'workspace-recipe-run',recipe:'design-grid'});
    await new Promise(resolve=>setImmediate(resolve));
  }
  return {writes,host,shown,closes,figma};
}
(async()=>{
  const ordinary=await harness('workspace-home');assert.equal(ordinary.host,1);
  const pending=await harness('flow-recipe:design-grid');
  assert.equal(pending.shown,1);assert.equal(pending.host,0);
  pending.figma.ui.onmessage({type:'workspace-recipe-cancel'});assert.equal(pending.writes,0);
  const run=await harness('flow-recipe:design-grid','figma','default',true);
  assert.equal(run.writes,1);assert.equal(run.host,0);assert.equal(run.closes,1);
  for(const [command,editor,mode] of [
    ['flow-recipe:design-grid','figjam','default'],
    ['flow-recipe:design-grid','figma','inspect'],
    ['flow-recipe:__proto__','figma','default'],
    ['flow-recipe:dev-codegen','figma','default'],
  ]){const denied=await harness(command,editor,mode);assert.equal(denied.writes,0);assert.equal(denied.host,0);assert.equal(denied.shown,0);assert.equal(denied.closes,1);}
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('SOURCE', json.dumps(source))
        result = subprocess.run(['node'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
