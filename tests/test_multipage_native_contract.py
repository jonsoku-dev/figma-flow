"""Local graph and supplied getter regressions, not live Figma evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_draft as draft
from test_design_quality import instantiate_demo
from test_specification_rendering import readable_fixture


class MultipagePacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.manifest = instantiate_demo(cls.folder.name)
        cls.review = draft.checked_review(cls.manifest)
        cls.layout_path = Path(cls.review['native_layout']['path'])
        cls.layout = json.loads(cls.layout_path.read_text())
        cls.graphs = [json.loads(Path(row['product_graph']['path']).read_text()) for row in cls.review['candidates']]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def packet(self, mutate=lambda graph, source: None, readable=False):
        review, layout = copy.deepcopy(self.review), copy.deepcopy(self.layout)
        if readable:
            review['mode'] = 'direct'
        for row, source, original in zip(review['candidates'], layout['candidates'], self.graphs):
            graph = copy.deepcopy(original)
            if readable:
                graph['nodes'] += [{'id': 'req', 'type': 'requirement', 'title': 'Read sessions'},
                                   {'id': 'ac', 'type': 'acceptance', 'title': 'Visible sessions'},
                                   {'id': 'test', 'type': 'test', 'title': 'Check sessions'}]
                graph['edges'] += [{'from': 'req', 'to': node['id'], 'type': 'appears on'} for node in graph['nodes'] if node['type'] == 'screen']
                graph['edges'] += [{'from': 'req', 'to': 'ac', 'type': 'accepted by'}, {'from': 'ac', 'to': 'test', 'type': 'checked by'}]
            mutate(graph, source)
            path = Path(row['product_graph']['path'])
            path.write_text(json.dumps(graph))
            row['product_graph'] = draft.design_directions.pin(path)
            source['graph']['sha256'] = row['product_graph']['sha256']
        self.layout_path.write_text(json.dumps(layout))
        review['native_layout'] = draft.design_directions.pin(self.layout_path)
        # Admission is isolated; packaging still reads and validates real pinned graph/layout/assets.
        with patch.object(draft, 'checked_review', return_value=review):
            return draft.make_packet(self.manifest)

    def test_legacy_entry_defaults_and_geometry_only_buttons(self):
        def mutate(graph, source):
            state = graph['draft_prototype']['entry_state']
            for viewport in ('desktop', 'mobile'):
                source['state_layouts'][viewport][state]['product_buttons'] = {'extra': {'label': 'Details', 'variant': 'Primary', 'box': [24, 500, 280, 48]}}
        for candidate in self.packet(mutate)['candidates']:
            self.assertEqual(candidate['entry_states'], [candidate['entry_state']])
            self.assertNotIn('entry_states', candidate['prototype'])
            self.assertNotIn('specifications', candidate)

    def test_disjoint_entry_components_need_union_reachability(self):
        def mutate(graph, source):
            prototype = graph['draft_prototype']
            original_states = copy.deepcopy(prototype['states'])
            copied = {state['id']: state['id'] + '-second' for state in original_states}
            for state in original_states:
                graph['nodes'].append({'id': copied[state['id']], 'type': 'state', 'title': state['title'] + ' second'})
                prototype['states'].append({**state, 'id': copied[state['id']]})
                for viewport in ('desktop', 'mobile'):
                    source['state_layouts'][viewport][copied[state['id']]] = copy.deepcopy(source['state_layouts'][viewport][state['id']])
            prototype['bindings'] += [{**edge, 'source_state': copied[edge['source_state']], 'target_state': copied[edge['target_state']]} for edge in list(prototype['bindings'])]
            prototype['entry_states'] = [prototype['entry_state'], copied[prototype['entry_state']]]
        for candidate in self.packet(mutate)['candidates']:
            self.assertEqual(len(candidate['entry_states']), 2)
            self.assertEqual(len(candidate['prototype']['states']), 4)
            self.assertTrue(all(edge['source_state'] != edge['target_state'] for edge in candidate['prototype']['bindings']))

    def test_native_self_navigation_is_rejected_for_legacy_and_declared_entries(self):
        for viewport in ('desktop', 'mobile'):
            for explicit in (False, True):
                def mutate(graph, source):
                    prototype = graph['draft_prototype']
                    if explicit:
                        prototype['entry_states'] = [prototype['entry_state']]
                    edge = next(edge for edge in prototype['bindings'] if edge['viewport'] == viewport)
                    edge['target_state'] = edge['source_state']
                with self.subTest(viewport=viewport, explicit=explicit), self.assertRaisesRegex(ValueError, 'Native NAVIGATE requires a different target state'):
                    self.packet(mutate)

    def test_invalid_declared_entries_fail(self):
        for invalid in ([], ['unknown'], None, 'entry', [{}], ['']):
            with self.subTest(entries=invalid), self.assertRaisesRegex(ValueError, 'entry_states'):
                self.packet(lambda graph, source: graph['draft_prototype'].update(entry_states=invalid))
        for problem in ('duplicate', 'missing primary'):
            def mutate(graph, source):
                prototype = graph['draft_prototype']
                primary, other = [state['id'] for state in prototype['states']]
                prototype['entry_states'] = [primary, primary] if problem == 'duplicate' else [other]
            with self.subTest(problem=problem), self.assertRaisesRegex(ValueError, 'entry_states'):
                self.packet(mutate)

    def test_one_viewport_unreachable_or_no_return_fails(self):
        for viewport in ('desktop', 'mobile'):
            for broken in ('forward', 'return'):
                def mutate(graph, source):
                    prototype = graph['draft_prototype']
                    entry = prototype['entry_state']
                    prototype['bindings'] = [edge for edge in prototype['bindings']
                        if not (edge['viewport'] == viewport and ((edge['source_state'] == entry) == (broken == 'forward')))]
                with self.subTest(viewport=viewport, broken=broken), self.assertRaisesRegex(ValueError, 'reachable from and return'):
                    self.packet(mutate)

    @staticmethod
    def add_static(graph, source):
        state = graph['draft_prototype']['states'][0]
        action = copy.deepcopy(next(node for node in graph['nodes'] if node['type'] == 'action'))
        action.update(id='ACT-static', source_screen=state['screen'])
        action['annotation']['control_id'] = 'ACT-static'
        graph['nodes'].append(action)
        graph['edges'].append({'from': state['screen'], 'to': action['id'], 'type': 'enables'})
        for viewport in ('desktop', 'mobile'):
            source['state_layouts'][viewport][state['id']]['product_buttons'] = {'ACT-static': {'specification_id': 'ACT-static', 'label': 'Details', 'variant': 'Primary', 'box': [24, 500, 280, 48]}}

    def test_static_button_uses_compiled_current_action_specification(self):
        for candidate in self.packet(self.add_static, readable=True)['candidates']:
            spec = candidate['specifications']['ACT-static']
            self.assertEqual(spec['kind'], 'action')
            self.assertEqual(spec['meaning']['action'], 'ACT-static')
            self.assertEqual(spec['trace']['status'], 'complete')
            graph_path = next(row['product_graph']['path'] for row in self.review['candidates'] if row['id'] == candidate['id'])
            self.assertEqual(spec['source_graph_sha256'], draft.sha(Path(graph_path).read_bytes()))

    def test_static_specification_preserves_distinct_control_identity(self):
        def mutate(graph, source):
            self.add_static(graph, source)
            state = graph['draft_prototype']['states'][0]
            graph['nodes'][-1]['annotation']['control_id'] = 'existing-save-control'
            for viewport in ('desktop', 'mobile'):
                buttons = source['state_layouts'][viewport][state['id']]['product_buttons']
                buttons['existing-save-control'] = buttons.pop('ACT-static')
        for candidate in self.packet(mutate, readable=True)['candidates']:
            self.assertEqual(candidate['specifications']['ACT-static']['target_id'], 'existing-save-control')

    def test_invalid_static_specification_references_fail(self):
        for problem in ('unknown', 'wrong screen', 'screen spec', 'bound reuse', 'wrong control', 'canonical control', 'null', 'empty'):
            def mutate(graph, source):
                self.add_static(graph, source)
                state, other = graph['draft_prototype']['states']
                action = graph['nodes'][-1]
                if problem == 'wrong screen':
                    action['source_screen'] = other['screen']
                if problem == 'canonical control':
                    action['annotation']['control_id'] = 'different-control'
                if problem == 'bound reuse':
                    graph['draft_prototype']['bindings'].append({'viewport': 'mobile', 'source_state': state['id'], 'target_state': other['id'], 'action': 'ACT-static', 'control_id': 'ACT-static'})
                for viewport in ('desktop', 'mobile'):
                    buttons = source['state_layouts'][viewport][state['id']]['product_buttons']
                    if problem == 'wrong control':
                        buttons['other'] = buttons.pop('ACT-static')
                    button = next(iter(buttons.values()))
                    if problem in ('unknown', 'screen spec', 'null', 'empty'):
                        button['specification_id'] = {'unknown': 'ACT-missing', 'screen spec': state['screen'], 'null': None, 'empty': ''}[problem]
            with self.subTest(problem=problem), self.assertRaisesRegex(ValueError, '[Pp]roduct button specification'):
                self.packet(mutate, readable=True)


class NativeReadbackContractTests(unittest.TestCase):
    def test_explicit_entries_require_both_viewports_and_legacy_only_desktop(self):
        candidate = {'id': 'app', 'entry_state': 'one', 'entry_states': ['one'], 'prototype': {}}
        keyed = {f'app.{vp}.{state}': {'id': f'{vp}-{state}'} for vp in ('desktop', 'mobile') for state in ('one', 'two')}
        packet = {'candidates': [candidate]}
        draft._verify_draft_flow_starts(packet, {'flowStartingPoints': [{'nodeId': 'desktop-one'}]}, keyed)
        candidate['prototype']['entry_states'] = ['one']
        with self.assertRaisesRegex(ValueError, 'viewports'):
            draft._verify_draft_flow_starts(packet, {'flowStartingPoints': [{'nodeId': 'desktop-one'}]}, keyed)
        starts = [{'nodeId': vp + '-one'} for vp in ('desktop', 'mobile')]
        draft._verify_draft_flow_starts(packet, {'flowStartingPoints': starts}, keyed)
        candidate['entry_states'].append('two')
        starts += [{'nodeId': vp + '-two'} for vp in ('desktop', 'mobile')]
        draft._verify_draft_flow_starts(packet, {'flowStartingPoints': starts}, keyed)
        for invalid in (None, [], starts[:-1], starts + [starts[0]], starts + [{}]):
            with self.subTest(starts=invalid), self.assertRaises(ValueError):
                draft._verify_draft_flow_starts(packet, {'flowStartingPoints': invalid}, keyed)

    @staticmethod
    def static_fixture():
        raw, _ = readable_fixture()
        target = raw['nodes'][1]
        target.update(type='INSTANCE', mainComponentId='main-static', reactions=[])
        raw['nodes'].append({'id': 'main-static', 'type': 'COMPONENT'})
        return raw, target, target['specification']['specification']

    def verify_static(self, raw, target, spec):
        draft._verify_static_product_button(target, spec, 'b' * 64, raw, {node['id']: node for node in raw['nodes']})

    def test_static_instance_connected_summary_and_full_board_pass(self):
        raw, target, spec = self.static_fixture()
        self.verify_static(raw, target, spec)
        self.assertTrue(target['annotations'][0]['labelMarkdown'])
        self.assertEqual(target['reactions'], [])

    def test_static_instance_rejects_all_reactions_and_missing_getters(self):
        for reactions in (None, [{'trigger': {'type': 'ON_CLICK'}}], [{'trigger': {'type': 'ON_HOVER'}}], [{}], 'missing'):
            raw, target, spec = self.static_fixture()
            if reactions == 'missing':
                del target['reactions']
            else:
                target['reactions'] = reactions
            with self.subTest(reactions=reactions), self.assertRaisesRegex(ValueError, 'reaction'):
                self.verify_static(raw, target, spec)
        raw, target, spec = self.static_fixture()
        raw['nodes'].pop()
        with self.assertRaisesRegex(ValueError, 'INSTANCE'):
            self.verify_static(raw, target, spec)

    def test_static_annotation_metadata_and_actual_board_getters_fail_closed(self):
        for problem in ('annotation', 'metadata', 'board text', 'hyperlink', 'target'):
            raw, target, spec = self.static_fixture()
            text = next(node for node in raw['nodes'] if node.get('hyperlink') == {'type': 'NODE', 'value': target['id']})
            if problem == 'annotation':
                target.pop('annotations')
            elif problem == 'metadata':
                target.pop('specification')
            elif problem == 'board text':
                text['characters'] = 'Plausible stale content'
            elif problem == 'hyperlink':
                text.pop('hyperlink')
            else:
                target['specification']['target_id'] = 'foreign'
            with self.subTest(problem=problem), self.assertRaisesRegex(ValueError, 'specification'):
                self.verify_static(raw, target, spec)


if __name__ == '__main__':
    unittest.main()
