"""Cached fixture evidence only; no actual native acceptance claim."""
import copy
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import specifications as api
import native_edit
from test_specification_contract import fixture


def readback():
    return {'fileKey':'file','pageId':'1:1','page_owner':'b'*64,'nodes':[
        {'id':'1:1','type':'PAGE'},
        {'id':'2:1','parentId':'1:1','type':'FRAME','name':'Deliver','semanticKey':'full.deliver','annotations':[{'label':'user note'},{'label':'[figma-flow:full.deliver] Legacy original','properties':[{'type':'width'}]}]},
        {'id':'3:1','parentId':'1:1','type':'FRAME','semanticKey':'design-note-board','layoutMode':'VERTICAL','itemSpacing':24,'designNoteBoard':{'pageId':'1:1','sourceHash':'b'*64}},
        {'id':'4:1','parentId':'3:1','type':'TEXT','fontSize':17,'semanticKey':'design-note-board:title','characters':'설명','hyperlink':None,'fontName':{'family':'Explicit','style':'Regular'}},
        {'id':'5:1','parentId':'3:1','type':'TEXT','fontSize':17,'semanticKey':'design-note-board:viewport|state|control','characters':'Legacy original','hyperlink':{'type':'NODE','value':'2:1'},'fontName':{'family':'Explicit','style':'Regular'}}]}


