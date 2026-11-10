import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'tools'))
from apply_figma_change import run
from design_system import compile_design
from test_sync_figma_tokens import fixture_export


class ChangeWorkflowTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = self.root/'cards'
        shutil.copytree(ROOT/'examples/review-cards', self.app)
        model = compile_design(json.loads((self.app/'design.json').read_text()))
        self.resolved = self.root/'resolved.json'
        self.resolved.write_text(json.dumps(model))
        before = fixture_export(model,hashlib.sha256(self.resolved.read_bytes()).hexdigest())
        after = copy.deepcopy(before)
        var = next(v for v in after['variables'] if v['semantic_id']=='palette.blue')
        var['valuesByMode']['default']={'r':0,'g':1,'b':0,'a':1}
        self.before, self.after = self.root/'before.json', self.root/'after.json'
        self.before.write_text(json.dumps(before)); self.after.write_text(json.dumps(after))

    def changes(self, folder, apply=False):
        return run(self.app,self.resolved,self.before,self.after,'main:page',self.root/folder, apply)

    def test_plan_apply_and_chain(self):
        design = self.app/'design.json'
        before = design.read_bytes()
        planned = self.changes('plan')
        self.assertEqual(planned['status'],'planned')
        self.assertEqual(design.read_bytes(),before)
        self.assertEqual(set(planned['planned_files']),{'design.json','app/tokens.css'})
        self.assertEqual(self.changes('apply',True)['status'],'applied')
        self.assertIn('--palette-blue: #00ff00;', (self.app/'app/tokens.css').read_text())
        verified = run(self.app,self.resolved,self.after,self.after,'main:page',self.root/'recheck',prior_sync=self.root/'apply')
        self.assertEqual(verified['planned_files'],[])

    def test_stale_generated_css_preserves_both_inputs(self):
        design = self.app/'design.json'; before=design.read_bytes()
        css = self.app/'app/tokens.css'; css.write_text(css.read_text()+'/* keep my work */')
        with self.assertRaises(ValueError):
            self.changes('drift',True)
        self.assertEqual(design.read_bytes(),before)
        self.assertTrue(css.read_text().endswith('/* keep my work */'))
