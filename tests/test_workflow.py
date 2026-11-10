import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import workflow as w


class WorkflowTests(unittest.TestCase):
    def resolve(self, guard, evidence):
        definition = next(g for g in self.graph['guards'] if g['id'] == guard.value)
        return w.VerifiedFact(guard, 'a' * 64, 'b' * 64, definition['authority'])

    def setUp(self):
        self.graph = w.load_graph()

    def test_exports_are_derived_from_same_graph(self):
        exported = w.public_graph()
        self.assertEqual(exported['graph'], self.graph)
        for name, enum in [('states', w.State), ('events', w.Event), ('guards', w.Guard)]:
            self.assertEqual(exported['symbols'][name], {item.name: item.value for item in enum})
            self.assertEqual(exported['symbols'][name], {row['symbol']: row['id'] for row in self.graph[name]})
        canonical = json.dumps(self.graph, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        self.assertEqual(exported['graph_sha256'], hashlib.sha256(canonical).hexdigest())
        exported['graph']['states'].clear()
        self.assertTrue(w.public_graph()['graph']['states'])
        cli = subprocess.run([sys.executable, str(ROOT / 'tools' / 'workflow.py')], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(cli.stdout), w.public_graph())

    def test_draft_and_production_native_require_design_canvas_note_boards(self):
        graph = w.public_graph()['graph']
        contract = graph['evidence_contracts']['native_canvas']
        self.assertIs(contract['dev_mode_required'], False)
        self.assertIn('design_canvas_linked_note_boards', contract['required_facts'])
        self.assertIn('native_annotations', contract['required_facts'])
        self.assertIn('node IDs', contract['note_board_evidence'])
        self.assertIn('readable note text', contract['note_board_evidence'])
        for guard in (w.Guard.NATIVE_REVIEW_CURRENT, w.Guard.NATIVE_CURRENT):
            definition = next(g for g in graph['guards'] if g['id'] == guard.value)
            self.assertEqual(definition['evidence_contract'], 'native_canvas')
        self.assertIn('ordinary Design-canvas readable linked note boards', graph['boundaries']['native_review'])
        self.assertIn('Figma Dev Mode is never required', graph['boundaries']['native_canvas'])

    def test_mermaid_contains_every_state_and_edge(self):
        diagram = w.mermaid()
        for state in self.graph['states']:
            self.assertIn(f'as {state["id"].replace("-", "_")}', diagram)
        for edge in self.graph['edges']:
            self.assertIn(f'{edge["from"].replace("-", "_")} --> {edge["to"].replace("-", "_")}: {edge["event"]}', diagram)

    def test_full_human_selected_native_flow(self):
        state = w.State(self.graph['initial'])
        path = [(w.Event.RESEARCH, w.State.RESEARCH),
                (w.Event.PREPARE_CANDIDATES, w.State.SELECTION_READY),
                (w.Event.PREPARE_NATIVE_DRAFT, w.State.NATIVE_REVIEW_PENDING),
                (w.Event.REQUEST_SELECTION, w.State.WAIT_SELECTION),
                (w.Event.SELECT, w.State.SELECTED),
                (w.Event.FREEZE_BATCH, w.State.BATCH_FROZEN),
                (w.Event.GENERATE, w.State.GENERATION),
                (w.Event.HANDOFF_NATIVE, w.State.NATIVE),
                (w.Event.IMPLEMENT, w.State.IMPLEMENTATION),
                (w.Event.VERIFY, w.State.VERIFICATION),
                (w.Event.COMPLETE, w.State.COMPLETE)]
        for event, expected in path:
            state = w.transition(state, event, resolver=self.resolve)
            self.assertEqual(state, expected)

    def test_native_review_requires_actual_current_native_observations(self):
        calls = []
        def resolver(guard, evidence):
            calls.append(guard)
            return self.resolve(guard, evidence)
        state = w.transition(w.State.SELECTION_READY, w.Event.PREPARE_NATIVE_DRAFT, resolver=resolver)
        self.assertEqual(state, w.State.NATIVE_REVIEW_PENDING)
        self.assertEqual(calls, [w.Guard.CANDIDATES_CURRENT, w.Guard.FIGMA_REVIEW_SCOPE])
        for value in (None, True, {'package_prepared': True},
                      replace(self.resolve(w.Guard.NATIVE_REVIEW_CURRENT, None), current=False)):
            def pending_resolver(guard, evidence):
                return value if guard == w.Guard.NATIVE_REVIEW_CURRENT else self.resolve(guard, evidence)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'missing or stale'):
                w.transition(state, w.Event.REQUEST_SELECTION, evidence={'admitted': True}, resolver=pending_resolver)
        self.assertEqual(w.transition(state, w.Event.REQUEST_SELECTION, resolver=resolver), w.State.WAIT_SELECTION)
        for event in [w.Event.SELECT, w.Event.FREEZE_BATCH, w.Event.GENERATE,
                      w.Event.HANDOFF_NATIVE, w.Event.IMPLEMENT, w.Event.COMPLETE]:
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, 'unsupported workflow transition'):
                w.transition(state, event, resolver=self.resolve)

    def test_direct_html_review_requires_explicit_non_figma_review_scope(self):
        calls = []
        def resolver(guard, evidence):
            calls.append(guard)
            return self.resolve(guard, evidence)
        self.assertEqual(w.transition(w.State.SELECTION_READY, w.Event.REQUEST_SELECTION,
                                      resolver=resolver), w.State.WAIT_SELECTION)
        self.assertEqual(calls, [w.Guard.CANDIDATES_CURRENT, w.Guard.NON_FIGMA_REVIEW_SCOPE])
        def figma_target(guard, evidence):
            return None if guard == w.Guard.NON_FIGMA_REVIEW_SCOPE else self.resolve(guard, evidence)
        with self.assertRaisesRegex(ValueError, 'missing or stale'):
            w.transition(w.State.SELECTION_READY, w.Event.REQUEST_SELECTION, resolver=figma_target)

    def test_missing_stale_and_boolean_evidence_fail_before_generation(self):
        for state, event in [(w.State.WAIT_SELECTION, w.Event.SELECT),
                             (w.State.SELECTED, w.Event.FREEZE_BATCH),
                             (w.State.BATCH_FROZEN, w.Event.GENERATE)]:
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, 'resolver required'):
                    w.transition(state, event, evidence={'approved': True})
                for resolver in [lambda g, e: True, lambda g, e: None,
                                 lambda g, e: replace(self.resolve(g, e), current=False)]:
                    with self.assertRaisesRegex(ValueError, 'missing or stale'):
                        w.transition(state, event, resolver=resolver)

    def test_human_selection_requires_human_authority_and_exact_hashes(self):
        for change, message in [({'authority': 'controller'}, 'authority'),
                                ({'subject_sha256': ''}, 'hashes'),
                                ({'evidence_sha256': 'old'}, 'hashes'),
                                ({'guard': w.Guard.BATCH_CURRENT}, 'missing or stale')]:
            def resolver(guard, evidence):
                fact = self.resolve(guard, evidence)
                return replace(fact, **change) if guard == w.Guard.HUMAN_SELECTION_CURRENT else fact
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                w.transition(w.State.WAIT_SELECTION, w.Event.SELECT, resolver=resolver)

    def test_actual_guard_result_is_used(self):
        calls = []
        def resolver(guard, evidence):
            calls.append((guard, evidence))
            if guard == w.Guard.BATCH_CURRENT:
                raise ValueError('batch no longer matches selected candidate')
            return self.resolve(guard, evidence)
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            w.transition(w.State.BATCH_FROZEN, w.Event.GENERATE, evidence='current files', resolver=resolver)
        self.assertEqual(calls, [(w.Guard.HUMAN_SELECTION_CURRENT, 'current files'), (w.Guard.BATCH_CURRENT, 'current files')])

    def test_explicit_scope_branches_require_evidence(self):
        for state in [w.State.BRIEF, w.State.SELECTED, w.State.GENERATION]:
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    w.transition(state, w.Event.IMPLEMENT)
                self.assertEqual(w.transition(state, w.Event.IMPLEMENT, resolver=self.resolve), w.State.IMPLEMENTATION)

    def test_native_without_generated_assets_requires_verified_scope_and_selection(self):
        with self.assertRaisesRegex(ValueError, 'resolver required'):
            w.transition(w.State.SELECTED, w.Event.HANDOFF_NATIVE)
        requested = []
        def resolver(guard, evidence):
            requested.append(guard)
            return self.resolve(guard, evidence)
        self.assertEqual(w.transition(w.State.SELECTED, w.Event.HANDOFF_NATIVE,
                                      resolver=resolver), w.State.NATIVE)
        self.assertEqual(requested, [w.Guard.NO_ASSET_SCOPE, w.Guard.HUMAN_SELECTION_CURRENT])
        for rejected in requested:
            def reject_scope(guard, evidence):
                return None if guard == rejected else self.resolve(guard, evidence)
            with self.subTest(rejected=rejected), self.assertRaisesRegex(ValueError, 'missing or stale'):
                w.transition(w.State.SELECTED, w.Event.HANDOFF_NATIVE, resolver=reject_scope)

    def test_invalidation_preserves_prior_work_and_evidence(self):
        boundary = self.graph['boundaries']['invalidation']
        self.assertIn('receipts and eligibility references', boundary)
        self.assertIn('preserve prior user work, assets, files and evidence', boundary)

    def test_reselection_and_rework_invalidate_downstream(self):
        for state in [w.State.SELECTED, w.State.BATCH_FROZEN, w.State.GENERATION, w.State.NATIVE, w.State.IMPLEMENTATION, w.State.VERIFICATION]:
            result = w.transition_result(state, w.Event.RESELECT, resolver=self.resolve)
            self.assertEqual(result['state'], w.State.WAIT_SELECTION)
            self.assertEqual(result['invalidates'], ['selection', 'batch', 'assets', 'native', 'implementation', 'verification'])
        result = w.transition_result(w.State.VERIFICATION, w.Event.REWORK)
        self.assertEqual(result['invalidates'], ['verification'])
        result = w.transition_result(w.State.SELECTED, w.Event.REVISE_BRIEF)
        self.assertEqual(result['state'], w.State.BRIEF)
        self.assertIn('selection', result['invalidates'])

    def test_unknown_edges_and_terminal_fail(self):
        for state, event in [(w.State.BRIEF, w.Event.GENERATE),
                             (w.State.WAIT_SELECTION, w.Event.COMPLETE),
                             (w.State.COMPLETE, w.Event.RESELECT),
                             ('unknown-state', w.Event.IMPLEMENT),
                             (w.State.BRIEF, 'auto-approve')]:
            with self.subTest(state=state, event=event), self.assertRaises(ValueError):
                w.transition(state, event, resolver=self.resolve)

    def test_graph_integrity_rejects_drift(self):
        mutations = [lambda g: g['states'].append(copy.deepcopy(g['states'][0])),
                     lambda g: g['states'][1].update(symbol=g['states'][0]['symbol']),
                     lambda g: g['edges'][0].update(to='absent'),
                     lambda g: g['edges'][0].update(event='absent'),
                     lambda g: g['edges'][0].update(guards=['absent']),
                     lambda g: g['edges'].append(copy.deepcopy(g['edges'][0])),
                     lambda g: g['states'].append({'id': 'orphan', 'symbol': 'ORPHAN', 'label': 'Orphan', 'terminal': True}),
                     lambda g: g['edges'].append({'from': w.State.COMPLETE.value, 'to': w.State.BRIEF.value, 'event': w.Event.REWORK.value, 'guards': []}),
                     lambda g: g.update(version=2),
                     lambda g: g['states'][0].update(id='invalid id'),
                     lambda g: g['edges'].__setitem__(0, None),
                     lambda g: g.update(edges=[e for e in g['edges'] if e['to'] != w.State.COMPLETE.value])]
        for mutate in mutations:
            graph = copy.deepcopy(self.graph)
            mutate(graph)
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                w.validate_graph(graph)


if __name__ == '__main__':
    unittest.main()
