import copy
import json
from pathlib import Path
import sys
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from design_foundations import derive_foundations, validate_foundations, validate_foundations_review


def fixture():
    contract = derive_foundations({'nodes': [{'id': 'action', 'type': 'component', 'title': 'Join action'}]})
    nodes = [
        {'id': 'page', 'type': 'PAGE'},
        {'id': 'library', 'type': 'FRAME', 'parentId': 'page'},
        {'id': 'set', 'type': 'COMPONENT_SET', 'parentId': 'library', 'x': 0, 'y': 0, 'width': 100, 'height': 50},
        {'id': 'main', 'type': 'COMPONENT', 'parentId': 'set', 'x': 0, 'y': 0, 'width': 100, 'height': 50, 'variantProperties': {'State': 'Default'}},
        {'id': 'sample', 'type': 'INSTANCE', 'name': 'Join action', 'parentId': 'library', 'mainComponentId': 'main', 'x': 0, 'y': 100, 'width': 100, 'height': 50},
        {'id': 'text', 'type': 'TEXT', 'parentId': 'sample', 'fontSize': 16, 'boundVariables': {}},
        {'id': 'layout', 'type': 'FRAME', 'parentId': 'sample', 'layoutMode': 'VERTICAL', 'paddingTop': 16, 'itemSpacing': 8, 'cornerRadius': 8, 'boundVariables': {}, 'fills': []}]
    variables = []
    fields = [('layout', 'fills'), ('text', 'fontSize'), ('layout', 'paddingTop'), ('layout', 'itemSpacing'), ('layout', 'cornerRadius')]
    by_id = {n['id']: n for n in nodes}
    for i, (role, (node_id, field)) in enumerate(zip(contract['roles'], fields)):
        value = {'r': .1, 'g': .2, 'b': .3} if i == 0 else [0, 16, 16, 8, 8][i]
        kind = 'COLOR' if i == 0 else 'FLOAT'
        variables += [
            {'id': f'primitive:{i}', 'name': role['alias'], 'resolvedType': kind, 'variableCollectionId': 'collection', 'valuesByMode': {'mode': value}},
            {'id': f'semantic:{i}', 'name': role['token'], 'resolvedType': kind, 'variableCollectionId': 'collection', 'valuesByMode': {'mode': {'type': 'VARIABLE_ALIAS', 'id': f'primitive:{i}'}}}]
        alias = {'type': 'VARIABLE_ALIAS', 'id': f'semantic:{i}'}
        if field == 'fills':
            by_id[node_id]['fills'] = [{'type': 'SOLID', 'color': value, 'boundVariables': {'color': alias}}]
        else:
            by_id[node_id]['boundVariables'][field] = alias
        role['bindings'] = [{'nodeId': node_id, 'field': field}]
    contract['palette']['libraryId'] = 'library'
    contract['palette']['samples'][0].update(instanceId='sample', mainComponentId='main', componentSetId='set', labelNodeId='label', documentationNodeId='documentation')
    nodes.extend([{'id': 'label', 'type': 'TEXT', 'parentId': 'library', 'characters': 'Join action', 'fontSize': 16, 'boundVariables': {'fontSize': {'type': 'VARIABLE_ALIAS', 'id': 'semantic:1'}}},
                  {'id': 'documentation', 'type': 'TEXT', 'parentId': 'library', 'characters': 'Join action / Default', 'fontSize': 16, 'boundVariables': {'fontSize': {'type': 'VARIABLE_ALIAS', 'id': 'semantic:1'}}}])
    return {'nodes': nodes, 'variables': variables, 'collections': [{'id': 'collection', 'name': 'Foundations', 'modes': [{'modeId': 'mode'}]}]}, contract


