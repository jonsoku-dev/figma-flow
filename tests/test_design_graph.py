import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_graph


class DesignGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.graph = {'version': 1, 'nodes': [
            {'id': name, 'type': kind, 'title': name, 'status': 'observed'}
            for name, kind in [('req', 'requirement'), ('S', 'screen'), ('T', 'screen'), ('go', 'action')]],
            'edges': [{'from': 'req', 'to': 'S', 'type': 'appears on'},
                      {'from': 'req', 'to': 'T', 'type': 'appears on'},
                      {'from': 'S', 'to': 'go', 'type': 'contains'},
                      {'from': 'go', 'to': 'T', 'type': 'navigates'}]}
        self.graph['nodes'][-1].update(source_screen='S', target_ids=['T'])
        self.design = {'version': 1, 'tokens': {'base': {'$type': 'color', '$value': '#ffffff'},
            'alias': {'$type': 'color', '$value': '{base}'}, 'unused': {'$type': 'number', '$value': 1}},
            'components': {'button': {'variants': {'primary': {'background': 'alias'}}}},
            'screens': [{'id': 'S', 'title': 'Start', 'trace': ['req'], 'elements': [
                {'kind': 'component', 'component': 'button', 'variant': 'primary', 'text': 'Go', 'action_id': 'go', 'target_screen': 'T'}]},
                {'id': 'T', 'title': 'End', 'trace': ['req'], 'elements': [{'kind': 'text', 'text': 'End'}]}]}

    def run_augment(self):
        for name, value in [('graph.json', self.graph), ('design.json', self.design)]:
            (self.base / name).write_text(json.dumps(value))
        return design_graph.augment(self.graph, self.design, self.base / 'graph.json', self.base / 'design.json', self.base / 'out.json')

    def test_exact_dependencies_and_coverage(self):
        original = copy.deepcopy(self.graph)
        result = self.run_augment()
        token = design_graph.stable_id('TOKEN', 'base')
        alias = design_graph.stable_id('TOKEN', 'alias')
        component = design_graph.stable_id('COMPONENT', 'button', 'primary')
        edges = {(e['from'], e['to']) for e in result['edges'] if e['type'] == 'depends-on'}
        self.assertEqual(edges, {(token, alias), (alias, component), (component, 'S'), (component, 'go')})
        self.assertEqual(result['design_system']['unused_token_paths'], ['unused'])
        self.assertEqual(result['design_system']['uncovered_product_screen_ids'], [])
        self.assertEqual(self.graph, original)
        self.assertEqual(result, self.run_augment())
        for node in result['nodes'][len(original['nodes']):]:
            self.assertTrue((self.base / node['source'].split('#')[0]).is_file())
            self.assertEqual(len(node['design_sha256']), 64)
        self.assertEqual(design_graph.graph.validate_graph(result)[0], [])

    def test_missing_screen_or_wrong_type(self):
        self.design['screens'][0]['id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'product screen'):
            self.run_augment()
        self.design['screens'][0]['id'] = 'req'
        with self.assertRaisesRegex(ValueError, 'product screen'):
            self.run_augment()

    def test_action_link_validation(self):
        item = self.design['screens'][0]['elements'][0]
        for key, value, message in [('action_id', 'absent', 'action does not belong'),
                                    ('target_screen', 'S', 'target mismatch'),
                                    ('action_id', None, 'explicit action_id'),
                                    ('target_screen', None, 'requires its target_screen')]:
            with self.subTest(key=key, value=value):
                saved = dict(item)
                if value is None:
                    item.pop(key)
                else:
                    item[key] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.run_augment()
                item.clear()
                item.update(saved)

    def test_rejects_unrelated_trace(self):
        self.design['screens'][1]['trace'] = ['go']
        self.graph['edges'] = [e for e in self.graph['edges'] if e['from'] != 'go']
        self.graph['nodes'][-1]['target_ids'] = []
        with self.assertRaisesRegex(ValueError, 'target mismatch'):
            self.run_augment()
        self.design['screens'][0]['elements'][0].pop('target_screen')
        with self.assertRaisesRegex(ValueError, 'trace does not belong'):
            self.run_augment()

    def test_collisions_and_regeneration_fail_closed(self):
        self.graph['nodes'].append({'id': design_graph.stable_id('TOKEN', 'base'), 'type': 'code', 'title': 'Existing', 'status': 'planned'})
        with self.assertRaisesRegex(ValueError, 'ID collision'):
            self.run_augment()
        self.graph['nodes'].pop()
        self.graph = self.run_augment()
        with self.assertRaisesRegex(ValueError, 'unaugmented'):
            self.run_augment()
        self.assertNotEqual(design_graph.stable_id('COMPONENT', 'a-b', 'c'), design_graph.stable_id('COMPONENT', 'a', 'b-c'))

    def test_granular_fingerprints_and_symlink_locator(self):
        self.graph['nodes'][0]['source'] = 'link/../evidence.txt#part'
        result = self.run_augment()
        self.design['tokens']['unused']['$value'] = 2
        changed = self.run_augment()
        before = {node['id']: node for node in result['nodes'] if 'design_sha256' in node}
        after = {node['id']: node for node in changed['nodes'] if 'design_sha256' in node}
        differences = [node_id for node_id in before if before[node_id] != after[node_id]]
        self.assertEqual(differences, [design_graph.stable_id('TOKEN', 'unused')])
        self.assertNotEqual(result['design_system']['inputs']['design']['sha256'], changed['design_system']['inputs']['design']['sha256'])
        output = self.base / 'nested' / 'out.json'
        relocated = design_graph.augment(self.graph, self.design, self.base / 'graph.json', self.base / 'design.json', output)
        self.assertEqual(relocated['nodes'][0]['source'], '../link/../evidence.txt#part')

    def audit_graph(self, value):
        path = self.base / 'augmented.json'
        path.write_text(json.dumps(value))
        return design_graph.audit(value, self.design, path, self.base / 'design.json')

    def test_audit_reports_missing_alias_component_edge_and_node(self):
        result = self.run_augment()
        self.assertTrue(self.audit_graph(result)['clear'])
        alias = design_graph.stable_id('TOKEN', 'alias')
        base = design_graph.stable_id('TOKEN', 'base')
        component = design_graph.stable_id('COMPONENT', 'button', 'primary')
        for source, target in [(base, alias), (alias, component)]:
            changed = copy.deepcopy(result)
            changed['edges'] = [edge for edge in changed['edges'] if (edge['from'], edge['to']) != (source, target)]
            report = self.audit_graph(changed)
            self.assertEqual(report['missing_edges'], [{'from': source, 'to': target, 'type': 'depends-on'}])
            self.assertFalse(report['clear'])
        changed = copy.deepcopy(result)
        changed['nodes'] = [node for node in changed['nodes'] if node['id'] != alias]
        self.assertEqual(self.audit_graph(changed)['missing_node_ids'], [alias])
        changed = copy.deepcopy(result)
        next(node for node in changed['nodes'] if node['id'] == alias)['design_value']['alias'] = None
        self.assertEqual(self.audit_graph(changed)['changed_nodes'][0]['fields'], ['design_value'])

    def test_audit_preserves_product_and_reports_drift_extra_edges(self):
        self.graph['nodes'].append({'id': 'isolated', 'type': 'code', 'title': 'Product', 'status': 'observed'})
        result = self.run_augment()
        original = copy.deepcopy(result)
        self.assertTrue(self.audit_graph(result)['clear'])
        self.assertEqual(result, original)
        result['edges'].append({'from': design_graph.stable_id('TOKEN', 'base'), 'to': 'isolated', 'type': 'depends-on'})
        self.assertEqual(len(self.audit_graph(result)['extra_edges']), 1)
        (self.base / 'design.json').write_text(json.dumps(self.design) + '\n')
        self.assertEqual(self.audit_graph(result)['source_drift'][0]['input'], 'design')

    def test_audit_cli_exit_codes_and_relocation(self):
        result = self.run_augment()
        relocated = self.base / 'nested'
        relocated.mkdir()
        result = design_graph.augment(self.graph, self.design, self.base / 'graph.json', self.base / 'design.json', relocated / 'graph.json')
        path = relocated / 'graph.json'
        command = [sys.executable, str(ROOT / 'tools/design_graph.py'), '--audit', '--graph', str(path), '--design', str(self.base / 'design.json')]
        for expected_exit in (0, 1, 2):
            if expected_exit == 1:
                result['edges'].pop()
            if expected_exit == 2:
                result = {'version': 1}
            path.write_text(json.dumps(result))
            before = path.read_bytes()
            check = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(check.returncode, expected_exit, check.stdout + check.stderr)
            self.assertIsInstance(json.loads(check.stdout), dict)
            self.assertEqual(before, path.read_bytes())

    def test_cli_immutable_and_output_location(self):
        self.run_augment()
        command = [sys.executable, str(ROOT / 'tools/design_graph.py'), '--graph', str(self.base / 'graph.json'), '--design', str(self.base / 'design.json'), '--out', str(self.base / 'out.json')]
        before = (self.base / 'graph.json').read_bytes()
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        output = (self.base / 'out.json').read_bytes()
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(output, (self.base / 'out.json').read_bytes())
        self.assertEqual(before, (self.base / 'graph.json').read_bytes())
        relocated = self.base / 'elsewhere'
        relocated.mkdir()
        command[-1] = str(relocated / 'out.json')
        self.graph['nodes'][0]['source'] = 'evidence.txt#section'
        self.graph['nodes'][1]['source'] = 'https://example.com/page#part'
        (self.base / 'evidence.txt').write_text('proof')
        self.run_augment()
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        moved = json.loads((relocated / 'out.json').read_text())
        self.assertEqual(moved['nodes'][0]['source'], '../evidence.txt#section')
        self.assertEqual(moved['nodes'][1]['source'], 'https://example.com/page#part')
        self.assertTrue((relocated / moved['nodes'][0]['source'].split('#')[0]).is_file())


if __name__ == '__main__':
    unittest.main()
