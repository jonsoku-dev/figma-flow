"""The product constitution and every active authoring entry point agree on Design."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import figma_feature
import figma_sdk_project as sdk
import figma_widget_project as widget
from workspace_recipes import design_recipes


class DesignSpecializationTest(unittest.TestCase):
    def test_contract_and_active_authoring_surfaces(self):
        contract = json.loads((ROOT/'specs/design-specialization/graph.json').read_bytes())
        target = next(n for n in contract['nodes'] if n['id'] == 'TARGET-DESIGN')
        self.assertEqual(target['editor_types'], ['figma'])
        self.assertEqual(target['modes'], ['default'])
        self.assertEqual(list(sdk.EDITORS), target['editor_types'])
        for recipe in design_recipes():
            self.assertEqual((recipe['editorType'], recipe.get('mode', 'default')), ('figma', 'default'))
        for row in figma_feature.ROUTES:
            self.assertNotIn(row['id'], {'figjam','slides','buzz','make','weave','sites','dev-codegen'})
            if row['editor']:
                self.assertIn(row['editor'], target['editor_types'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            sdk.initialize(root/'sdk', 'figma')
            widget.initialize(root/'widget')
            for name in ('sdk','widget'):
                manifest = json.loads((root/name/'manifest.template.json').read_bytes())
                self.assertEqual(manifest['editorType'], target['editor_types'])

    def test_a_nonmenu_recipe_cannot_escape_the_catalog_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for editor in ('figjam', 'slides', 'buzz', 'dev'):
                (root/'manifest.json').write_text(json.dumps({'recipes': [
                    {'id':'test','editorType':editor,'mode':'default'}]}))
                with self.assertRaisesRegex(ValueError, 'Design/default'):
                    design_recipes(root)