class DesignFoundationsTests(unittest.TestCase):
    def codes(self, report):
        return {f['code'] for f in report['failures']}

    def test_plan_never_claims_native_integration(self):
        contract = derive_foundations({'nodes': [{'id': 'button', 'type': 'component', 'title': 'Continue button'}]})
        report = validate_foundations(None, contract, stage='plan')
        self.assertTrue(report['ok'], report)
        self.assertFalse(report['native_verified'])
        self.assertEqual(report['evidence_kind'], 'proposed-only')
        self.assertFalse(validate_foundations(None, contract)['ok'])

    def test_actual_modeled_relationships_and_bindings_pass(self):
        native, contract = fixture()
        report = validate_foundations(native, contract)
        self.assertTrue(report['ok'], report)
        self.assertEqual(len(report['coverage']['roles']), 5)
        self.assertTrue(report['native_verified'])

    def test_typed_font_family_and_zero_spacing_are_actual_native_consumers(self):
        native, contract = fixture()
        font_alias = {'type': 'VARIABLE_ALIAS', 'id': 'semantic:family'}
        native['variables'] += [
            {'id': 'primitive:family', 'name': 'font/source', 'resolvedType': 'STRING', 'variableCollectionId': 'collection', 'valuesByMode': {'mode': 'Gowun Dodum'}},
            {'id': 'semantic:family', 'name': 'font/body', 'resolvedType': 'STRING', 'variableCollectionId': 'collection', 'valuesByMode': {'mode': {'type': 'VARIABLE_ALIAS', 'id': 'primitive:family'}}}]
        for node in native['nodes']:
            if node.get('type') == 'TEXT':
                node['fontName'] = {'family': 'Gowun Dodum', 'style': 'Regular'}
                node.setdefault('boundVariables', {})['fontFamily'] = font_alias
        contract['roles'].append({'name': 'Body family', 'kind': 'typography', 'token': 'font/body', 'alias': 'font/source',
            'value': 'Body font family', 'native': {'type': 'STRING', 'value': 'Gowun Dodum', 'bindings': [{'nodeId': 'text', 'field': 'fontFamily'}]}})
        contract['roles'][2]['native'] = {'type': 'FLOAT', 'value': 0}
        native['variables'][4]['valuesByMode']['mode'] = 0
        native['nodes'][6]['paddingTop'] = 0
        self.assertTrue(validate_foundations(None, contract, stage='plan')['ok'])
        result = validate_foundations(native, contract)
        self.assertTrue(result['ok'], result)
        native['nodes'][5]['fontName']['family'] = 'Different font'
        self.assertIn('native-rendered-value-mismatch', self.codes(validate_foundations(native, contract)))
        native['nodes'][5]['fontName']['family'] = 'Gowun Dodum'
        native['variables'][-2]['valuesByMode']['mode'] = 'Different font'
        self.assertIn('native-token-value-mismatch', self.codes(validate_foundations(native, contract)))

    def test_typed_role_rejects_wrong_types_and_invalid_zero_font_size(self):
        _, contract = fixture()
        for kind, native_type, value in [('typography', 'FLOAT', 0), ('spacing', 'FLOAT', -1),
                                         ('typography', 'STRING', ''), ('spacing', 'STRING', 'Gowun Dodum')]:
            changed = copy.deepcopy(contract)
            changed['roles'][1].update(kind=kind, native={'type': native_type, 'value': value})
            self.assertIn('invalid-native-role-value', self.codes(validate_foundations(None, changed, stage='plan')))

    def test_typed_color_role_is_a_valid_plan(self):
        _, contract = fixture()
        color = next(role for role in contract['roles'] if role['kind'] == 'color')
        color['native'] = {'type': 'COLOR', 'value': {'r': 1, 'g': .5, 'b': 0}}
        self.assertNotIn('invalid-native-role-value', self.codes(validate_foundations(None, contract, stage='plan')))
        for value in ({'r': 1, 'g': .5, 'b': 0, 'a': .5}, {'r': 2, 'g': 0, 'b': 0}, '#FF8000', {'r': 1, 'g': 0}):
            with self.subTest(value=value):
                color['native'] = {'type': 'COLOR', 'value': value}
                self.assertIn('invalid-native-role-value', self.codes(validate_foundations(None, contract, stage='plan')))

    def test_style_id_must_resolve_and_be_applied_to_real_text(self):
        native, contract = fixture()
        contract['roles'][1]['styleId'] = 'body-style'
        self.assertIn('native-style-mismatch', self.codes(validate_foundations(native, contract)))
        native['styles'] = [{'id': 'body-style', 'name': 'Body', 'type': 'TEXT'}]
        native['nodes'][5]['textStyleId'] = 'body-style'
        report = validate_foundations(native, contract)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['coverage']['styles'], [{'styleId': 'body-style', 'nodeId': 'text'}])

    def test_json_documentation_cannot_replace_visible_native_text(self):
        native, contract = fixture()
        native['nodes'][-1]['characters'] = ''
        self.assertIn('missing-visible-sample-documentation', self.codes(validate_foundations(native, contract)))
        native['nodes'][-2]['visible'] = False
        self.assertIn('missing-visible-sample-label', self.codes(validate_foundations(native, contract)))

    def test_review_requires_visible_role_and_palette_meaning(self):
        _, contract = fixture()
        values = [str(role[key]) for role in contract['roles'] for key in ('name', 'kind', 'token', 'value')]
        sample = contract['palette']['samples'][0]
        values += [sample[key] for key in ('label', 'component', 'variant', 'action', 'state')] + sample['useCases']
        html = '<p>planned · not native</p><p>' + ' '.join(values) + '</p>'
        self.assertTrue(validate_foundations_review(contract, html)['ok'])
        self.assertFalse(validate_foundations_review(contract, '<section hidden>' + html + '</section>')['ok'])
        self.assertFalse(validate_foundations_review(contract, html.replace('planned · not native', 'complete'))['ok'])

    def test_malformed_plan_returns_failure(self):
        self.assertFalse(validate_foundations(None, {'version': 1, 'roles': [{'name': {}, 'token': []}]}, stage='plan')['ok'])

    def test_color_only_is_not_complete(self):
        native, contract = fixture()
        native['variables'] = [v for v in native['variables'] if v['resolvedType'] == 'COLOR']
        report = validate_foundations(native, contract)
        self.assertFalse(report['ok'])
        self.assertIn('missing-or-invalid-native-token', self.codes(report))
        self.assertIn('unbound-rendered-use', self.codes(report))

    def test_missing_binding_or_wrong_node_cannot_pass(self):
        for mutate in (lambda d, c: d['nodes'][5]['boundVariables'].clear(),
                       lambda d, c: c['roles'][1]['bindings'][0].update(nodeId='missing')):
            native, contract = fixture()
            mutate(native, contract)
            self.assertFalse(validate_foundations(native, contract)['ok'])

    def test_alias_cycles_and_undeclared_radius_fail(self):
        native, contract = fixture()
        native['variables'][0]['valuesByMode']['mode'] = {'type': 'VARIABLE_ALIAS', 'id': 'semantic:0'}
        contract['roles'] = [r for r in contract['roles'] if r['kind'] != 'radius']
        codes = self.codes(validate_foundations(native, contract))
        self.assertIn('missing-or-invalid-native-token', codes)
        self.assertIn('missing-role-kind', codes)

    def test_overlapping_sets_and_collapsed_variants_fail(self):
        native, contract = fixture()
        native['nodes'].append(dict(native['nodes'][2], id='set2'))
        native['nodes'].append(dict(native['nodes'][3], id='main2'))
        self.assertIn('overlapping-palette-items', self.codes(validate_foundations(native, contract)))

    def test_overlapping_samples_or_broken_main_relationship_fail(self):
        native, contract = fixture()
        sample = dict(contract['palette']['samples'][0], label='Second action', instanceId='sample2', labelNodeId='label2')
        native['nodes'].append({'id': 'label2', 'type': 'TEXT', 'parentId': 'library', 'characters': 'Second action'})
        contract['palette']['samples'].append(sample)
        native['nodes'].append(dict(native['nodes'][4], id='sample2', name='Second action'))
        self.assertIn('overlapping-palette-items', self.codes(validate_foundations(native, contract)))
        native['nodes'][-1]['mainComponentId'] = 'other'
        self.assertIn('invalid-palette-native-relationship', self.codes(validate_foundations(native, contract)))

    def test_palette_requires_unique_labels_actions_and_use_cases(self):
        _, contract = fixture()
        contract['palette']['samples'][0]['useCases'] = []
        self.assertIn('missing-sample-documentation', self.codes(validate_foundations(None, contract, stage='plan')))

    def test_uniform_corner_binding_reads_real_per_corner_aliases(self):
        native, contract = fixture()
        layout = native['nodes'][6]
        alias = layout['boundVariables'].pop('cornerRadius')
        for corner in ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'):
            layout[corner] = 8
            layout['boundVariables'][corner] = alias
        self.assertTrue(validate_foundations(native, contract)['ok'])

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for native helper model')
    def test_authoring_helper_layout_bindings_and_rollback(self):
        helper = ROOT / 'figma-bridge' / 'foundation_palette.js'
        script = r"""
const assert = require('node:assert/strict');
const {layoutFoundationSets, createFoundationPalette} = require(process.argv[1]);
let next = 0;
const nodes = [];
function node(type) {
  const n = {id:String(++next),type,children:[],removed:false,
    appendChild(child) { if(child.parent)child.parent.children=child.parent.children.filter(n=>n!==child); this.children.push(child);child.parent=this; },
    remove() {this.removed=true;for(const c of this.children)c.remove();}};
  nodes.push(n);return n;
}
const page = node('PAGE'), owned = node('FRAME'), set = node('COMPONENT_SET');
owned.appendChild(set);
layoutFoundationSets(owned, [set]);
assert.equal(owned.layoutMode, 'VERTICAL');assert.equal(set.layoutMode, 'VERTICAL');
assert.equal(set.primaryAxisSizingMode, 'AUTO');assert.equal(set.itemSpacing,24);
assert.throws(()=>layoutFoundationSets(page,[set]));
const main = node('COMPONENT');set.appendChild(main);main.variantProperties={State:'Default'};
main.createInstance=()=>node('INSTANCE');
const figma={createFrame:()=>node('FRAME'),createText:()=>node('TEXT'),
  async loadFontAsync(){},async getNodeByIdAsync(id){return nodes.find(n=>n.id===id);}};
const contract={sourceHash:'source',type:{token:'type/body',value:16},space:{token:'space/content',value:16},
  ink:{token:'color/ink',value:{r:0,g:0,b:0}}, tokens:[],samples:[{label:'Join action',component:'action',
  mainComponentId:main.id,variant:'Default',action:'Join',state:'Default',useCases:['Registration']} ]};
(async()=>{
  let rolledBack=false;
  const result=await createFoundationPalette(figma,page,contract,async(f,p,c)=>{
    assert(c.bindings.some(b=>b.field==='fontSize'&&nodes.find(n=>n.id===b.key).fontSize===16));
    assert(c.bindings.some(b=>b.field==='itemSpacing'));
    assert(c.bindings.some(b=>b.field==='paddingTop'));
    assert(c.bindings.some(b=>b.field==='fills'));
    return {async rollback(){rolledBack=true;}};
  });
  assert.equal(result.samples[0].mainComponentId,main.id);
  assert.equal(result.samples[0].componentSetId,set.id);
  assert.equal(nodes.find(n=>n.id===result.libraryId).layoutMode,'VERTICAL');
  await result.rollback();assert(rolledBack);assert(nodes.find(n=>n.id===result.libraryId).removed);
  const before=nodes.length;
  await assert.rejects(createFoundationPalette(figma,page,contract,async()=>{throw Error('binding failure');}));
  assert(nodes.slice(before).every(n=>n.removed));
  assert(!main.removed);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        completed = subprocess.run(['node', '-e', script, str(helper)], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for native collector model')
    def test_plugin_api_getters_collect_styles_padding_gap_and_per_corner_radius(self):
        native, contract = fixture()
        contract['roles'][1]['styleId'] = 'body-style'
        native['nodes'][5]['textStyleId'] = 'body-style'
        font_binding = native['nodes'][5]['boundVariables'].pop('fontSize')
        native['styles'] = [{'id': 'body-style', 'type': 'TEXT', 'name': 'Body',
                             'fontSize': 16, 'fontName': {'family': 'Inter', 'style': 'Regular'},
                             'boundVariables': {'fontSize': font_binding}}]
        layout = native['nodes'][6]
        corner_binding = layout['boundVariables'].pop('cornerRadius')
        for corner in ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'):
            layout[corner] = 8
            layout['boundVariables'][corner] = corner_binding
        helper = ROOT / 'figma-bridge' / 'native_semantic_read.js'
        script = r"""
