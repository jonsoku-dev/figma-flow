import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/design_bundle.py'
sys.path.insert(0, str(TOOL.parent))
from design_bundle import build
from direction_fixture import selected_direction
from workflow import State


class BundleTests(unittest.TestCase):
    def test_cross_surface_alias_pin_and_output_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            graph = base / 'graph.json'
            design = base / 'design.json'
            graph.write_text(json.dumps({'version':1, 'nodes':[
                {'id':'R','type':'requirement','title':'Need','status':'observed'},
                {'id':'S','type':'screen','title':'Screen','status':'planned'}],
                'edges':[{'from':'R','to':'S','type':'appears on'}]}))
            source = {'version':1, 'tokens':{'base':{'$type':'color','$value':'#446688'},
                       'brand':{'$type':'color','$value':'{base}'}},
                      'components':{'card':{'variants':{'default':{'background':'brand'}}}},
                      'screens':[{'id':'S','title':'Screen','trace':['R'],
                                  'elements':[{'id':'x','kind':'component','component':'card',
                                               'variant':'default','text':'</textarea><script>bad()'}]}]}
            design.write_text(json.dumps(source))
            out=base/'new'
            command=[sys.executable,'-B',str(TOOL),'--draft-only','--graph',str(graph),'--design',str(design),'--out',str(out)]
            completed=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            stamp=json.loads((out/'bundle.json').read_text())
            self.assertEqual(stamp['status'], 'exploratory')
            self.assertFalse(stamp['production_eligible'])
            self.assertEqual(stamp['resolved_sha256'],hashlib.sha256((out/'preview/resolved.json').read_bytes()).hexdigest())
            self.assertFalse((out/'figma-plugin').exists())
            self.assertIn('card / default', (out/'tokens.html').read_text())
            self.assertNotIn('</textarea><script>bad()', (out/'index.html').read_text())
            self.assertFalse((out/'figma-plugin.zip').exists())
            template = base / 'assigned.json'
            template.write_text(json.dumps({'id':'12345'}))
            identified = base / 'identified'
            other = subprocess.run(command[:-1]+[str(identified),'--id-from',str(template)],capture_output=True)
            self.assertNotEqual(other.returncode,0,other.stderr)
            self.assertFalse(identified.exists())
            original=(out/'bundle.json').read_bytes()
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(original,(out/'bundle.json').read_bytes())

    def test_selected_graph_builds_import_and_rejects_old_geometry_only_readback(self):
        # Only the user-turn resolver is isolated to the test directory. No actual user consent or Figma execution.
        spec = importlib.util.spec_from_file_location('bridge_examples', ROOT / 'tests/test_figma_bridge.py')
        examples = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(examples)
        raw = examples.design()
        graph = examples.selected_graph(raw)
        reference = ROOT / 'examples/native-direction-review/previews/bulletin-mobile.png'
        encoded = base64.b64encode(reference.read_bytes()).decode('ascii')
        graph['reference_image'] = 'data:image/png;base64,' + encoded
        graph['nodes'].append({'id':'REQ-ONE','type':'requirement','title':'Read notes'})
        for node in graph['nodes']:
            node['status'] = 'planned'
            if node['type'] == 'action':
                node['target_ids'] = ['SCR-TWO']
        graph['edges'] = [{'from':'REQ-ONE','to':s['id'],'type':'appears on'} for s in raw['screens']]
        graph['edges'] += [{'from':'SCR-ONE','to':'ACT-GO','type':'offers'},
                           {'from':'ACT-GO','to':'SCR-TWO','type':'transitions to'}]
        tokens = {}
        for key, token in raw['tokens'].items():
            group, leaf = key.split('.')
            value = '{' + token['alias'] + '}' if token.get('alias') else token['value']
            tokens.setdefault(group, {})[leaf] = {'$type': token['type'], '$value': value}
        for screen in raw['screens']:
            screen['trace'] = ['REQ-ONE']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root/'design.json'
            design.write_text(json.dumps(dict(raw,tokens=tokens)))
            with selected_direction(root,graph,native_review=True) as f:
                out = root/'bundle'
                result = build(design,f.product_graph,out,'12345',selection_path=f.selection_path)
                self.assertEqual(result['workflow_state'], State.SELECTED.value)
                self.assertEqual(result['status'], 'pending_native_handoff')
                self.assertEqual(result['warnings'], [])
                self.assertIn('--expected figma-plugin/expected-native-handoff.json', result['acceptance_command'])
                with patch('embedded_assets.WARNING_BYTES', len(encoded) - 1):
                    warning_out = root / 'bundle-with-warning'
                    build(design, f.product_graph, warning_out, '12345', selection_path=f.selection_path)
                    warning = json.loads((warning_out / 'bundle.json').read_text())['warnings'][0]
                    self.assertIn(f'{len(encoded):,} base64 bytes', warning)
                self.assertTrue((out/'figma-plugin.zip').is_file())
                self.assertEqual(json.loads((out/'figma-plugin/manifest.json').read_text())['id'],'12345')
                contract = json.loads((out/result['native_handoff_contract']).read_text())
                self.assertEqual(contract['mode'],'strict-creation')
                self.assertEqual(contract['annotation_contract']['product_graph'],json.loads(f.product_graph.read_text()))
                self.assertTrue(contract['design_foundations']['palette']['samples'])
                observed = examples.simulated_readback(json.loads((out/'preview/resolved.json').read_text()),result['resolved_sha256'])
                import native_handoff
                report = native_handoff.evaluate(observed,contract)
                self.assertFalse(report['passed'], 'Historical data must not satisfy stricter creation acceptance')
                current = json.loads(f.product_graph.read_text())
                current['nodes'][0]['title'] = 'A new design direction'
                f.product_graph.write_text(json.dumps(current))
                with self.assertRaises(ValueError):
                    build(design,f.product_graph,root/'stale',selection_path=f.selection_path)
                self.assertFalse((root/'stale').exists())

if __name__=='__main__':
    unittest.main()
