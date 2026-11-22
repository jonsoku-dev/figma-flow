"""Mutate family definitions once and exercise the Python compiler and native workbench on the new values."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FamilyAuthorityTests(unittest.TestCase):
    def test_graph_edits_reach_family_compilation_and_native_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for folder in ('tools','library','figma-bridge','panel-ui/src','examples/owned-component-families'):
                shutil.copytree(ROOT/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__','node_modules','.DS_Store'))
            (root/'tests').mkdir()
            for name in ('nf01_semantic_family_runtime.cjs','semantic_component_reuse_oracle.cjs'):
                shutil.copyfile(ROOT/'tests'/name,root/'tests'/name)
            path=root/'library/component-families.json'
            contract=json.loads(path.read_bytes())
            contract['native']['component'].update(width=283,indicatorSize=23)
            contract['native']['workbench'].update(width=1317,originX=1531)
            contract['tokens']['color']['accent']['$value']='#1e8a61'
            path.write_text(json.dumps(contract))
            project=[sys.executable,'-B',root/'tools/component_family_contract.py']
            self.assertNotEqual(subprocess.run(project,cwd=root).returncode,0)
            subprocess.run([*project,'--write'],cwd=root,check=True)
            subprocess.run(project,cwd=root,check=True)
            node=subprocess.run(['node','--test','--test-name-pattern','^the native family workbench consumes the projected sizing contract$',
                                 'tests/nf01_semantic_family_runtime.cjs'],cwd=root,capture_output=True,text=True)
            self.assertEqual(node.returncode,0,node.stdout+node.stderr)
            probe="""
import json,sys
sys.path.insert(0,'tools')
import design_system
doc=json.load(open('examples/owned-component-families/design.json'))
source={'nodes':[],'edges':[],'componentFamilies':doc['componentFamilies']}
design=design_system._graph_to_family_design(source, source['componentFamilies'])
assert design['tokens']['color']['accent']['$value']=='#1e8a61'
assert design['components']['checkbox']['variants']['checked']['color']=='color.accent'
"""
            result=subprocess.run([sys.executable,'-B','-c',probe],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
