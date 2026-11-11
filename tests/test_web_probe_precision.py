import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from graph_design_system import load_graph, resolve_design_system
from graph_sync import verify_web_proof, web_probe


class WebProbePrecisionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'graph.json'
        values = dict.fromkeys(('fontSize', 'paddingLeft', 'paddingRight', 'paddingTop',
                               'paddingBottom', 'gap', 'borderWidth', 'borderRadius',
                               'minWidth', 'minHeight'), 10.171875)
        values.update(width=120, height=40)
        self.path.write_text(json.dumps({'design_system': {'version': 1,
            'tokens': {field: {'type': 'FLOAT', 'value': value} for field, value in values.items()},
            'components': {'button': {'properties': {field: field for field in values},
                                      'web': {'selector': '#button'}}}}}))
        self.graph = load_graph(self.path)
        self.sha = resolve_design_system(self.graph)['graphSha256']

    def probe(self, typed_setup='', style_updates=None):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node required to execute generated probe')
        style = dict.fromkeys(resolve_design_system(self.graph)['components']['button'], '10.1719px')
        style.update(width='120px', height='40px')
        style.update(style_updates or {})
        script = """
const element = {
  getClientRects: () => [{width:120, height:40}],
  getAttribute: () => %s
};
%s
global.document = {querySelectorAll: () => [element]};
global.getComputedStyle = () => (%s);
global.location = {href:'http://localhost:3000/'};
global.innerWidth = 1200; global.innerHeight = 800; global.devicePixelRatio = 2;
console.log(JSON.stringify(%s));
""" % (json.dumps(self.sha), typed_setup, json.dumps(style), web_probe(self.graph, ['button']).strip())
        return json.loads(subprocess.run([node, '-e', script], check=True, capture_output=True, text=True).stdout)

    def test_typed_pixels_preserve_precision_and_dimensions_keep_used_values(self):
        proof = self.probe("element.computedStyleMap = () => ({get: () => ({unit:'px', value:10.171875})});")
        self.assertTrue(verify_web_proof(self.graph, proof, ['button']))
        self.assertEqual(proof['components'][0]['properties']['paddingLeft'], 10.171875)
        self.assertEqual(proof['components'][0]['properties']['width'], 120)
        self.assertEqual(proof['components'][0]['properties']['height'], 40)
        self.assertNotIn('10.171875', web_probe(self.graph))

    def test_missing_unsupported_throwing_and_nonpixel_typed_values_fall_back(self):
        cases = ('',
                 'element.computedStyleMap = () => {throw Error("unavailable")};',
                 'element.computedStyleMap = () => ({get: () => {throw Error("unsupported")}});',
                 'element.computedStyleMap = () => ({get: () => undefined});',
                 'element.computedStyleMap = () => ({get: () => ({toString: () => "10.171875px"})});',
                 'element.computedStyleMap = () => ({get: () => ({unit:"percent", value:10.171875})});',
                 'element.computedStyleMap = () => ({get: () => ({unit:"px", value:NaN})});',
                 'element.computedStyleMap = () => ({get: () => ({unit:"px", value:Infinity})});',
                 'element.computedStyleMap = () => ({get: () => ({unit:"px", value:true})});')
        for setup in cases:
            with self.subTest(setup=setup):
                proof = self.probe(setup)
                self.assertEqual(proof['components'][0]['properties']['paddingLeft'], 10.1719)
                with self.assertRaisesRegex(ValueError, 'property mismatch'):
                    verify_web_proof(self.graph, proof, ['button'])
        percent = self.probe("element.computedStyleMap = () => ({get: field => ({unit:field === 'padding-left' ? 'percent' : 'px', value:10.171875})});", {'paddingLeft': '10%'})
        self.assertEqual(percent['components'][0]['properties']['paddingLeft'], '10%')
        with self.assertRaisesRegex(ValueError, 'numeric pixels'):
            verify_web_proof(self.graph, percent, ['button'])

    def test_float32_is_exact_and_invalid_numbers_and_stale_graph_fail(self):
        raw = json.loads(self.path.read_text())
        raw['design_system']['tokens']['paddingLeft']['value'] = 0.1
        self.path.write_text(json.dumps(raw))
        self.graph = load_graph(self.path)
        self.sha = resolve_design_system(self.graph)['graphSha256']
        proof = self.probe("element.computedStyleMap = () => ({get: field => ({unit:'px', value:field === 'padding-left' ? Math.fround(0.1) : 10.171875})});")
        self.assertEqual(proof['components'][0]['properties']['paddingLeft'], struct.unpack('f', struct.pack('f', 0.1))[0])
        self.assertTrue(verify_web_proof(self.graph, proof, ['button']))
        exact = copy.deepcopy(proof)
        exact['components'][0]['properties']['paddingLeft'] = 0.1
        self.assertTrue(verify_web_proof(self.graph, exact, ['button']))
        for field, value in (('paddingLeft', 0.10001), ('paddingRight', 10.172),
                             ('paddingLeft', True), ('paddingLeft', 10 ** 400), ('paddingLeft', float('nan')),
                             ('paddingLeft', float('inf')), ('paddingLeft', -float('inf'))):
            bad = copy.deepcopy(proof)
            bad['components'][0]['properties'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                verify_web_proof(self.graph, bad, ['button'])
        for component_hash in (False, True):
            stale = copy.deepcopy(proof)
            target = stale['components'][0] if component_hash else stale
            target['graph_sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                verify_web_proof(self.graph, stale, ['button'])


if __name__ == '__main__':
    unittest.main()
