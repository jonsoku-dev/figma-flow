import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_figma_bridge import bridge, design, readback_nodes, simulated_readback


class Readback0180Tests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = root / 'resolved.json'
        self.model = design()
        self.source.write_text(json.dumps(self.model))
        self.export = simulated_readback(self.model, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.path = root / 'readback.json'
        self.contract = root / 'contract.json'

    def inspect(self, contract=None):
        self.path.write_text(json.dumps(self.export))
        return bridge.inspect_readback(self.path, self.source, contract)

    def test_selected_annotation_text_and_legacy_fallback(self):
        required = bridge.handoff_contract(self.model)['required_annotations']
        self.assertTrue(self.inspect()['matches_supplied_source'])
        selected = {key: 'Selected graph note for ' + key for key in required}
        for node in readback_nodes(self.export):
            if node.get('semantic_id') in selected:
                node['annotations'] = [{'label': selected[node['semantic_id']]}]
        for mode, notes, status in [('strict-creation', selected, 'match'), ('strict-creation', None, 'missing'),
                                    ('technical', selected, 'missing')]:
            with self.subTest(mode=mode, notes=notes is not None):
                contract = dict(bridge.expected_handoff(self.model), mode=mode)
                if notes is not None:
                    contract['required_annotations'] = notes
                self.contract.write_text(json.dumps(contract))
                checks = self.inspect(self.contract)['import_checks'][0]['annotation_checks']
                self.assertEqual({check['semantic_id']: check['status'] for check in checks},
                                 dict.fromkeys(required, status))
        self.contract.write_text(json.dumps(dict(bridge.expected_handoff(self.model),
                                                 mode='strict-creation', required_annotations={})))
        with self.assertRaisesRegex(ValueError, 'every required annotation'):
            self.inspect(self.contract)

    def test_inherited_label_ignored_but_real_duplicates_still_unsupported(self):
        page = self.export['pages'][0]
        label = next(node for node in readback_nodes(self.export)
                     if node.get('semantic_id') == 'component:button/primary/label')
        clone = dict(copy.deepcopy(label), id='9:11')
        page['children'].append({'type': 'INSTANCE', 'id': '9:9', 'semantic_id': 'palette:sample',
                                 'children': [{'type': 'FRAME', 'id': '9:10', 'children': [clone]}]})
        self.assertTrue(self.inspect()['matches_supplied_source'])
        page['children'].append(dict(clone, id='9:12'))
        report = self.inspect()
        self.assertFalse(report['matches_supplied_source'])
        bindings = report['import_checks'][0]['binding_checks']
        self.assertEqual({b['status'] for b in bindings if b['semantic_id'] == label['semantic_id']}, {'unsupported'})
