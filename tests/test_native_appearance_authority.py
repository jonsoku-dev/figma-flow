"""Mutate actual Design board colors, canvas sizing and the approved starter component identity."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class NativeAppearanceTests(unittest.TestCase):
    def test_actual_native_board_and_starter_validator_follow_their_graph_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            files=('tools/native_appearance.py','tools/web-interaction-contract.json','figma-bridge/web_design.js','figma-bridge/presentation.json','figma-bridge/native_graph_review.js',
                   'figma-bridge/native_edit.js','figma-bridge/native_provision.js','figma-bridge/design_note_board.js',
                   'tests/test_native_graph_review.cjs','apps/little-hands/static/littlehands/design-system.manifest.json','apps/little-hands/design/graph.json','apps/little-hands/design/tokens.json')
            files += ('figma-bridge/edit-contract.json','figma-bridge/chat-input.json','library/component-families.json')
            modules=json.loads((ROOT/'figma-bridge/presentation.json').read_bytes())['modules']
            for name in {*files, *(m['source'] for m in modules.values())}:
                (root/name).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,root/name)
            src=root/'figma-bridge/presentation.json'
            record=json.loads(src.read_bytes())
            fields=record['modules']['graphReview']['fields']
            fields['card']['width']=288
            fields['groups']['requirement']['fill']={'r':0.52,'g':0.46,'b':0.3}
            src.write_text(json.dumps(record))
            p=root/'apps/little-hands/design/graph.json'
            d=json.loads(p.read_bytes())
            d['design_system']['components']['button.bookingCTA']['native']['mainKeys']=['changed-main']
            p.write_text(json.dumps(d))
            cmd=[sys.executable,'-B','tools/native_appearance.py']
            self.assertNotEqual(subprocess.run(cmd,cwd=root,capture_output=True).returncode,0)
            subprocess.run([*cmd,'--write'],cwd=root,check=True)
            subprocess.run(cmd,cwd=root,check=True)
            result=subprocess.run(['node','--test','--test-name-pattern','^graph-owned card sizing and paint reach Figma and an old appearance stamp requests refresh$',
                                   'tests/test_native_graph_review.cjs'],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            probe="""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const ctx=vm.createContext({});
vm.runInContext(fs.readFileSync('figma-bridge/native_provision.js','utf8'),ctx);
const validate=vm.runInContext('nativeProvisionValidate',ctx);
const seed={schema:'figma-flow-starter-cta-provision-v1',graph_sha256:'a'.repeat(64),
 frame_key:'little-hands/booking-cta/starter-frame',main_key:'bookingCTA',instance_keys:['reserve-preview','reserve-login'],
 seed_collection_name:'Little Hands · CTA SSOT seed',seed_variable_name:'starter/little-hands/booking-cta-seed',
 canonical_variable_name:'ssot/little-hands/color/action/primary',page_roots:[],position:{x:1,y:2}};
assert.throws(()=>validate({provision:seed}),/Invalid or stale/);
validate({provision:{...seed, main_key:'changed-main'}});
"""
            subprocess.run(['node','-e',probe],cwd=root,check=True,capture_output=True,timeout=15)


if __name__=='__main__':
    unittest.main()
