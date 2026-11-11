"""Native mutation preparation is data-only and preserves exact plan pins."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import native_edit

def plan():return {'schema':'figma-flow-native-edit-plan-v1','file_key':'file','page_id':'1:1','edits':[{'node_id':'2:1','field':'paddingLeft','before':16,'after':24}]}
class NativeEditPlan(unittest.TestCase):
    def test_prepare_has_exact_data_nonce_scoped_getter_and_network_disabled(self):
        with tempfile.TemporaryDirectory()as folder:
            source=Path(folder)/'plan.json';raw=(json.dumps(plan())+'\n').encode();source.write_bytes(raw)
            out=Path(folder)/'plugin';receipt=native_edit.prepare(source,out,'123456789')
            self.assertEqual(receipt['plan_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual((out/'native-edit-plan.json').read_bytes(),raw)
            manifest=json.loads((out/'manifest.json').read_text());self.assertEqual(manifest['networkAccess']['allowedDomains'],['none']);self.assertEqual(manifest['id'],'123456789')
            code=(out/'code.js').read_text();self.assertIn('readNativeSemantics',code);self.assertIn('figma-flow-graph-native-discovery-v1',code);self.assertIn('NATIVE_EDIT_SESSION',code)
            self.assertEqual(subprocess.run(['node','--check',str(out/'code.js')],capture_output=True).returncode,0)
            with self.assertRaises(FileExistsError):native_edit.prepare(source,out)
    def test_unsupported_scope_and_values_never_prepare(self):
        for mutate in [lambda p:p.update(file_key='bad/host'),lambda p:p['edits'][0].update(field='characters'),lambda p:p['edits'][0].update(after=-1),lambda p:p['edits'].append(copy.deepcopy(p['edits'][0])),lambda p:p.update(script='arbitrary()')]:
            data=plan();mutate(data)
            with self.subTest(data=data),self.assertRaises(ValueError):native_edit.validate_plan(data)
        data=plan();data['edits']=[dict(node_id='3:1',field='fontSize',before=14,after=18)]
        with self.assertRaises(ValueError):native_edit.validate_plan(data)
        data['edits'][0]['main_id']='2:1';native_edit.validate_plan(data)
        data['edits'].append(dict(node_id='3:1',main_id='2:1',field='fontFamily',before='Inter',after='Other'))
        with self.assertRaises(ValueError):native_edit.validate_plan(data)
    def test_existing_variable_value_is_typed_and_alias_rewrites_are_not_admitted(self):
        data=plan();data.pop('edits');data['variableedit']=dict(variable_id='VariableID:1:1',mode_id='1:0',before=14,after=18);native_edit.validate_plan(data)
        for after in [{'type':'VARIABLE_ALIAS','id':'other'},True,'Other',{'r':0,'g':0,'b':0,'a':0.5}]:
            bad=copy.deepcopy(data);bad['variableedit']['after']=after
            with self.subTest(after=after),self.assertRaises(ValueError):native_edit.validate_plan(bad)
if __name__=='__main__':unittest.main()
