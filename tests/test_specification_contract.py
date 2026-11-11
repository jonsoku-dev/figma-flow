"""Local supplied-artifact tests; no Figma origin or runtime claims."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import specification_contract as contract


def fixture():
    graph = {'nodes': [
        {'id': 'screen', 'type': 'screen', 'title': '편지함', 'source': 'brief.md', 'annotation': {
            'purpose': '받은 편지를 읽고 목적지를 고른다.', 'journey': '편지를 고른 뒤 배달을 시작한다.',
            'first_action': 'deliver', 'design_choice': '목적지의 단서를 나란히 비교한다.'}},
        {'id': 'deliver', 'type': 'action', 'title': '편지 배달', 'source_screen': 'screen',
         'source': 'brief.md', 'annotation_authority': {'reference': 'brief.md', 'version': 2},
         'annotation': {'purpose': '고른 목적지로 편지를 배달한다.', 'behavior': '선택한 목적지의 답장 화면을 연다.',
                        'result': '답장과 배달 완료 상태를 표시한다.', 'control_id': 'button.deliver',
                        'functional_states': ['idle'], 'visual_variant': 'Primary'}},
        {'id': 'idle', 'type': 'state', 'title': '배달 전'},
        {'id': 'req', 'type': 'requirement', 'title': '편지를 배달한다.', 'source': 'brief.md'},
        {'id': 'ac', 'type': 'acceptance', 'title': '답장을 표시한다.', 'status': 'unverified'},
        {'id': 'test', 'type': 'test', 'title': '배달 결과 검사', 'status': 'unverified'}],
        'edges': [{'from': 'req', 'to': 'screen', 'type': 'appears on'},
                  {'from': 'req', 'to': 'ac', 'type': 'accepted by'},
                  {'from': 'ac', 'to': 'test', 'type': 'checked by'}]}
    return graph


def wrapper(spec):
    board = {'boardId': 'board:1', 'textNodeId': 'text:1', 'key': 'deliver'}
    result = {'schema': contract.NATIVE_SCHEMA, 'semantic_key': spec['target_id'], 'target_id': 'native:1',
            'source_owner_hash': 'b' * 64, 'specification': copy.deepcopy(spec),
            'legacy_annotations': [{'index': 0, 'annotation': {'label': 'Keep me'}}], 'state': 'applied'}
    if spec.get('presentation') == 'connected-spec-v2':
        connected = contract.connected_annotation_markdown(spec, 'file key', board['textNodeId'])
        raw = {'labelMarkdown': connected['markdown']}
        result.update(human_annotation={'schema': 'figma-flow-human-annotation-v1', 'index': 1, 'annotation': raw,
                                        'board': board, 'url': connected['url']},
                      _annotations=[{'label': 'Keep me'}, raw], _board_ref=board)
    return result


def validate(spec, observed):
    return contract.validate_specification(spec, observed, native_id='native:1', source_owner_hash='b' * 64,
                                           annotations=observed.get('_annotations'), file_key='file key',
                                           board_ref=observed.get('_board_ref'))


class SpecificationContractTests(unittest.TestCase):
    def test_existing_meaning_verbatim_with_optional_precondition_and_technical_ids_separate(self):
        graph = fixture()
        spec = contract.derive_specifications(graph)[1]
        self.assertEqual(spec['title'], '편지 배달')
        for field, value in graph['nodes'][1]['annotation'].items():
            self.assertEqual(spec['meaning'][field], value)
        self.assertEqual(spec['meaning']['action'], 'deliver')
        self.assertEqual([section['key'] for section in spec['sections']], ['purpose', 'behavior', 'result'])
        self.assertEqual(spec['annotation_text'], graph['nodes'][1]['annotation']['behavior'])
        self.assertIn('목적\n' + graph['nodes'][1]['annotation']['purpose'], spec['display_text'])
        for technical in ('button.deliver', 'idle', 'Primary', 'first_action'):
            self.assertNotIn(technical, spec['display_text'])
        graph['nodes'][1]['annotation']['precondition'] = '목적지를 하나 고른 뒤 사용할 수 있다.'
        self.assertIn(graph['nodes'][1]['annotation']['precondition'], contract.derive_specifications(graph)[1]['display_text'])
        del graph['nodes'][1]['annotation']
        with self.assertRaises(ValueError):
            contract.derive_specifications(graph)

    def test_hash_changes_only_for_target_meaning_not_global_revision(self):
        graph = fixture()
        before = contract.derive_specifications(graph)
        graph['nodes'][1]['annotation']['behavior'] = '선택한 목적지의 편지 내용을 표시한다.'
        after = contract.derive_specifications(graph)
        self.assertEqual(before[0]['meaning_sha256'], after[0]['meaning_sha256'])
        self.assertNotEqual(before[1]['meaning_sha256'], after[1]['meaning_sha256'])
        self.assertNotEqual(before[0]['source_graph_sha256'], after[0]['source_graph_sha256'])
        supplied = contract.derive_specifications(graph, source_graph_sha256='a' * 64)
        self.assertEqual(supplied[1]['meaning_sha256'], after[1]['meaning_sha256'])
        self.assertEqual(supplied[1]['source_graph_encoding'], 'file-bytes-sha256')

    def test_exact_supplied_wrapper_and_binding_required(self):
        spec = contract.derive_specifications(fixture())[1]
        self.assertTrue(validate(spec, wrapper(spec))['passed'])
        for field in ('semantic_key', 'target_id', 'source_owner_hash', 'state', 'specification', 'legacy_annotations'):
            observed = wrapper(spec)
            del observed[field]
            self.assertFalse(validate(spec, observed)['passed'], field)
        for field, value in [('semantic_key', 'other'), ('target_id', 'native:2'),
                             ('source_owner_hash', 'c' * 64), ('state', 'pending'), ('state', 'conflict')]:
            observed = wrapper(spec)
            observed[field] = value
            self.assertFalse(validate(spec, observed)['passed'], field)
        self.assertFalse(contract.validate_specification(spec, wrapper(spec))['passed'])

    def test_plausible_body_tampering_or_stale_revision_fails(self):
        spec = contract.derive_specifications(fixture())[1]
        for field, value in [('display_text', '고른 목적지로 이동한다.'), ('title', '다른 제목'),
                             ('source_graph_sha256', 'c' * 64), ('source_graph_encoding', 'unknown'),
                             ('meaning_sha256', 'd' * 64), ('meaning', {'purpose': '그럴듯한 설명이다.'})]:
            observed = wrapper(spec)
            observed['specification'][field] = value
            self.assertFalse(validate(spec, observed)['passed'], field)
        observed = wrapper(spec)
        observed['specification']['schema'] = 'older-schema'
        self.assertFalse(validate(spec, observed)['passed'])

    def test_actual_graph_relationships_and_external_refs_never_claim_read_or_acceptance(self):
        graph = fixture()
        spec = contract.derive_specifications(graph)[1]
        trace = spec['trace']
        self.assertEqual(trace['relationships'], sorted(graph['edges'], key=lambda e: (e['from'], e['type'], e['to'])))
        self.assertEqual(trace['tests'][0]['status'], 'unverified')
        self.assertEqual(trace['source_authority']['annotation_authority'], {'reference': 'brief.md', 'version': 2})
        self.assertIn('not read', trace['authority_basis'])
        self.assertEqual(trace['status'], 'complete')  # Link coverage, not acceptance outcome.
        for edges, status in [(graph['edges'][:-1], 'partial'), ([], 'unverified')]:
            changed = copy.deepcopy(graph)
            changed['edges'] = edges
            current = contract.derive_specifications(changed)[1]
            self.assertEqual(current['trace']['status'], status)
            report = validate(current, wrapper(current))
            self.assertFalse(report['passed'])
            self.assertTrue(report['unverified'])
        changed = copy.deepcopy(graph)
        changed['nodes'][1]['source_screen'] = 'not-a-screen'
        with self.assertRaises(ValueError):
            contract.derive_specifications(changed)

    def test_unrelated_graph_edit_and_expanded_control_identity(self):
        graph = fixture()
        initial = contract.derive_specifications(graph)
        graph['nodes'].append({'id': 'unrelated', 'type': 'state', 'title': '다른 상태'})
        changed = contract.derive_specifications(graph)
        self.assertEqual([s['meaning_sha256'] for s in initial], [s['meaning_sha256'] for s in changed])
        graph['nodes'][1]['annotation'].pop('control_id')
        graph['nodes'][1]['annotation']['control_ids'] = ['button.one', 'button.two']
        expanded = contract.derive_specifications(graph)[1:]
        self.assertEqual([s['id'] for s in expanded], ['deliver@button.one', 'deliver@button.two'])
        self.assertNotEqual(expanded[0]['meaning_sha256'], expanded[1]['meaning_sha256'])
        self.assertEqual(expanded[0]['meaning']['action'], 'deliver')

    def test_render_uses_canonical_meaning_and_explicit_technical_section(self):
        rendered = contract.render_screen_spec(fixture())
        body, technical = rendered.split('<details>', 1)
        self.assertIn('받은 편지를 읽고 목적지를 고른다.', body)
        self.assertNotIn('first_action', body)
        self.assertIn('Technical references', technical)
        self.assertIn('first_action', technical)
        self.assertIn('not a second source of truth', body)

    def test_projection_locale_summary_hash_and_connected_annotation_are_graph_derived(self):
        graph = fixture()
        graph['specification_locale'] = 'en'
        graph['nodes'][1]['annotation'].update(summary='A short grounded summary.', platform_scope='Available in Figma and web.')
        spec = contract.derive_specifications(graph)[1]
        self.assertEqual(spec['locale'], 'en')
        self.assertEqual(spec['annotation_text'], 'A short grounded summary.')
        self.assertIn('Figma and web scope\n', spec['display_text'])
        forged = copy.deepcopy(spec)
        forged['sections'][0]['body'] = 'plausible text'
        self.assertFalse(contract.validate_specification(forged, wrapper(forged))['passed'])
        markdown = contract.connected_annotation_markdown(spec, 'file key', 'text:1')
        self.assertEqual(markdown['url'], 'https://www.figma.com/design/file%20key?node-id=text-1')
        self.assertIn('[View full specification](', markdown['markdown'])

    def test_connected_annotation_requires_actual_raw_readback_and_board_binding(self):
        spec = contract.derive_specifications(fixture())[1]
        observed = wrapper(spec)
        self.assertTrue(validate(spec, observed)['passed'])
        duplicate = copy.deepcopy(observed['human_annotation']['annotation'])
        duplicate['categoryId'] = 'other-category'
        observed['_annotations'].append(duplicate)
        self.assertFalse(validate(spec, observed)['passed'])
        observed = wrapper(spec)
        self.assertFalse(contract.validate_specification(spec, observed, native_id='native:1', source_owner_hash='b' * 64)['passed'])
        observed['human_annotation']['annotation']['labelMarkdown'] = 'Edited but plausible'
        self.assertFalse(validate(spec, observed)['passed'])
        observed = wrapper(spec)
        observed['_board_ref']['textNodeId'] = 'text:other'
        self.assertFalse(validate(spec, observed)['passed'])

    def test_legacy_spec_hash_and_validation_remain_supported(self):
        spec = contract.derive_specifications(fixture())[1]
        for field in ('presentation', 'locale', 'sections', 'annotation_text'):
            spec.pop(field, None)
        spec['display_text'] = 'legacy display'
        spec['meaning_sha256'] = contract._meaning_hash(spec)
        observed = wrapper(spec)
        observed.pop('human_annotation', None)
        self.assertTrue(contract.validate_specification(spec, observed, native_id='native:1', source_owner_hash='b' * 64)['passed'])


if __name__ == '__main__':
    unittest.main()
