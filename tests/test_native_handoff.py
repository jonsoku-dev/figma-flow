"""Local fixtures test evidence validation, not live Figma provenance."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
SPEC = importlib.util.spec_from_file_location('native_handoff', ROOT / 'tools/native_handoff.py')
handoff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handoff)


def fixture():
    alias = {'type': 'VARIABLE_ALIAS', 'id': 'v:semantic'}
    data = {'fileKey': 'fixture', 'pageId': '1:1', 'nodes': [
        {'id': '1:2', 'semanticKey': 'screen', 'type': 'FRAME', 'parentId': '1:1',
         'annotations': [{'label': 'Campaign screen'}], 'width': 1440},
        {'id': '1:3', 'semanticKey': 'screen.play', 'type': 'INSTANCE', 'parentId': '1:2',
         'mainComponentId': '1:5', 'annotations': [{'label': 'ACT-PLAY idle playing; toggle audio'}],
         'fills': [{'type': 'SOLID', 'boundVariables': {'color': alias}}]},
        {'id': '1:4', 'semanticKey': 'components.play', 'type': 'COMPONENT_SET', 'parentId': '1:1'},
        {'id': '1:5', 'semanticKey': 'components.play/idle', 'type': 'COMPONENT', 'parentId': '1:4',
         'variantProperties': {'State': 'idle'}}],
        'collections': [{'id': 'c:1', 'name': 'Tokens', 'modes': [{'modeId': 'm:1', 'name': 'Light'}, {'modeId': 'm:2', 'name': 'Dark'}]}],
        'variables': [
            {'id': 'v:raw', 'name': 'palette.brand', 'variableCollectionId': 'c:1', 'resolvedType': 'COLOR',
             'valuesByMode': {'m:1': {'r': 1, 'g': 0, 'b': 0}, 'm:2': {'r': 0, 'g': 0, 'b': 1}}},
            {'id': 'v:semantic', 'name': 'color.brand', 'variableCollectionId': 'c:1', 'resolvedType': 'COLOR',
             'valuesByMode': {'m:1': {'type': 'VARIABLE_ALIAS', 'id': 'v:raw'},
                              'm:2': {'type': 'VARIABLE_ALIAS', 'id': 'v:raw'}}}]}
    contract = {'collection_name': 'Tokens', 'variables': [{'name': 'color.brand', 'resolved_type': 'COLOR'}],
                'screens': [{'key': 'screen', 'controls': [{'key': 'screen.play', 'action': 'ACT-PLAY',
                    'states': ['idle', 'playing'], 'component_key': 'components.play/idle',
                    'token_bindings': [{'property': 'fills.0.color', 'variable': 'color.brand'}]}]}]}
    return data, contract


def attach_design_note_board(data, expected):
    entries = []
    for screen in expected['screens']:
        for wanted in [screen] + screen['controls']:
            node = next(node for node in data['nodes'] if node.get('semanticKey') == wanted.get('key') or node['id'] == wanted.get('id'))
            key = wanted.get('key', node['id'])
            entries.append({'key': key, 'target_key': node.get('semanticKey'), 'label': '\n'.join(note['label'] for note in node['annotations'])})
    expected['design_note_board'] = {'required': True, 'key': 'design-note-board', 'entries': entries}
    data['nodes'].append({'id': 'note-board', 'semanticKey': 'design-note-board', 'type': 'FRAME',
        'parentId': data['pageId'], 'visible': True, 'clipsContent': False, 'layoutMode': 'VERTICAL', 'itemSpacing': 24,
        'absoluteBoundingBox': {'x': 0, 'y': 0, 'width': 760, 'height': 1000}})
    for index, entry in enumerate(entries):
        target = next(node for node in data['nodes'] if node.get('semanticKey') == entry['target_key'])
        data['nodes'].append({'id': 'note-' + str(index), 'semanticKey': 'design-note-board:' + entry['key'],
            'parentId': 'note-board', 'type': 'TEXT', 'visible': True, 'fontSize': 16, 'textAutoResize': 'HEIGHT',
            'characters': entry['label'], 'hyperlink': {'type': 'NODE', 'value': target['id']},
            'absoluteBoundingBox': {'x': 24, 'y': 24 + index * 200, 'width': 712, 'height': 160}})


class NativeHandoffTest(unittest.TestCase):
    def test_flat_current_native_evidence_and_actual_spec(self):
        data, expected = fixture()
        result = handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        control = result['screens'][0]['controls'][0]
        self.assertEqual(control['main_component']['id'], '1:5')
        self.assertEqual(control['bindings'][0]['variable']['resolved_modes']['m:2'],
                         {'value': {'r': 0, 'g': 0, 'b': 1}, 'alias_chain': ['v:semantic', 'v:raw']})
        self.assertEqual(result['screens'][0]['observed']['width'], 1440)
        self.assertIn('node-id=1-2', result['screens'][0]['url'])
        self.assertNotIn('disabled', handoff.markdown(result))

    def test_korean_spec_includes_actual_additional_annotated_screen_nodes(self):
        data, expected = fixture()
        data['nodes'][0].update(name='오디오 캠페인', height=900)
        data['nodes'][1]['name'] = '재생 버튼'
        data['nodes'][3]['name'] = '재생 / 대기'
        for index, (key, label) in enumerate((
                ('start', '시작: 첫 재생을 시작한다. 차단되면 재시도를 안내한다.'),
                ('volume', '음량: 슬라이더로 볼륨을 조정한다. 0은 음소거 상태다.'),
                ('motion', '움직임: 애니메이션을 켜거나 끈다.'),
                ('language', '언어: 한국어와 일본어 화면 문구를 전환한다.'))):
            data['nodes'].append({'id': f'2:{index}', 'name': key, 'type': 'FRAME', 'parentId': '1:2',
                'annotations': [{'label': f'[figma-flow:screen.{key}] {label}', 'properties': [{'type': 'width'}]}],
                'reactions': [{'trigger': {'type': 'ON_CLICK'}, 'actions': []}],
                'boundVariables': {'cornerRadius': {'type': 'VARIABLE_ALIAS', 'id': 'v:semantic'}}})
        data['nodes'] += [
            {'id': '3:1', 'type': 'FRAME', 'parentId': 'other', 'annotations': [{'label': '외부 화면 설명'}]},
            {'id': '3:2', 'type': 'FRAME', 'parentId': '1:2', 'annotations_status': 'unavailable',
             'annotations': [{'label': '관측하지 못한 설명'}]}]
        data['nodes'][2]['annotations'] = [{'label': '화면 밖 라이브러리 설명'}]
        result = handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        extras = result['screens'][0]['additional_annotations']
        self.assertEqual([n['id'] for n in extras], ['2:0', '2:1', '2:2', '2:3'])
        self.assertEqual(extras[0]['annotation_details'][0]['properties'], [{'type': 'width'}])
        self.assertEqual(extras[0]['observed']['reactions'][0]['trigger']['type'], 'ON_CLICK')
        self.assertEqual(extras[0]['bindings'][0]['variable']['name'], 'color.brand')
        document = handoff.markdown(result)
        for text in ('네이티브 화면 명세', '오디오 캠페인', '1440 × 900 px', '재생 / 대기',
                     'State=idle', 'color.brand', 'node-id=1-5', 'node-id=2-0', '음량:', '언어:'):
            self.assertIn(text, document)
        for absent in ('```json', 'resolved_modes', '[figma-flow:', '외부 화면 설명', '화면 밖 라이브러리 설명', '관측하지 못한 설명'):
            self.assertNotIn(absent, document)
        data['nodes'][1].pop('annotations')
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_native_state_coverage_requires_actual_sibling_variants_when_requested(self):
        data, expected = fixture()
        control = expected['screens'][0]['controls'][0]
        control['native_state_property'] = 'State'
        blocked = handoff.evaluate(data, expected)
        self.assertFalse(blocked['passed'])
        self.assertTrue(any('missing native component state variants' in error for error in blocked['errors']))
        playing = {'id': '1:6', 'name': '재생 중', 'type': 'COMPONENT', 'parentId': '1:4',
                   'variantProperties': {'State': 'playing'}}
        data['nodes'].append(playing)
        passed = handoff.evaluate(data, expected)
        self.assertTrue(passed['passed'], passed['errors'])
        self.assertEqual(passed['screens'][0]['controls'][0]['covered_native_states'], ['idle', 'playing'])
        self.assertIn('node-id=1-6', handoff.markdown(passed))
        playing['parentId'] = 'other-set'
        self.assertFalse(handoff.evaluate(data, expected)['passed'])
        playing['parentId'] = '1:4'
        playing['type'] = 'FRAME'
        self.assertFalse(handoff.evaluate(data, expected)['passed'])
        playing['type'] = 'COMPONENT'
        control['state_variants'] = {'idle': 'idle', 'playing': 'Active'}
        self.assertFalse(handoff.evaluate(data, expected)['passed'])
        playing['variantProperties']['State'] = 'Active'
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        control['state_variants'] = ['idle', 'Active']
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        control['state_variants'] = {'idle': 'idle'}
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_static_screen_and_real_static_reusable_instance_preserve_native_gate(self):
        data, expected = fixture()
        control = expected['screens'][0]['controls'][0]
        control.pop('action')
        control.pop('states')
        control['static'] = True
        data['nodes'][3].pop('variantProperties')
        data['nodes'][3]['parentId'] = '1:1'
        data['nodes'].append({'id': '4:1', 'type': 'FRAME', 'name': '정적 안내', 'parentId': '1:1',
                              'annotations': [{'label': '제품 정보와 안내 문구'}]})
        expected['screens'].append({'id': '4:1', 'static': True, 'controls': []})
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        expected['screens'][0].update(static=True, controls=[])
        self.assertFalse(handoff.evaluate(data, expected)['passed'])
        expected['screens'][0]['controls'] = [control]
        data['nodes'][1]['reactions'] = [{'trigger': {'type': 'ON_CLICK'}}]
        self.assertFalse(handoff.evaluate(data, expected)['passed'])
        data['nodes'][1].pop('reactions')
        data['nodes'][1].pop('fills')
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_collection_semantic_key_page_pin_and_descendant_binding(self):
        data, expected = fixture()
        expected.pop('collection_name')
        expected['collection_key'] = 'token-collection'
        data['collections'][0]['semantic_id'] = 'token-collection'
        data['nodes'].append({'id': '1:1', 'type': 'PAGE', 'declared_metadata': {'collection_id': 'c:1'}})
        label = {'id': '5:1', 'type': 'TEXT', 'semantic_id': 'screen.play/label', 'parentId': '1:3',
                 'fills': data['nodes'][1].pop('fills')}
        data['nodes'].append(label)
        expected['screens'][0]['controls'][0]['token_bindings'][0]['node_key'] = 'screen.play/label'
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        label['parentId'] = '1:2'
        self.assertFalse(handoff.evaluate(data, expected)['passed'])
        label['parentId'] = '1:3'
        data['nodes'][-2]['declared_metadata']['collection_id'] = 'unrelated'
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_standard_nested_bridge_snake_main_component(self):
        data, expected = fixture()
        flat = data.pop('nodes')
        by_id = {n['id']: n for n in flat}
        page = {'id': '1:1', 'type': 'PAGE', 'children': []}
        for n in flat:
            parent = n.pop('parentId')
            (page if parent == '1:1' else by_id[parent]).setdefault('children', []).append(n)
            if 'mainComponentId' in n:
                n['main_component_id'] = n.pop('mainComponentId')
            n['semantic_id'] = n.pop('semanticKey')
        data.pop('pageId')
        data['format'] = 'figma-flow-readback-v1'
        data['pages'] = [page]
        self.assertTrue(handoff.evaluate(data, expected, '1:1')['passed'])

    def test_fail_closed_mutations(self):
        def wrong_type(d, _): d['nodes'][1]['type'] = 'FRAME'
        def fake_set(d, _): d['nodes'][2]['type'] = 'FRAME'
        def no_variants(d, _): d['nodes'][3].pop('variantProperties')
        def wrong_component(d, _): d['nodes'][1]['mainComponentId'] = 'outside'
        def plugin_notes(d, _):
            for n in d['nodes']:
                n['declared_metadata'] = {'annotation': str(n.pop('annotations', []))}
        def unrelated_note(d, _):
            d['nodes'][0]['annotations'] += d['nodes'][1].pop('annotations')
        def wrong_binding(d, _): d['nodes'][1]['fills'][0]['boundVariables']['color']['id'] = 'v:raw'
        def metadata_binding(d, _):
            d['nodes'][1]['declared_metadata'] = {'boundVariables': d['nodes'][1].pop('fills')}
        def alias_cycle(d, _): d['variables'][0]['valuesByMode']['m:2'] = {'type': 'VARIABLE_ALIAS', 'id': 'v:semantic'}
        def missing_mode(d, _): d['variables'][0]['valuesByMode'].pop('m:2')
        def wrong_collection(d, _): d['variables'][0]['variableCollectionId'] = 'other'
        def unobserved_state(d, _): d['nodes'][1]['annotations'] = [{'label': 'ACT-PLAY idle'}]
        def dummy_control(_, e): e['screens'][0]['controls'].append({'key': 'save'})
        def no_controls(_, e): e['screens'][0]['controls'] = []
        def misleading_state(d, e):
            e['screens'][0]['controls'][0]['states'] = ['enabled']
            d['nodes'][1]['annotations'] = [{'label': 'ACT-PLAY disabled'}]
        def wrong_page(d, _): d['nodes'][0]['parentId'] = 'other'
        def duplicate(d, _): d['nodes'].append(copy.deepcopy(d['nodes'][1]))
        def duplicate_key(d, _): d['nodes'][3]['semanticKey'] = 'screen.play'
        def unavailable_annotation(d, _): d['nodes'][1]['annotations_status'] = 'unavailable'
        for mutation in (wrong_type, fake_set, no_variants, wrong_component, plugin_notes, unrelated_note,
                         wrong_binding, metadata_binding, alias_cycle, missing_mode, wrong_collection,
                         unobserved_state, dummy_control, no_controls, wrong_page, duplicate,
                         duplicate_key, unavailable_annotation, misleading_state):
            with self.subTest(mutation=mutation.__name__):
                data, expected = fixture()
                mutation(data, expected)
                result = handoff.evaluate(data, expected)
                self.assertFalse(result['passed'], result)
                self.assertTrue(result['errors'])

    def test_direct_scalar_native_binding_and_singleton_array(self):
        data, expected = fixture()
        data['variables'].append({'id': 'v:radius', 'name': 'radius.control',
            'variableCollectionId': 'c:1', 'resolvedType': 'FLOAT',
            'valuesByMode': {'m:1': 8, 'm:2': 10}})
        expected['variables'].append({'name': 'radius.control'})
        expected['screens'][0]['controls'][0]['token_bindings'].append(
            {'property': 'cornerRadius', 'variable_id': 'v:radius'})
        data['nodes'][1]['boundVariables'] = {'cornerRadius': [{'type': 'VARIABLE_ALIAS', 'id': 'v:radius'}]}
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        data['nodes'][1]['boundVariables']['cornerRadius'].append({'type': 'VARIABLE_ALIAS', 'id': 'v:radius'})
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_strict_creation_requires_structured_semantics_without_changing_history(self):
        data, expected = fixture()
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        expected['mode'] = 'strict-creation'
        strict = handoff.evaluate(data, expected)
        self.assertFalse(strict['passed'])
        self.assertIn('annotation_contract', strict)
        expected['annotation_contract'] = {'mode': 'strict-creation', 'product_graph': {'nodes': []}, 'notes': []}
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_strict_creation_real_annotations_cover_every_required_native_node(self):
        from annotation_contract import derive_notes
        data, expected = fixture()
        graph = {'nodes': [
            {'id': 'SCR-HOME', 'type': 'screen', 'annotation': {'purpose': '캠페인 재생 상태를 확인한다.',
                'journey': '대기 중인 음악을 재생하고 상태 변화를 확인한다.', 'first_action': 'ACT-PLAY'}},
            {'id': 'ACT-PLAY', 'type': 'action', 'source_screen': 'SCR-HOME', 'annotation': {
                'control_id': 'screen.play', 'purpose': '현재 캠페인의 음악을 재생한다.',
                'behavior': '누르면 재생 상태를 전환한다.', 'result': '현재 음악의 재생 상태를 표시한다.',
                'functional_states': ['STATE-IDLE', 'STATE-PLAYING']}},
            {'id': 'STATE-IDLE', 'type': 'state'}, {'id': 'STATE-PLAYING', 'type': 'state'}]}
        notes = derive_notes(graph)
        notes[0]['native_key'] = 'screen'
        for node, note in zip(data['nodes'][:2], notes):
            node['annotations'][0]['label'] += ' ' + ' '.join(
                value if isinstance(value, str) else ' '.join(value)
                for key, value in note.items() if key in ('purpose', 'journey', 'first_action', 'behavior', 'result', 'action', 'functional_states'))
        expected.update(mode='strict-creation', annotation_contract={
            'mode': 'strict-creation', 'product_graph': graph, 'notes': notes})
        attach_design_note_board(data, expected)
        result = handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        data['nodes'][1]['annotations'][0]['label'] = 'ACT-PLAY idle playing'
        self.assertFalse(handoff.evaluate(data, expected)['passed'])

    def test_strict_static_reusable_sample_requires_actual_canonical_screen_note(self):
        from annotation_contract import derive_notes
        data, expected = fixture()
        control = expected['screens'][0]['controls'][0]
        control.pop('action')
        control.pop('states')
        control['static'] = True
        purpose = '선택한 디자인의 정적 컴포넌트 사용 예를 보여준다.'
        journey = '사용자는 실제 화면의 배치와 간격을 살펴본다.'
        graph = {'nodes': [{'id': 'SCR-SAMPLE', 'type': 'screen', 'annotation': {
            'purpose': purpose, 'journey': journey}}]}
        notes = derive_notes(graph)
        notes[0]['native_key'] = 'screen'
        control['static_annotation'] = '샘플 사용 사례: 내용 확인용 버튼. ' + purpose + ' ' + journey
        data['nodes'][0]['annotations'] = [{'label': purpose + ' ' + journey}]
        data['nodes'][1]['annotations'] = [{'label': control['static_annotation']}]
        expected.update(mode='strict-creation', annotation_contract={
            'mode': 'strict-creation', 'product_graph': graph, 'notes': notes})
        attach_design_note_board(data, expected)
        result = handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        self.assertIsNone(result['screens'][0]['controls'][0]['covered_action'])
        for mutation in ('missing declaration', 'placeholder', 'wrong note', 'bad component', 'missing binding', 'fake static action'):
            changed_data, changed_expected = copy.deepcopy(data), copy.deepcopy(expected)
            changed_control = changed_expected['screens'][0]['controls'][0]
            if mutation == 'missing declaration':
                changed_control.pop('static_annotation')
            elif mutation == 'placeholder':
                changed_control['static_annotation'] = 'Control sample placeholder'
                changed_data['nodes'][1]['annotations'] = [{'label': changed_control['static_annotation']}]
            elif mutation == 'wrong note':
                changed_data['nodes'][1]['annotations'] = [{'label': '다른 화면의 컴포넌트 설명'}]
            elif mutation == 'bad component':
                changed_data['nodes'][1]['mainComponentId'] = 'outside'
            elif mutation == 'missing binding':
                changed_data['nodes'][1].pop('fills')
            else:
                changed_control['action_id'] = 'ACT-HIDDEN'
            self.assertFalse(handoff.evaluate(changed_data, changed_expected)['passed'], mutation)

    def test_strict_declared_navigation_requires_actual_getter_destination(self):
        from annotation_contract import derive_notes, TEXT_FIELDS
        data, expected = fixture()
        graph = {'nodes': [
            {'id': 'SCR-HOME', 'type': 'screen', 'annotation': {'purpose': '참여할 다음 화면을 선택한다.',
                'journey': '대기 화면에서 다음 읽기 화면으로 이동한다.', 'first_action': 'ACT-PLAY'}},
            {'id': 'ACT-PLAY', 'type': 'action', 'source_screen': 'SCR-HOME', 'target_ids': ['SCR-END'],
             'annotation': {'control_id': 'screen.play', 'purpose': '다음 참여 화면으로 이동한다.',
                'behavior': '다음 화면의 본문을 연다.', 'result': '선택한 본문 화면을 표시한다.',
                'functional_states': ['ST-READY']}},
            {'id': 'SCR-END', 'type': 'screen', 'annotation': {'purpose': '선택한 본문 내용을 읽는다.',
                'journey': '본문을 읽고 현재 내용을 확인한다.'}}, {'id': 'ST-READY', 'type': 'state'}]}
        notes = derive_notes(graph)
        notes[0]['native_key'] = 'screen'
        data['nodes'].append({'id': '1:6', 'semanticKey': 'SCR-END', 'type': 'FRAME', 'parentId': '1:1'})
        mapping = {'SCR-HOME': data['nodes'][0], 'ACT-PLAY': data['nodes'][1], 'SCR-END': data['nodes'][-1]}
        for note in notes:
            meaning = ' '.join(note[field] for field in TEXT_FIELDS + ('action', 'first_action') if field in note)
            mapping[note['id']]['annotations'] = [{'label': meaning + ' idle playing ' + ' '.join(note.get('functional_states', []))}]
        expected['screens'].append({'key': 'SCR-END', 'static': True, 'controls': []})
        expected['screens'][0]['controls'][0]['target_screen'] = 'SCR-END'
        expected.update(mode='strict-creation', annotation_contract={'mode': 'strict-creation', 'product_graph': graph, 'notes': notes})
        data['nodes'][1]['reactions'] = [{'trigger': {'type': 'ON_CLICK'}, 'actions': [
            {'type': 'NODE', 'navigation': 'NAVIGATE', 'destinationId': '1:6'}]}]
        attach_design_note_board(data, expected)
        result = handoff.evaluate(data, expected)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['prototype_checks'][0]['destination_id'], '1:6')
        for reactions in ([], [{'trigger': {'type': 'ON_CLICK'}, 'actions': [
                {'type': 'NODE', 'navigation': 'NAVIGATE', 'destinationId': '1:2'}]}]):
            changed = copy.deepcopy(data)
            changed['nodes'][1]['reactions'] = reactions
            self.assertFalse(handoff.evaluate(changed, expected)['passed'])
        graph['nodes'][1]['target_ids'] = ['SCR-HOME']
        expected['screens'][0]['controls'][0]['target_screen'] = 'SCR-HOME'
        data['nodes'][1]['reactions'][0]['actions'][0]['destinationId'] = '1:2'
        self.assertTrue(handoff.evaluate(data, expected)['passed'])

    def test_design_mode_note_board_links_text_and_containment_fail_closed(self):
        data, expected = fixture()
        attach_design_note_board(data, expected)
        self.assertTrue(handoff.evaluate(data, expected)['passed'])
        for mutation in ('wrong target', 'hidden', 'outside', 'no text', 'no link', 'wrong parent', 'small text', 'overlap', 'missing target'):
            changed_data, changed_expected = copy.deepcopy(data), copy.deepcopy(expected)
            note = changed_data['nodes'][-1]
            if mutation == 'wrong target': note['hyperlink']['value'] = 'unrelated'
            elif mutation == 'hidden': note['visible'] = False
            elif mutation == 'outside': note['absoluteBoundingBox']['x'] = 800
            elif mutation == 'no text': note['characters'] = 'placeholder'
            elif mutation == 'no link': note.pop('hyperlink')
            elif mutation == 'wrong parent': note['parentId'] = '1:2'
            elif mutation == 'small text': note['fontSize'] = 9
            elif mutation == 'overlap': note['absoluteBoundingBox']['y'] = 24
            else: changed_expected['design_note_board']['entries'].pop()
            self.assertFalse(handoff.evaluate(changed_data, changed_expected)['passed'], mutation)

    def test_missing_contract_and_readback_never_pass(self):
        data, expected = fixture()
        for readback, contract in ((None, expected), ({}, expected), (data, None), (data, {})):
            self.assertFalse(handoff.evaluate(readback, contract)['passed'])

    def test_cli_outputs_observed_spec_and_refuses_overwrite(self):
        data, expected = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'readback.json').write_text(json.dumps(data))
            (root / 'contract.json').write_text(json.dumps(expected))
            args = [sys.executable, str(ROOT / 'tools/native_handoff.py'), '--readback', str(root / 'readback.json'),
                    '--contract', str(root / 'contract.json'), '--page-id', '1:1', '--out', str(root / 'out')]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(p.name for p in (root / 'out').iterdir()), {'report.json', 'screen-spec.json', 'screen-spec.md'})
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            data['nodes'][1].pop('annotations')
            (root / 'readback.json').write_text(json.dumps(data))
            args[-1] = str(root / 'blocked')
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 1)
            self.assertEqual(json.loads((root / 'blocked/report.json').read_text())['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
