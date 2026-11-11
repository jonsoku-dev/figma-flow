"""Supplied getter fixtures only; these checks do not prove a live Figma run."""
import copy
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import annotation_contract
import native_handoff
import specification_contract
from test_native_handoff import fixture as native_fixture, attach_design_note_board
from test_specification_contract import fixture as graph_fixture


def readable_fixture():
    data, expected = native_fixture()
    graph = graph_fixture()
    action = graph['nodes'][1]
    action['id'] = 'ACT-PLAY'
    action['annotation'].update(control_id='screen.play', functional_states=['idle', 'playing'])
    graph['nodes'][0]['annotation']['first_action'] = 'ACT-PLAY'
    graph['nodes'].append({'id': 'playing', 'type': 'state', 'title': '재생 중'})
    notes = annotation_contract.derive_notes(graph)
    specs = specification_contract.derive_specifications(graph, source_graph_sha256='a' * 64)
    by_target = {spec['target_id']: spec for spec in specs}
    for note in notes:
        note['native_key'] = note['target_id']
    expected['annotation_contract'] = {'mode': 'strict-creation', 'product_graph': graph, 'notes': notes,
        'source_owner_hash': 'b' * 64, 'specifications': {s['id']: s for s in specs}}
    expected['annotation_presentation'] = 'metadata'
    for node in data['nodes'][:2]:
        spec = by_target[node['semanticKey']]
        node['specification'] = {'schema': specification_contract.NATIVE_SCHEMA, 'state': 'applied',
            'semantic_key': node['semanticKey'], 'target_id': node['id'], 'source_owner_hash': 'b' * 64,
            'specification': copy.deepcopy(spec), 'legacy_annotations': [{'index': 0, 'annotation': node['annotations'][0]}]}
        node['annotations'] = []
    data['nodes'][0]['absoluteBoundingBox'] = {'x': 0, 'y': 0, 'width': 1440, 'height': 900}
    attach_design_note_board(data, expected)
    for entry in expected['design_note_board']['entries']:
        spec = by_target[entry['target_key']]
        entry['label'] = spec['title'] + '\n' + spec['display_text']
    board = next(n for n in data['nodes'] if n.get('semanticKey') == 'design-note-board')
    board['designNoteBoard'] = {'pageId': data['pageId'], 'sourceHash': 'b' * 64}
    for node in data['nodes'][:2]:
        spec = by_target[node['semanticKey']]
        text = next(n for n in data['nodes'] if n.get('hyperlink') == {'type':'NODE','value':node['id']})
        ref = {'boardId':board['id'],'textNodeId':text['id'],'key':node['semanticKey']}
        connected = specification_contract.connected_annotation_markdown(spec,data['fileKey'],text['id'])
        raw = {'label':spec['title']+'\n'+spec['annotation_text']+'\n전체 스펙 보기','labelMarkdown':connected['markdown']}
        node['annotations'] = [raw]
        node['specification']['human_annotation'] = {'schema':'figma-flow-human-annotation-v1','index':0,
            'annotation':copy.deepcopy(raw),'board':ref,'url':connected['url']}
    for node in data['nodes']:
        if node.get('semanticKey') == 'design-note-board':
            node['absoluteBoundingBox']['x'] = 2000
        elif node.get('semanticKey', '').startswith('design-note-board:'):
            node['absoluteBoundingBox']['x'] = 2024
            entry = next(e for e in expected['design_note_board']['entries']
                         if node['semanticKey'] == 'design-note-board:' + e['key'])
            node['characters'] = entry['label']
    return data, expected


