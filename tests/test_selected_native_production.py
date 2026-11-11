"""Selected authoring contract tests. Synthetic records are not native or human proof."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_draft as draft
import design_directions as directions


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return directions.pin(path)


class SelectedProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old_graph = self.root / 'selected-graph.json'; self.graph_path = self.root / 'production/graph.json'
        graph = {'version':1,'nodes':[{'id':'screen','type':'screen'}],'edges':[],
                 'draft_prototype':{'entry_state':'idle','states':[{'id':'idle','entry':True}], 'bindings':[]},
                 'design_foundations':{'roles':[{'kind':'color','token':'color/paper','native':{'type':'COLOR','value':'#ffffff','bindings':[]}}], 'palette':{'samples':[]}}}
        write(self.old_graph, graph); self.graph = copy.deepcopy(graph)
        self.text = {'id':'label','kind':'text','value':'Chosen content','x':10,'y':10,'w':40,'h':20,'ink':'ink'}
        self.old = {'id':'chosen','colors':{'ink':'#000000','paper':'#ffffff'},'fonts':{'body':{'family':'Inter','style':'Regular'}},
                    'control_styles':{'desktop':{'Primary':{'ink':'ink','fill':'paper'}}},
                    'state_layouts':{'desktop':{'idle':{'width':100,'height':100,'layers':[self.text],'control_boxes':{}}}},
                    'graph':directions.pin(self.old_graph),'references':{}}
        self.old['layouts'] = {'desktop':copy.deepcopy(self.old['state_layouts']['desktop']['idle'])}
        self.old_layout = self.root / 'native-layout.json'; self.layout = self.root / 'production/native-layout.json'
        self.art = self.root / 'art.bin'; self.art.write_bytes(b'previously reviewed art')
        self.art_copy = self.root / 'production/art.bin'; self.art_copy.parent.mkdir(); self.art_copy.write_bytes(self.art.read_bytes())
        self.assets = {'art':{'path':'art.bin','sha256':draft.sha(self.art.read_bytes()),'reference':False}}
        write(self.old_layout, {'candidates':[self.old],'assets':self.assets})
        self.selection_file = self.root / 'selection.json'; self.selection_file.write_text('{}')
        self.selected = {'selection_path':str(self.selection_file),'selection_sha256':draft.sha(self.selection_file.read_bytes()),
                         'candidate_id':'chosen','candidate_sha256':'a'*64,'product_graph':directions.pin(self.old_graph)}
        self.provenance = {**{k:self.selected[k] for k in ('candidate_id','candidate_sha256')},'path':str(self.selection_file),
                           'sha256':self.selected['selection_sha256'],'review_layout_sha256':draft.sha(self.old_layout.read_bytes())}
        self.candidate = copy.deepcopy(self.old)
        self.rect = {'id':'backing','kind':'rect','role':'surface','fill':'paper','opacity':1,'x':10,'y':10,'w':40,'h':20}
        self.candidate['state_layouts']['desktop']['idle']['layers'].insert(0,self.rect)
        self.authored = {'schema':'figma-flow-authored-native-production-v1','scope':'selected-production','sourceSelection':self.provenance,
                         'candidates':[self.candidate],'assets':copy.deepcopy(self.assets)}
        self.user_file = self.root / 'managed.jsonl'; self.directive = 'Preserve the chosen design, synchronize it, and correct the contrast of its text surfaces.'
        self.user_file.write_text(json.dumps({'type':'event_msg','payload':{'type':'user_message','message':self.directive}})+'\n')
        message = list(directions._messages(self.user_file))[0]
        self.user = {'path':str(self.user_file),'prefix_length':message['prefix_length'],'prefix_sha256':message['prefix_sha256'],'directive':self.directive}
        self.selected['human'] = copy.deepcopy(self.user)
        self.request_path = self.root / 'production/change.json'
        self.reviewed = {'project_root':str(self.root),'native_layout':directions.pin(self.old_layout)}
        self.user_root = self.enterContext(patch.object(directions,'user_record_root',return_value=self.root))
        self.save()

    def save(self):
        graph_pin = write(self.graph_path,self.graph); self.candidate['graph'] = graph_pin
        self.candidate['layouts'] = {'desktop':copy.deepcopy(self.candidate['state_layouts']['desktop']['idle'])}
        write(self.layout,self.authored)
        changes = draft._production_diff(draft._production_layer_map(self.old,'idle'),draft._production_layer_map(self.candidate,'idle'))
        for row in changes:
            row['category']='contrast'
            if row['path'][-1]=='backing': row['text_ids']=['label']
        self.request = {'schema':'figma-flow-selected-production-change-v1','selection':directions.pin(self.selection_file),
                        'candidate_id':'chosen','reviewed_layout':directions.pin(self.old_layout),'production_layout':directions.pin(self.layout),
                        'production_graph':graph_pin,'user':self.user,'categories':['contrast','sync'],'changes':changes}
        write(self.request_path,self.request)

    def check(self):
        return draft._selected_production_inputs(self.selected,self.reviewed,self.authored,self.layout,self.graph_path,self.request_path)

    def test_valid_selected_backing_and_identical_art_copy(self):
        provenance, graph_pin, request_pin = self.check()
        self.assertEqual(provenance,self.provenance); self.assertEqual(graph_pin,directions.pin(self.graph_path))
        self.assertEqual(request_pin,directions.pin(self.request_path)); self.assertEqual(len(self.request['changes']),1)

    def test_missing_or_wrong_selection_authority_stops(self):
        with self.assertRaises(ValueError): draft._selected_production_inputs(self.selected,self.reviewed,self.authored,self.layout,self.graph_path,None)
        self.authored['sourceSelection']={**self.provenance,'candidate_id':'other'}
        with self.assertRaisesRegex(ValueError,'source selection'): self.check()

    def test_forged_managed_prefix_stops(self):
        self.request['user']={**self.user,'prefix_sha256':'0'*64}; write(self.request_path,self.request)
        with self.assertRaisesRegex(ValueError,'Managed user prefix'): self.check()

    def test_actions_and_prototype_semantics_cannot_change(self):
        self.graph['nodes'].append({'id':'new-action','type':'action'}); self.save()
        with self.assertRaisesRegex(ValueError,'semantics'): self.check()

    def test_declared_authority_cannot_change_text_fonts_or_geometry(self):
        for field,value in [('value','Rewritten copy'),('x',11),('font','different')]:
            with self.subTest(field=field):
                text=self.candidate['state_layouts']['desktop']['idle']['layers'][1]; before=copy.deepcopy(text)
                text[field]=value; self.save()
                with self.assertRaisesRegex(ValueError,'contrast fields'): self.check()
                text.clear();text.update(before)

    def test_backing_must_be_opaque_and_cover_existing_text(self):
        for field,value in [('opacity',.5),('w',39)]:
            with self.subTest(field=field):
                before=self.rect[field];self.rect[field]=value;self.save()
                with self.assertRaises(ValueError):self.check()
                self.rect[field]=before

    def test_existing_layers_cannot_be_removed(self):
        self.candidate['state_layouts']['desktop']['idle']['layers'].pop();self.save()
        with self.assertRaisesRegex(ValueError,'cannot be removed|existing text'):self.check()

    def test_mirror_cannot_diverge(self):
        self.candidate['layouts']['desktop']['layers']=[]
        with self.assertRaisesRegex(ValueError,'mirror'):draft._production_layer_map(self.candidate,'idle')

    def test_foundation_values_and_undeclared_changes_stay_guarded(self):
        self.graph['design_foundations']['roles'][0]['native']['value']='#000000';self.save()
        with self.assertRaisesRegex(ValueError,'foundation values'):self.check()
        self.graph['design_foundations']['roles'][0]['native']['value']='#ffffff';self.save()
        self.request['changes']=[];write(self.request_path,self.request)
        with self.assertRaisesRegex(ValueError,'deltas differ'):self.check()

    def test_review_flags_cannot_be_flipped_into_production(self):
        packet=self.root/'packet.json';write(packet,{'schema':'figma-flow-native-direction-review-v1','scope':'selected-production','production_admitted':True})
        report=draft.verify_native_production(packet,self.root/'unused-readback.json')
        self.assertFalse(report['passed']);self.assertIn('Distinct selected production',report['errors'][0])


class RendererAttestationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.manifest=self.root/'directions.json';self.manifest.write_text('{}')
        sources={}
        for name in (*draft.HELPERS,'direction_review.js'):
            path=self.root/name;path.write_text('// '+name);sources[name]=directions.pin(path)
        importer=draft.canonical_sha({name:pin['sha256'] for name,pin in sources.items()})
        self.packet={'schema':'figma-flow-native-direction-review-v1','scope':'exploratory-only','production_admitted':False,
                     'packet_sha256':'a'*64,'layout_sha256':'b'*64,'fileKey':'fixture','importer_sha256':importer,
                     'prepared_at':'original-time','candidates':[{'id':'chosen','fonts':{'body':'exact'}}]}
        self.packet['instance_sha256']=draft.canonical_sha({'packet':self.packet['packet_sha256'],'layout':self.packet['layout_sha256'],'fileKey':'fixture','importer':importer})
        self.packet_path=self.root/'packet.json';write(self.packet_path,self.packet)
        self.code_path=self.root/'code.js'
        code=draft.review_plugin_code(json.dumps(self.packet,ensure_ascii=False),'\n'.join((self.root/name).read_text()for name in draft.HELPERS),(self.root/'direction_review.js').read_text())
        self.code_path.write_text(code)
        self.snapshot={'schema':'figma-flow-native-renderer-snapshot-v1','packet':directions.pin(self.packet_path),'code':directions.pin(self.code_path),'sources':sources}
        self.sidecar=self.root/'renderer-snapshot.json';write(self.sidecar,self.snapshot)
        fresh={**copy.deepcopy(self.packet),'importer_sha256':'c'*64,'instance_sha256':'d'*64,'prepared_at':'new-time'}
        self.fresh=self.enterContext(patch.object(draft,'make_packet',return_value=fresh))
        self.raw={'instance_sha256':self.packet['instance_sha256']}

    def test_exact_original_sources_and_logical_packet_are_admitted(self):
        self.assertEqual(draft._attested_review_packet(self.manifest,self.raw),self.packet)

    def test_rehashed_code_tamper_cannot_bypass_reconstruction(self):
        self.code_path.write_text(self.code_path.read_text()+'\n// tampered')
        self.snapshot['code']=directions.pin(self.code_path);write(self.sidecar,self.snapshot)
        with self.assertRaisesRegex(ValueError,'exactly contain'):draft._attested_review_packet(self.manifest,self.raw)

    def test_source_hash_and_logical_changes_cannot_be_skipped(self):
        self.fresh.return_value['candidates'][0]['fonts']['body']='changed'
        with self.assertRaisesRegex(ValueError,'logical'):draft._attested_review_packet(self.manifest,self.raw)
        self.fresh.return_value['candidates'][0]['fonts']['body']='exact'
        path=self.root/'direction_review.js';path.write_text('// altered');self.snapshot['sources']['direction_review.js']=directions.pin(path);write(self.sidecar,self.snapshot)
        with self.assertRaisesRegex(ValueError,'implementation digest'):draft._attested_review_packet(self.manifest,self.raw)


if __name__=='__main__':unittest.main()

class ObservedProductionGeometryTests(unittest.TestCase):
    def test_subpixel_delta_requires_unchanged_pinned_dom_measurement(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'measured.json'
            write(path, {'viewport':'desktop','state':'idle','layers':[{'id':'label','y':10.5}]})
            request={'measurements':{'desktop|idle':{'source':directions.pin(path)}}}
            key=['state_layouts','desktop','idle','layers','label','y']
            self.assertTrue(draft._observed_production_geometry(request,key,10.5))
            self.assertFalse(draft._observed_production_geometry(request,key,10.8))
            write(path, {'viewport':'desktop','state':'idle','layers':[{'id':'label','y':10.8}]})
            self.assertFalse(draft._observed_production_geometry(request,key,10.8))
