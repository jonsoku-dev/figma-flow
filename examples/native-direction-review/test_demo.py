"""Source-only checks; no browser, Figma, selection, hooks or asset production."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import demo


class NativeRoleDemoTest(unittest.TestCase):
    def test_generated_source_is_byte_identical_to_shipped_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            demo.build_files(root)
            for path in root.rglob('*'):
                if path.is_file():
                    self.assertEqual(path.read_bytes(),(demo.EXAMPLE/path.relative_to(root)).read_bytes(),str(path.relative_to(root)))

    def test_exact_roles_bind_actual_source_and_reject_missing_or_wrong_targets(self):
        layout=json.loads((demo.EXAMPLE/'native-layout.json').read_text())
        for candidate in layout['candidates']:
            graph=json.loads((demo.EXAMPLE/candidate['graph']['path']).read_text())
            targets=demo.attach_native_roles(candidate['id'],graph,candidate['state_layouts'],candidate['fonts'],candidate['control_styles'])
            roles={role['token']:role['native']for role in graph['design_foundations']['roles']if role['kind']!='color'}
            self.assertEqual(roles['type/body']['type'],'FLOAT')
            self.assertEqual(roles['type/body']['value'],16)
            self.assertEqual(roles['type/family/body']['type'],'STRING')
            self.assertEqual(roles['type/family/body']['value'],'Inter')
            self.assertEqual(roles['space/content']['value'],24)
            self.assertEqual(roles['radius/control']['value'],6)
            target=roles['type/body']['bindings'][0]
            missing=copy.deepcopy(targets);del missing[target['key']]
            with self.assertRaisesRegex(ValueError,'target missing'):
                demo.check_native_roles(graph,missing)
            changed=copy.deepcopy(targets);changed[target['key']][target['field']]=18
            with self.assertRaisesRegex(ValueError,'value/type mismatch'):
                demo.check_native_roles(graph,changed)
            with self.assertRaisesRegex(ValueError,'target missing'):
                bad_layout=copy.deepcopy(candidate['state_layouts'])
                edge=graph['draft_prototype']['bindings'][0]
                del bad_layout[edge['viewport']][edge['source_state']]['control_boxes'][edge['control_id']]
                demo.attach_native_roles(candidate['id'],graph,bad_layout,candidate['fonts'],candidate['control_styles'])
            with self.assertRaisesRegex(ValueError,'value/type mismatch'):
                bad=copy.deepcopy(candidate['control_styles'])
                bad['mobile']['Primary']['paddingX']=20
                demo.attach_native_roles(candidate['id'],graph,candidate['state_layouts'],candidate['fonts'],bad)


if __name__=='__main__':
    unittest.main()