const fs = require('node:fs'), assert = require('node:assert/strict');
const {readNativeSemantics} = require(process.argv[1]);
const input = JSON.parse(fs.readFileSync(0,'utf8'));
// API-backed getters intentionally have no enumerable own properties.
function api(values) {const proto={};for(const [k,v] of Object.entries(values))Object.defineProperty(proto,k,{get(){return v;}});return Object.create(proto);}
const nodes = new Map(input.nodes.map(raw=>[raw.id,api(raw)]));
for(const raw of input.nodes){const n=nodes.get(raw.id);n.parent=nodes.get(raw.parentId);n.children=input.nodes.filter(r=>r.parentId===raw.id).map(r=>nodes.get(r.id));n.getPluginData=()=>'';}
const page=nodes.get('page');page.loadAsync=async()=>{};page.findAll=()=>[...nodes.values()].filter(n=>n!==page);
for(const n of nodes.values())if(n.type==='INSTANCE')n.getMainComponentAsync=async()=>nodes.get(n.mainComponentId);
const collections=input.collections.map(raw=>({...raw,defaultModeId:'mode',variableIds:input.variables.map(v=>v.id),getPluginData:()=>''}));
const figma={getStyleByIdAsync:async id=>{if(process.argv[2]==='missing')return null;const style=api(input.styles.find(s=>s.id===id));if(process.argv[2]==='broken')Object.defineProperty(style,'fontSize',{get(){throw Error('style getter failed');}});return style;},variables:{
 getLocalVariableCollectionsAsync:async()=>collections,
 getVariableByIdAsync:async id=>api(input.variables.find(v=>v.id===id)),
 getVariableCollectionByIdAsync:async id=>collections.find(c=>c.id===id)}};
