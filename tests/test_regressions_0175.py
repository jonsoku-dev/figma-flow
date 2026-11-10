"""0.17.5: an implementation graph may extend the user-selected graph with coverage, never redesign it."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_directions  # noqa: E402

SELECTED = json.loads((ROOT / 'examples/native-direction-review/bulletin/graph.json').read_text())


def implemented():
    graph = copy.deepcopy(SELECTED)
    screens = [n['id'] for n in graph['nodes'] if n['type'] == 'screen']
    for node in graph['nodes']:
        if node['type'] == 'screen':
            node['status'] = 'observed'
            node['source'] = 'app/index.html#' + node['id']
    graph['stage'] = 'implementation'
    graph['nodes'] += [{'id': 'REQ-X', 'type': 'requirement', 'title': 'Read the bulletin', 'status': 'observed'},
                       {'id': 'CODE-X', 'type': 'code', 'title': 'App', 'status': 'verified', 'source': 'app/index.html'},
                       {'id': 'TEST-X', 'type': 'test', 'title': 'Round trip', 'status': 'verified', 'source': 'tests/x.test.cjs'}]
    graph['edges'] += [{'from': 'REQ-X', 'to': s, 'type': 'appears on'} for s in screens]
    graph['edges'] += [{'from': s, 'to': 'CODE-X', 'type': 'implemented by'} for s in screens]
    graph['edges'] += [{'from': 'CODE-X', 'to': 'TEST-X', 'type': 'verified by'}]
    return graph


def errors(graph):
    return design_directions.implementation_fidelity_errors(SELECTED, graph)


class ImplementationFidelityTests(unittest.TestCase):
    def test_additive_coverage_and_status_updates_are_faithful(self):
        self.assertEqual(errors(implemented()), [])

    def test_design_changes_are_rejected(self):
        first_action = next(n for n in SELECTED['nodes'] if n['type'] == 'action')['id']
        first_screen = next(n for n in SELECTED['nodes'] if n['type'] == 'screen')['id']
        def changed_title(g): next(n for n in g['nodes'] if n['id'] == first_screen)['title'] = 'Other'
        def dropped_action(g): g['nodes'][:] = [n for n in g['nodes'] if n['id'] != first_action]
        def changed_targets(g): next(n for n in g['nodes'] if n['id'] == first_action)['target_ids'] = []
        def changed_annotation(g): next(n for n in g['nodes'] if n['id'] == first_screen)['annotation']['purpose'] = 'Other'
        def changed_foundation(g): g['design_foundations']['roles'][0]['value'] = '#000000'
        def changed_prototype(g): g['draft_prototype']['entry_state'] = 'elsewhere'
        def new_selected_edge(g): g['edges'].append({'from': first_action, 'to': first_screen, 'type': 'shows'})
        def dropped_edge(g): g['edges'].pop(0)
        def added_screen(g): g['nodes'].append({'id': 'SCR-NEW', 'type': 'screen', 'title': 'New', 'status': 'planned'})
        cases = {'changed field title': changed_title, 'selected node removed': dropped_action, 'changed field target_ids': changed_targets,
                 'changed field annotation': changed_annotation, 'field changed: design_foundations': changed_foundation,
                 'field changed: draft_prototype': changed_prototype, 'new edge between selected nodes': new_selected_edge,
                 'selected edge removed': dropped_edge, 'may only add': added_screen}
        for message, mutate in cases.items():
            with self.subTest(message):
                graph = implemented()
                mutate(graph)
                found = errors(graph)
                self.assertTrue(any(message in e for e in found), found)

    def test_guard_uses_fidelity_check_when_bytes_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            selected_path = Path(tmp) / 'selected.json'
            selected_path.write_text(json.dumps(SELECTED))
            impl_path = Path(tmp) / 'impl.json'
            receipt = {'product_graph': {'path': str(selected_path), 'sha256': design_directions.pin(selected_path)['sha256']}}
            original = design_directions.require_selected
            design_directions.require_selected = lambda _: receipt
            try:
                impl_path.write_text(json.dumps(implemented()))
                self.assertIs(design_directions.require_implementation_selection('x', impl_path), receipt)
                bad = implemented()
                bad['nodes'][0]['title'] = 'Redesigned'
                impl_path.write_text(json.dumps(bad))
                with self.assertRaises(design_directions.SelectionRequired):
                    design_directions.require_implementation_selection('x', impl_path)
            finally:
                design_directions.require_selected = original


if __name__ == '__main__':
    unittest.main()
