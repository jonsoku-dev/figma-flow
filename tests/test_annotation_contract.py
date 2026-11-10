"""Fixture evidence validates semantic contracts, never live Figma provenance."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location('annotation_contract', TOOLS / 'annotation_contract.py')
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def fixture():
    graph = {'nodes': [
        {'id': 'SCR-HOME', 'type': 'screen', 'annotation': {
            'purpose': '편지를 읽고 배달할 목적지를 고른다.', 'first_action': 'ACT-DELIVER',
            'journey': '대기 상태에서 선택한 목적지로 배달을 시작한다.',
            'design_choice': '두 목적지의 단서를 나란히 비교한다.'}},
        {'id': 'ACT-DELIVER', 'type': 'action', 'source_screen': 'SCR-HOME',
         'target_ids': ['STATE-DELIVERED'], 'annotation': {
             'control_id': 'home.deliver', 'purpose': '고른 목적지로 편지를 배달한다.',
             'behavior': '선택한 목적지에 맞는 답장 화면을 연다.',
             'precondition': '목적지를 하나 고른 뒤 사용할 수 있다.',
             'result': '현재 답장과 배달 완료 상태를 표시한다.',
             'failure': '배달에 실패하면 편지를 유지하고 재시도를 안내한다.',
             'functional_states': ['STATE-IDLE', 'STATE-DELIVERED'], 'visual_variant': 'Primary'}},
        {'id': 'STATE-IDLE', 'type': 'state', 'title': '배달 전'},
        {'id': 'STATE-DELIVERED', 'type': 'state', 'title': '배달 완료'}], 'edges': []}
    notes = contract.derive_notes(graph)
    source = '<main id="SCR-HOME"><button id="home.deliver">배달</button></main>'
    review = '<p>계획 주석 · Figma 네이티브 관측 아님 (planned, not native)</p>'
    for note in notes:
        review += '<section><a href="#' + note['target_id'] + '">대상 확인</a>'
        review += ''.join('<p>' + note[field] + '</p>' for field in contract.TEXT_FIELDS if field in note)
        review += '</section>'
    return graph, notes, source, review


def native_fixture():
    graph, notes, _, _ = fixture()
    nodes = [{'id': 'p', 'type': 'PAGE'}, {'id': 's', 'type': 'FRAME', 'semanticKey': 'SCR-HOME', 'parentId': 'p'},
             {'id': 'b', 'type': 'INSTANCE', 'semanticKey': 'home.deliver', 'parentId': 's'}]
    for node, note in zip(nodes[1:], notes):
        fields = [note[field] for field in contract.TEXT_FIELDS + ('first_action', 'action', 'visual_variant') if field in note]
        node['annotations'] = [{'label': ' '.join(fields + note.get('functional_states', []))}]
    return {'pageId': 'p', 'nodes': nodes}, {'mode': 'strict-creation', 'product_graph': graph, 'notes': notes}


class AnnotationContractTests(unittest.TestCase):
    def test_canonical_projection_and_visible_linked_planned_review(self):
        graph, notes, source, review = fixture()
        result = contract.validate_notes(notes, graph, source_html=source, review_html=review)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(notes[1]['action'], 'ACT-DELIVER')
        self.assertEqual(notes[1]['functional_states'], ['STATE-IDLE', 'STATE-DELIVERED'])
        self.assertEqual(notes[1]['visual_variant'], 'Primary')
        self.assertNotIn('failure', notes[0])

    def test_one_canonical_action_covers_every_declared_control_instance(self):
        graph, _, _, _ = fixture()
        meaning = graph['nodes'][1]['annotation']
        meaning.pop('control_id')
        meaning['control_ids'] = ['list-spacing', 'list-retrieval', 'list-feedback', 'list-interleave']
        notes = contract.derive_notes(graph)
        self.assertEqual([note['id'] for note in notes[1:]], ['ACT-DELIVER@' + key for key in meaning['control_ids']])
        self.assertEqual({note['action'] for note in notes[1:]}, {'ACT-DELIVER'})
        self.assertEqual([note['target_id'] for note in notes[1:]], meaning['control_ids'])
        self.assertFalse(contract.validate_notes(notes[:-1], graph)['passed'])
        self.assertTrue(contract.validate_notes(notes, graph)['passed'])
        nodes = [{'id': 'p', 'type': 'PAGE'}]
        for index, note in enumerate(notes):
            label = ' '.join(note[field] for field in contract.TEXT_FIELDS + ('first_action', 'action', 'visual_variant') if field in note)
            label += ' ' + ' '.join(note.get('functional_states', []))
            nodes.append({'id': str(index), 'type': 'FRAME' if index == 0 else 'INSTANCE',
                          'semanticKey': note['target_id'], 'parentId': 'p' if index == 0 else '0',
                          'annotations': [{'label': label}]})
        declaration = {'mode': 'strict-creation', 'product_graph': graph, 'notes': notes}
        self.assertTrue(contract.validate_native_annotations({'pageId': 'p', 'nodes': nodes}, declaration)['passed'])
        nodes[-1]['annotations'] = []
        self.assertFalse(contract.validate_native_annotations({'pageId': 'p', 'nodes': nodes}, declaration)['passed'])
        meaning['control_ids'] = ['list-spacing']
        self.assertEqual(contract.derive_notes(graph)[1]['id'], 'ACT-DELIVER')

    def test_missing_source_semantics_are_not_inferred_or_placeholder_filled(self):
        graph, _, _, _ = fixture()
        for mutate in (lambda g: g['nodes'][1].pop('annotation'),
                       lambda g: g['nodes'][1]['annotation'].update(behavior='TODO'),
                       lambda g: g['nodes'][0]['annotation'].update(first_action='ACT-INVENTED'),
                       lambda g: g['nodes'][1]['annotation'].update(functional_states=['Primary'])):
            broken = copy.deepcopy(graph)
            mutate(broken)
            with self.assertRaises(ValueError):
                contract.derive_notes(broken)

    def test_note_content_must_match_canonical_function_not_component_style(self):
        graph, notes, source, review = fixture()
        for field, value in [('behavior', '다른 목적지로 이동하고 결과를 삭제한다.'),
                             ('functional_states', ['Primary', 'Secondary', 'Quiet']),
                             ('visual_variant', 'Secondary'), ('status', 'observed'),
                             ('provenance', 'actual-native-figma')]:
            broken = copy.deepcopy(notes)
            broken[1][field] = value
            self.assertFalse(contract.validate_notes(broken, graph, source_html=source, review_html=review)['passed'])

    def test_source_anchor_and_review_link_text_and_planned_boundary_are_required(self):
        graph, notes, source, review = fixture()
        for changed_source, changed_review in (
                (source.replace('id="home.deliver"', 'id="other"'), review),
                (source, review.replace('href="#home.deliver"', 'href="#other"')),
                (source, review.replace(notes[1]['failure'], '')),
                (source, '<script>' + review + '</script>'),
                (source, '<div hidden>' + review + '</div>'),
                (source, review.replace('계획 주석 · Figma 네이티브 관측 아님 (planned, not native)', '완료'))):
            result = contract.validate_notes(notes, graph, source_html=changed_source, review_html=changed_review)
            self.assertFalse(result['passed'], result)
        self.assertFalse(contract.validate_notes(notes, graph, source_html=source)['passed'])

    def test_filename_anchor_is_checked_in_the_named_source(self):
        graph, notes, source, review = fixture()
        notes[1]['target'] = 'candidate.html#home.deliver'
        review = review.replace('href="#home.deliver"', 'href="candidate.html#home.deliver"')
        self.assertTrue(contract.validate_notes(notes, graph, source_html={'candidate.html': source}, review_html=review)['passed'])
        self.assertFalse(contract.validate_notes(notes, graph, source_html={'wrong.html': source}, review_html=review)['passed'])

    def test_native_requires_actual_annotations_and_exact_functional_content(self):
        readback, declaration = native_fixture()
        self.assertTrue(contract.validate_native_annotations(readback, declaration)['passed'])
        self.assertFalse(contract.validate_notes(declaration['notes'], declaration['product_graph'], stage='native')['passed'])
        for mutation in ('metadata', 'unavailable', 'wrong function', 'wrong state'):
            current = copy.deepcopy(readback)
            node = current['nodes'][2]
            if mutation == 'metadata':
                node['declared_metadata'] = {'annotations': node.pop('annotations')}
            elif mutation == 'unavailable':
                node['annotations_status'] = 'unavailable'
            elif mutation == 'wrong function':
                node['annotations'][0]['label'] = node['annotations'][0]['label'].replace('선택한 목적지에 맞는 답장 화면을 연다.', '다른 화면')
            else:
                node['annotations'][0]['label'] = node['annotations'][0]['label'].replace('STATE-DELIVERED', 'Primary')
            self.assertFalse(contract.validate_native_annotations(current, declaration)['passed'], mutation)

    def test_native_claims_do_not_accept_plain_button_or_visual_functional_states(self):
        readback, declaration = native_fixture()
        readback['nodes'][2].update(layoutMode='HORIZONTAL', layoutSizingHorizontal='HUG')
        readback['nodes'][2]['annotations'][0]['label'] += ' Content hug responsive nine-slice skin; edit 문구. States: Primary, Secondary, Quiet.'
        report = contract.validate_native_annotations(readback, declaration)
        self.assertFalse(report['passed'])
        self.assertTrue(any('nine-slice' in error for error in report['errors']))
        self.assertTrue(any('visual variants' in error for error in report['errors']))
        self.assertFalse(any('content-hug' in error for error in report['errors']))

    def test_native_nine_slice_claim_needs_native_image_regions_and_constraints(self):
        readback, declaration = native_fixture()
        readback['nodes'][2]['annotations'][0]['label'] += ' Nine-slice skin.'
        readback['nodes'][2].update(width=60, height=60)
        constraints = {'tl': ('MIN', 'MIN'), 't': ('STRETCH', 'MIN'), 'tr': ('MAX', 'MIN'),
                       'l': ('MIN', 'STRETCH'), 'c': ('STRETCH', 'STRETCH'), 'r': ('MAX', 'STRETCH'),
                       'bl': ('MIN', 'MAX'), 'b': ('STRETCH', 'MAX'), 'br': ('MAX', 'MAX')}
        for index, (suffix, (horizontal, vertical)) in enumerate(constraints.items()):
            readback['nodes'].append({'id': 'slice-' + suffix, 'parentId': 'b', 'name': 'button.skin.' + suffix,
                'type': 'RECTANGLE', 'x': index % 3 * 20, 'y': index // 3 * 20, 'width': 20, 'height': 20,
                'constraints': {'horizontal': horizontal, 'vertical': vertical},
                'fills': [{'type': 'IMAGE', 'imageHash': suffix}]})
        self.assertTrue(contract.validate_native_annotations(readback, declaration)['passed'])
        readback['nodes'][-1]['fills'] = []
        self.assertFalse(contract.validate_native_annotations(readback, declaration)['passed'])


if __name__ == '__main__':
    unittest.main()