(async()=>{const result=await readNativeSemantics(figma,page);assert.equal(result.nodes.find(n=>n.id==='layout').paddingTop,16);assert.equal(result.nodes.find(n=>n.id==='layout').itemSpacing,8);assert.equal(result.nodes.find(n=>n.id==='layout').topLeftRadius,8);console.log(JSON.stringify(result));})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        for mode in ('available', 'missing', 'broken'):
            with self.subTest(style=mode):
                completed = subprocess.run(['node', '-e', script, str(helper), mode], input=json.dumps(native), text=True, capture_output=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                observed = json.loads(completed.stdout)
                report = validate_foundations(observed, contract)
                if mode == 'available':
                    self.assertEqual(observed['styles'][0]['fontSize'], 16)
                    self.assertEqual(observed['styles'][0]['boundVariables']['fontSize'], font_binding)
                    self.assertTrue(report['ok'], report)
                else:
                    self.assertTrue(any(row.get('styleId') == 'body-style' for row in observed['unavailableFields']))
                    self.assertFalse(report['ok'])
                    self.assertIn('native-style-mismatch' if mode == 'missing' else 'native-binding-mismatch', self.codes(report))

    def test_stored_night_exports_fail_actual_foundations(self):
        # Portable excerpts of actual stored exports, never synthetic passing proof.
        # Full-source audit stays separate; no sibling workspace or home is needed.
        samples = [('postal', '2:4953', 18, 18, 9, 'd209e11718ed6f402b37a22d71a4a31321953da36facd92ff06e94c6906196b8'),
                   ('club', '2:2574', 22, 6, 3, 'e90c913c770d7d69fc130e9f95fffea689fa733465f1ab49507dc7f7907d0868')]
        for slug, library_id, full_set_count, variable_count, alias_count, source_sha in samples:
            path = ROOT / 'tests' / 'fixtures' / f'night-{slug}-foundations-excerpt.json'
            with self.subTest(slug=slug):
                captured = json.loads(path.read_text())
                provenance, native = captured['provenance'], captured['native']
                self.assertEqual(provenance['kind'], 'excerpt-of-stored-native-readback-not-live-verification')
                self.assertEqual(provenance['source_sha256'], source_sha)
                self.assertEqual(provenance['source_library_component_set_count'], full_set_count)
                self.assertEqual(provenance['included_node_ids'], [n['id'] for n in native['nodes']])
                self.assertLess(len(native['nodes']), provenance['source_node_count'])
                sets = [n for n in native['nodes'] if n.get('type') == 'COMPONENT_SET' and n.get('parentId') == library_id]
                self.assertEqual(len(sets), 2)  # Two original overlapping sets suffice.
                self.assertEqual({(n['x'], n['y']) for n in sets}, {(0, 0)})
                self.assertEqual(len(native['variables']), variable_count)
                self.assertEqual({v['resolvedType'] for v in native['variables']}, {'COLOR'})
                self.assertEqual(sum(any(isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS'
                                         for value in variable['valuesByMode'].values()) for variable in native['variables']), alias_count)
                _, contract = fixture()
                contract['palette']['libraryId'] = library_id
                report = validate_foundations(native, contract)
                self.assertFalse(report['ok'])
                self.assertIn('overlapping-palette-items', self.codes(report))
                self.assertEqual({use['kind'] for use in report['coverage']['unbound_uses']}, {'typography', 'spacing', 'radius'})
                color_node = next(n for n in native['nodes'] if n['id'] == provenance['representative_nodes']['bound_solid_color'])
                self.assertTrue(any(paint.get('boundVariables', {}).get('color') for paint in color_node['fills']))


if __name__ == '__main__':
    unittest.main()