class SpecificationUpdate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'graph.json';self.path.write_text(json.dumps(fixture()))
        self.raw=readback();self.note=api.compile_graph(self.path)[2][1]['id']
    def plan(self):return api.plan(self.path,self.raw,[self.note+'=full.deliver'])
    def after(self,plan):
        actual=copy.deepcopy(self.raw);row=plan['specifications']['targets'][0];target=actual['nodes'][1]
        target['specification']={'schema':'figma-flow-native-spec-v1','semantic_key':'full.deliver','target_id':'2:1','source_owner_hash':'b'*64,'specification':row['after'],'legacy_annotations':row['legacy_annotations'],'state':'applied'}
        target['annotations']=target['annotations'][:1]
        ref={'boardId':'3:1','textNodeId':'5:1','key':'viewport|state|control'}
        connected=api.connected_annotation_markdown(row['after'],'file',ref['textNodeId'])
        annotation={'labelMarkdown':connected['markdown']}
        target['annotations'].append(annotation)
        target['specification']['human_annotation']={'schema':'figma-flow-human-annotation-v1','index':1,
            'annotation':annotation,'board':ref,'url':connected['url']}
        actual['nodes'][4]['characters']=row['after']['title']+'\n'+row['after']['display_text']
        return actual
    def test_plan_recompiles_and_verifies_exact_actual_fields(self):
        plan=self.plan();self.assertEqual(plan['specifications']['targets'][0]['legacy_annotations'][0]['index'],1)
        self.assertTrue(api.verify(self.path,plan,self.after(plan))['passed'])
        rebound=self.after(plan);rebound['nodes'][4]['id']='99:1';rebound['nodes'][4]['semanticKey']='design-note-board:different-entry'
        self.assertFalse(api.verify(self.path,plan,rebound)['passed'])
        for mutate in [lambda r:r['nodes'][1]['specification']['specification'].update(meaning={}),lambda r:r['nodes'][1].update(semanticKey='wrong'),lambda r:r['nodes'][4].update(hyperlink={'type':'NODE','value':'7:1'}),lambda r:r['nodes'][4].update(characters='stale')]:
            actual=self.after(plan);mutate(actual)
            try:self.assertFalse(api.verify(self.path,plan,actual)['passed'])
            except ValueError:pass
    def test_no_suffix_guess_unknown_board_children_and_duplicate_fail(self):
        with self.assertRaises(ValueError):api.plan(self.path,self.raw)
        for mutate in [lambda r:r['nodes'].append(copy.deepcopy(r['nodes'][1])),lambda r:r['nodes'][2].update(designNoteBoard={'pageId':'1:1','sourceHash':'c'*64}),lambda r:r['nodes'][4].update(semanticKey='user'),lambda r:r['nodes'][1]['annotations'].append(copy.deepcopy(r['nodes'][1]['annotations'][1]))]:
            self.raw=readback();mutate(self.raw)
            with self.assertRaises(ValueError):self.plan()
    def test_variable_font_getter_is_preserved_and_validated_exactly(self):
        font={'family':'Noto Sans KR','style':'Regular','variationSettings':{'wght':400}}
        self.raw['nodes'][3]['fontName']=copy.deepcopy(font)
        self.raw['nodes'][4]['fontName']=copy.deepcopy(font)
        prepared=self.plan()
        self.assertEqual(prepared['specifications']['board']['font'],font)
        api.validate_update(prepared)
        self.raw['nodes'][4]['fontName']['variationSettings']['wght']=500
        with self.assertRaises(ValueError):self.plan()
        for bad in [
            {'family':'Noto Sans KR','style':'Regular','variationSettings':{'wght':float('nan')}},
            {'family':'Noto Sans KR','style':'Regular','variationSettings':{'bad-axis':400}},
            {'family':'Noto Sans KR','style':'Regular','variationSettings':{'wght':True}},
            {'family':'Noto Sans KR','style':'Regular','variationSettings':{'wght':10001}},
            {'family':'Noto Sans KR','style':'Regular','extra':'untrusted'},
        ]:
            self.raw=readback();self.raw['nodes'][3]['fontName']=copy.deepcopy(bad);self.raw['nodes'][4]['fontName']=copy.deepcopy(bad)
            with self.assertRaises(ValueError):self.plan()
        self.raw=readback();self.raw['nodes'][3]['fontName']=copy.deepcopy(font);self.raw['nodes'][4]['fontName']=copy.deepcopy(font)
        prepared=self.plan();prepared['specifications']['board']['font']['variationSettings']={'wght':float('nan')}
        with self.assertRaises(ValueError):api.validate_update(prepared)
    def test_new_graph_revision_invalidates_old_plan_and_caller_authored_after(self):
        prepared=self.plan();forged=copy.deepcopy(prepared);forged['specifications']['targets'][0]['after']['display_text']='plausible'
        with self.assertRaises(ValueError):native_edit.validate_plan(forged)
        graph=fixture();graph['nodes'][1]['annotation']['behavior']='새 목적지의 답장을 연다.';self.path.write_text(json.dumps(graph))
        with self.assertRaises(ValueError):native_edit.validate_plan(prepared)
        fresh=self.plan();self.assertNotEqual(prepared['specifications']['targets'][0]['after']['meaning_sha256'],fresh['specifications']['targets'][0]['after']['meaning_sha256'])
    def test_prepare_emits_private_nested_pins_and_same_protocol(self):
        prepared=self.plan();source=Path(self.temp.name)/'plan.json';source.write_text(json.dumps(prepared));out=Path(self.temp.name)/'prepared'
        native_edit.prepare(source,out)
        sidecar=json.loads((out/'source-inputs.json').read_text());self.assertEqual(sidecar['schema'],'figma-flow-source-pins-v1');self.assertEqual(sidecar['pins'][1],prepared['specifications']['source_graph'])
        self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((out/'source-inputs.json').stat().st_mode),0o600)
        self.assertIn('nativeSpecificationApply',(out/'code.js').read_text())
        self.assertEqual(subprocess.run(['node','--check',str(out/'code.js')],capture_output=True).returncode,0)
        self.path.write_text(self.path.read_text()+' ')
        with self.assertRaises(ValueError):native_edit.prepare(source,Path(self.temp.name)/'stale')
    def test_v2_getter_replans_and_edited_human_text_fails(self):
        prepared=self.plan();self.raw=self.after(prepared)
        fresh=self.plan();self.assertEqual(fresh['specifications']['targets'][0]['legacy_annotations'],[])
        self.assertEqual(fresh['specifications']['targets'][0]['node_id'],'2:1')
        self.raw['nodes'][4]['characters']='user edited text'
        with self.assertRaises(ValueError):self.plan()
    def test_distinct_board_key_and_proven_unprefixed_legacy_annotation(self):
        plan=self.plan();self.raw['nodes'][4]['characters']='Deliver · viewport|state|control\nLegacy original\n화면·조작으로 이동'
        self.raw['nodes'][1]['annotations']=[{'label':'keep this note'},{'label':'Legacy original','labelMarkdown':'**Legacy original**'}]
        self.raw['nodes'][1]['declared_metadata']={'annotation_mode':'native','semantic_id':'full.deliver'}
        self.raw['nodes'][0]['declared_metadata']={'source_sha256':'b'*64}
        plan=self.plan();self.assertEqual(plan['specifications']['targets'][0]['legacy_annotations'][0]['index'],1)
        self.assertTrue(api.verify(self.path,plan,self.after(plan))['passed'])
        unsafe=copy.deepcopy(self.raw);unsafe['nodes'][1]['declared_metadata']={}
        with self.assertRaises(ValueError):api.plan(self.path,unsafe,[self.note+'=full.deliver'])
        partial=copy.deepcopy(self.raw);partial['nodes'][1]['annotations']=[{'label':'Legacy'}]
        self.assertEqual(api.plan(self.path,partial,[self.note+'=full.deliver'])['specifications']['targets'][0]['legacy_annotations'],[])
    def test_archived_unprefixed_annotation_reappearing_conflicts(self):
        plan=self.plan();actual=self.after(plan)
        archived=actual['nodes'][1]['specification']['legacy_annotations'][0]['annotation']
        actual['nodes'][1]['annotations'].append(archived)
        with self.assertRaises(ValueError):api.plan(self.path,actual,[self.note+'=full.deliver'])
    def test_export_and_flat_general_tree_normalization(self):
        out=Path(self.temp.name)/'export';api.export(self.path,out)
        self.assertTrue((out/'screen-spec.md').exists())
        raw=self.raw;page=copy.deepcopy(raw['nodes'][0]);page['children']=copy.deepcopy(raw['nodes'][1:3]);page['children'][1]['children']=copy.deepcopy(raw['nodes'][3:]);page['declared_metadata']={'source_sha256':'b'*64}
        for node in [*page['children'],*page['children'][1]['children']]:
            if 'semanticKey' in node: node['semantic_id']=node.pop('semanticKey')
        general={'fileKey':'file','pages':[page]}
        self.assertEqual(api.plan(self.path,general,[self.note+'=full.deliver'])['page_id'],'1:1')

if __name__=='__main__':unittest.main()