class ReadableRenderingTests(unittest.TestCase):
    def test_human_display_and_private_trace_pass_normal_handoff_without_fake_native_annotations(self):
        data, expected = readable_fixture()
        result = native_handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(len(result['screens'][0]['native_annotations']), 1)
        self.assertEqual(len(result['screens'][0]['controls'][0]['native_annotations']), 1)
        rendered = native_handoff.markdown(result)
        self.assertIn('받은 편지를 읽고 목적지를 고른다.', rendered)
        self.assertIn('<details>', rendered)
        self.assertIn('기술 추적 정보', rendered)

    def test_actual_metadata_binding_revision_and_owned_callout_drift_fail(self):
        mutations = [
            lambda d: d['nodes'][1].pop('specification'),
            lambda d: d['nodes'][1]['specification'].update(target_id='9:9'),
            lambda d: d['nodes'][1]['specification']['specification'].update(source_graph_sha256='c' * 64),
            lambda d: d['nodes'][1]['specification']['specification'].update(display_text='그럴듯한 새 설명'),
            lambda d: d['nodes'][1]['annotations'].append({'label': '[figma-flow:screen.play] old trace'}),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data, expected = readable_fixture()
                mutate(data)
                self.assertFalse(native_handoff.evaluate(data, expected)['passed'])

    def test_actual_visible_text_link_and_artwork_overlap_fail_independently_of_metadata(self):
        for field, value in [('characters', '다른 설명'), ('hyperlink', {'type': 'NODE', 'value': '1:2'})]:
            data, expected = readable_fixture()
            next(n for n in data['nodes'] if n.get('semanticKey') == 'design-note-board:screen.play')[field] = value
            self.assertFalse(native_handoff.evaluate(data, expected)['passed'], field)
        data, expected = readable_fixture()
        for node in data['nodes']:
            if node.get('semanticKey', '').startswith('design-note-board'):
                node['absoluteBoundingBox']['x'] -= 2000
        result = native_handoff.evaluate(data, expected)
        self.assertFalse(result['passed'])
        self.assertTrue(any('overlaps artwork' in error for error in result['errors']))

    def test_unrelated_user_annotation_is_preserved_and_missing_trace_never_passes(self):
        data, expected = readable_fixture()
        data['nodes'][1]['annotations'].append({'label': '사용자가 남긴 별도 의견'})
        result = native_handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['screens'][0]['controls'][0]['native_annotations'][-1], '사용자가 남긴 별도 의견')
        expected['annotation_contract']['product_graph']['edges'] = []
        self.assertFalse(native_handoff.evaluate(data, expected)['passed'])

    def test_source_inspection_uses_supplied_readable_contract_for_each_page(self):
        import figma_bridge
        from test_figma_bridge import design
        data, expected = readable_fixture()
        page = {'id': data['pageId'], 'type': 'PAGE', 'children': []}
        nodes = {node['id']: node for node in data.pop('nodes')}
        for node in nodes.values():
            parent = nodes.get(node.get('parentId'), page)
            parent.setdefault('children', []).append(node)
        data.update(format='figma-flow-readback-v1', pages=[page])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, value in [('readback', data), ('contract', expected), ('source', design())]:
                (root / name).write_text(json.dumps(value))
            # Isolate the import comparison boundary; exercise the real handoff evaluator twice.
            comparison = {'status': 'match', 'origin_stamp_match': True, 'missing_screens': []}
            with patch.object(figma_bridge, 'compare_import', return_value=comparison):
                result = figma_bridge.inspect_readback(root / 'readback', root / 'source', root / 'contract')
            self.assertTrue(result['matches_supplied_source'], result)
            self.assertTrue(result['import_checks'][0]['native_handoff']['passed'])

    def test_readable_import_compiler_runtime_and_normal_inspection_chain(self):
        import figma_bridge
        import design_directions
        from direction_fixture import annotated_graph
        from test_figma_bridge import design, selected_graph, MOCK
        source = design()
        graph = annotated_graph(selected_graph(source))
        graph['nodes'] += [{'id': 'req', 'type': 'requirement', 'title': 'Read the supplied content'},
                           {'id': 'ac', 'type': 'acceptance', 'title': 'Show the reading destination'},
                           {'id': 'test', 'type': 'test', 'title': 'Local import fixture'}]
        graph['edges'] += [{'from': 'req', 'to': screen['id'], 'type': 'appears on'} for screen in source['screens']]
        graph['edges'] += [{'from': 'req', 'to': 'ac', 'type': 'accepted by'},
                           {'from': 'ac', 'to': 'test', 'type': 'checked by'}]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, value in [('graph.json', graph), ('source.json', source), ('draft.json', {'mode': 'compare'})]:
                (root / name).write_text(json.dumps(value))
            selected = {'product_graph': design_directions.pin(root / 'graph.json'), 'draft_path': str(root / 'draft.json')}
            digest = hashlib.sha256((root / 'source.json').read_bytes()).hexdigest()
            # Admission is an explicit local test adapter; production authority has separate regressions.
            with patch.object(design_directions, 'require_selected', return_value=selected), \
                    patch.object(design_directions, 'guard_production', return_value={'effect_status': 'test-adapter-only'}):
                figma_bridge.compile_plugin(root / 'source.json', digest, root / 'build', product_graph=root / 'graph.json')
            script = MOCK.split('(async()=>{', 1)[0] + r'''
(async()=>{
  load(process.argv[2]); await send({type:'ready'}); await send({type:'import'});
  assert.equal(imported().length,1,JSON.stringify(messages));
  const page=imported()[0], go=page.findOne(node=>meta(node).semantic_id==='go');
  assert.equal(go.annotations.length,1);
  assert.match(go.annotations[0].labelMarkdown,/전체 스펙 보기/);
  assert.equal(JSON.parse(go.getPluginData('figmaFlowSpecification')).state,'applied');
  assert.equal(root.children[0].children[0],userNode);
  await send({type:'export'});
  fs.writeFileSync(process.argv[3],JSON.stringify(messages.findLast(m=>m.type==='readback').data));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
            (root / 'mock.cjs').write_text(script)
            process = subprocess.run(['node', str(root / 'mock.cjs'), str(root / 'build/code.js'), str(root / 'readback.json')],
                                     text=True, capture_output=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = figma_bridge.inspect_readback(root / 'readback.json', root / 'source.json', root / 'build/expected-native-handoff.json')
            self.assertTrue(result['matches_supplied_source'], result)


if __name__ == '__main__':
    unittest.main()
