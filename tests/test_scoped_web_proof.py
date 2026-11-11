import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from graph_design_system import load_graph, resolve_design_system
from graph_sync import combine_web_proofs, main, parse_web_proof, verify_web_proof, web_probe


class ScopedWebProofTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'graph.json'
        self.path.write_text(json.dumps({'design_system': {'version': 1,
            'tokens': {'size': {'type': 'FLOAT', 'value': 18},
                       'ink': {'type': 'COLOR', 'value': {'r': 0, 'g': 0, 'b': 0}}},
            'components': {key: {'properties': {'fontSize': 'size', 'color': 'ink'},
                                 'web': {'selector': '#' + key}}
                           for key in ('submit', 'return')}}}))
        self.graph = load_graph(self.path)
        self.sha = resolve_design_system(self.graph)['graphSha256']

    def proof(self, key, width=1200):
        return {'schema': 'figma-flow-graph-web-readback-v1', 'graph_sha256': self.sha,
                'component_ids': [key], 'url': 'http://localhost:3000/' + key,
                'observed_at': '2026-11-11T12:00:00+09:00',
                'viewport': {'width': width, 'height': 800, 'device_pixel_ratio': 2},
                'components': [{'id': key, 'selector': '#' + key, 'graph_sha256': self.sha,
                                'properties': {'fontSize': 18, 'color': {'r': 0, 'g': 0, 'b': 0, 'a': 1}}}]}

    def write(self, proof, name):
        path = self.directory / name
        path.write_text(json.dumps(proof))
        return path

    def sources(self):
        return [self.write(self.proof('submit'), 'submit.json'),
                self.write(self.proof('return', 390), 'return.json')]

    def test_scoped_probe_reads_actual_dom_and_viewport_without_expected_values(self):
        if not shutil.which('node'):
            self.skipTest('Node required to execute generated probe')
        probe = web_probe(self.graph, ['return'])
        harness = """
global.document = {querySelectorAll(selector) {
  if (selector !== '#return') throw Error('unmounted screen queried');
  return [{getClientRects() {return [{width:100,height:40,top:2000}];}, getAttribute(name) {if(name !== 'data-graph-sha') throw Error(name); return 'actual-dom-hash';}}];
}};
global.getComputedStyle = () => ({fontSize:'31px', color:'rgb(255, 0, 128)'});
global.innerWidth = 390; global.innerHeight = 844; global.devicePixelRatio = 3;
global.location = {href:'https://example.test/confirmation'};
console.log(JSON.stringify(%s));
""" % probe.strip()
        observed = json.loads(subprocess.run(['node', '-e', harness], check=True, capture_output=True, text=True).stdout)
        self.assertEqual(observed['component_ids'], ['return'])
        self.assertEqual(observed['components'][0]['properties']['fontSize'], 31)
        self.assertEqual(observed['components'][0]['properties']['color']['b'], 128 / 255)
        self.assertEqual(observed['graph_sha256'], 'actual-dom-hash')
        self.assertEqual(observed['viewport'], {'width': 390, 'height': 844, 'device_pixel_ratio': 3})
        self.assertNotIn(self.sha, probe)
        self.assertIn('"submit"', web_probe(self.graph))
        self.assertNotIn('component_ids:', web_probe(self.graph))
        full = subprocess.run(['node', '-e', harness.replace(probe.strip(), web_probe(self.graph).strip())], capture_output=True, text=True)
        self.assertNotEqual(full.returncode, 0)
        self.assertIn('unmounted screen queried', full.stderr)
        for hidden in (harness.replace('width:100,height:40', 'width:0,height:0'),
                       harness.replace('[{width:100,height:40,top:2000}]', '[]'),
                       harness.replace("fontSize:'31px'", "visibility:'hidden',fontSize:'31px'"),
                       harness.replace("fontSize:'31px'", "display:'none',fontSize:'31px'")):
            with self.subTest(hidden=hidden):
                result = subprocess.run(['node', '-e', hidden], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Web component is not rendered: return (#return)', result.stderr)
        legacy_hidden = harness.replace("if (selector !== '#return')", 'if (false)')
        legacy_hidden = legacy_hidden.replace('width:100,height:40', 'width:0,height:0')
        legacy_hidden = legacy_hidden.replace(probe.strip(), web_probe(self.graph).strip())
        self.assertEqual(subprocess.run(['node', '-e', legacy_hidden], capture_output=True, text=True).returncode, 0)

    def test_full_verifier_rejects_partial_even_when_scope_is_declared(self):
        proof = self.proof('submit')
        self.assertTrue(verify_web_proof(self.graph, proof, ['submit']))
        with self.assertRaises(ValueError):
            verify_web_proof(self.graph, proof)
        del proof['component_ids']
        with self.assertRaises(ValueError):
            verify_web_proof(self.graph, proof)

    def test_scope_rejects_empty_unknown_duplicate_and_mismatch(self):
        for scope in ([], ['unknown'], ['submit', 'submit'], 'submit', [None]):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    web_probe(self.graph, scope)
                with self.assertRaises(ValueError):
                    verify_web_proof(self.graph, self.proof('submit'), scope)
        with self.assertRaises(ValueError):
            verify_web_proof(self.graph, self.proof('return'), ['submit'])

    def test_legacy_full_proof_does_not_require_new_combiner_metadata(self):
        proof = self.proof('submit')
        proof['components'] += self.proof('return')['components']
        del proof['component_ids'], proof['viewport']
        proof['observed_at'] = 'legacy observation label'
        proof['sources'] = [{'path': 'legacy/opaque-source.json', 'scope': 'desktop'}]
        proof['evidence'] = 'legacy actual DOM observations'
        proof['components'][0]['properties']['legacy_extra'] = 'opaque metadata'
        self.assertTrue(verify_web_proof(self.graph, proof))

    def test_two_screen_viewports_combine_immutable_rows_and_all_provenance(self):
        paths = self.sources()
        before = {path: path.read_bytes() for path in [self.path] + paths}
        result = combine_web_proofs(self.graph, paths)
        self.assertEqual(result['composition_protocol'], 'figma-flow-web-composition-v1')
        self.assertTrue(verify_web_proof(self.graph, result))
        self.assertEqual(result['components'], [json.loads(before[path])['components'][0] for path in paths])
        self.assertEqual([source['viewport']['width'] for source in result['sources']], [1200, 390])
        for source, path in zip(result['sources'], paths):
            actual = json.loads(before[path])
            self.assertEqual(source, {'path': str(path.resolve()), 'sha256': hashlib.sha256(before[path]).hexdigest(),
                'url': actual['url'], 'observed_at': actual['observed_at'],
                'viewport': actual['viewport'], 'component_ids': actual['component_ids']})
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_missing_empty_or_undeclared_partial_evidence_rejected(self):
        with self.assertRaises(ValueError):
            combine_web_proofs(self.graph, [])
        path = self.write(self.proof('submit'), 'one.json')
        with self.assertRaises(ValueError):
            combine_web_proofs(self.graph, [path])
        for mutation in (lambda p: p.update(components=[]), lambda p: p.pop('component_ids')):
            proof = self.proof('submit')
            mutation(proof)
            path.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                combine_web_proofs(self.graph, [path])

    def test_source_validation_rejects_bad_scope_stale_identity_and_measured_values(self):
        mutations = [lambda p: p.update(component_ids=[]),
                     lambda p: p.update(component_ids=None),
                     lambda p: p.update(component_ids=['unknown']),
                     lambda p: p.update(component_ids=['submit', 'submit']),
                     lambda p: p.update(graph_sha256='stale'),
                     lambda p: p['components'][0].update(graph_sha256='stale'),
                     lambda p: p['components'][0].update(selector='#wrong'),
                     lambda p: p['components'][0]['properties'].update(fontSize=19),
                     lambda p: p['components'][0]['properties'].update(fontSize='18px'),
                     lambda p: p['components'][0]['properties'].update(fontSize=True),
                     lambda p: p['components'][0]['properties'].pop('color'),
                     lambda p: p['components'][0]['properties'].update(color={'r': 2, 'g': 0, 'b': 0}),
                     lambda p: p.update(observed_at='2026-11-11T12:00:00'),
                     lambda p: p.update(observed_at='invalid'),
                     lambda p: p.update(url='file:///tmp/example.html'),
                     lambda p: p.update(url='http:///missing-host'),
                     lambda p: p.pop('viewport'),
                     lambda p: p['viewport'].update(width=True),
                     lambda p: p['viewport'].update(height=0),
                     lambda p: p['viewport'].update(device_pixel_ratio=-1)]
        other = self.write(self.proof('return'), 'return.json')
        for mutation in mutations:
            proof = self.proof('submit')
            mutation(proof)
            with self.subTest(mutation=mutation):
                path = self.write(proof, 'bad.json')
                with self.assertRaises(ValueError):
                    combine_web_proofs(self.graph, [path, other])

    def test_duplicate_viewports_keep_all_sources_and_conflicting_measured_color_fails(self):
        paths = self.sources()
        duplicate = self.proof('submit', 390)
        duplicate['observed_at'] = '2026-11-11T04:00:00Z'
        paths.append(self.write(duplicate, 'submit-mobile.json'))
        result = combine_web_proofs(self.graph, paths)
        self.assertEqual(len(result['components']), 2)
        self.assertEqual(len(result['sources']), 3)
        self.assertEqual(result['observed_at'], duplicate['observed_at'])
        duplicate['components'][0]['properties']['color']['r'] = 0.001
        self.assertTrue(verify_web_proof(self.graph, duplicate, ['submit']))
        paths[-1].write_text(json.dumps(duplicate))
        with self.assertRaisesRegex(ValueError, 'conflicting duplicate'):
            combine_web_proofs(self.graph, paths)

    def test_source_tampering_and_provenance_tampering_rejected(self):
        paths = self.sources()
        result = combine_web_proofs(self.graph, paths)
        for protocol in (None, 'unknown'):
            bad = copy.deepcopy(result)
            bad['composition_protocol'] = protocol
            with self.subTest(protocol=protocol), self.assertRaises(ValueError):
                verify_web_proof(self.graph, bad)
        for field, value in (('sha256', '0' * 64), ('url', 'https://elsewhere.test/'),
                             ('component_ids', ['return']), ('viewport', {'width': 1, 'height': 1})):
            bad = copy.deepcopy(result)
            bad['sources'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_web_proof(self.graph, bad)
        paths[0].write_bytes(paths[0].read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            verify_web_proof(self.graph, result)

    def test_legacy_full_sources_can_be_combined_but_new_compositions_cannot(self):
        paths = self.sources()
        legacy = self.proof('submit')
        legacy['components'] += self.proof('return')['components']
        del legacy['component_ids']
        legacy['sources'] = [{'path': 'legacy/opaque.json'}]
        result = combine_web_proofs(self.graph, [self.write(legacy, 'legacy.json')])
        self.assertTrue(verify_web_proof(self.graph, result))
        nested = self.write(combine_web_proofs(self.graph, paths), 'nested.json')
        with self.assertRaisesRegex(ValueError, 'original actual'):
            combine_web_proofs(self.graph, [nested])

    def test_one_json_string_wrapper_preserves_raw_source_hash_and_rows(self):
        paths = self.sources()
        original = paths[0].read_bytes()
        paths[0].write_text(json.dumps(original.decode('utf-8')))
        wire = paths[0].read_bytes()
        self.assertEqual(parse_web_proof(wire), json.loads(original))
        result = combine_web_proofs(self.graph, paths)
        self.assertTrue(verify_web_proof(self.graph, result))
        self.assertEqual(result['sources'][0]['sha256'], hashlib.sha256(wire).hexdigest())
        self.assertEqual(result['components'][0], json.loads(original)['components'][0])
        self.assertEqual(paths[0].read_bytes(), wire)
        paths[0].write_bytes(wire + b'\n')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            verify_web_proof(self.graph, result)

    def test_web_proof_transport_rejects_malformed_inner_json_and_nonobjects(self):
        other = self.write(self.proof('return'), 'return.json')
        for wire in ('not json', json.dumps('not json'), json.dumps([]), json.dumps(18),
                     json.dumps(json.dumps([])), json.dumps(json.dumps(None)),
                     json.dumps(json.dumps(json.dumps(self.proof('submit'))))):
            with self.subTest(wire=wire):
                path = self.directory / 'bad-transport.json'
                path.write_text(wire)
                with self.assertRaises(ValueError):
                    combine_web_proofs(self.graph, [path, other])

    def test_cli_new_outputs_only_and_full_combined_gate(self):
        paths = self.sources()
        probe = self.directory / 'probe.js'
        self.assertEqual(main(['probe', '--graph', str(self.path), '--component', 'return', '--out', str(probe)]), 0)
        self.assertEqual(probe.read_text(), web_probe(self.graph, ['return']))
        output = self.directory / 'combined.json'
        args = ['combine-web', '--graph', str(self.path), '--out', str(output)]
        for path in paths:
            args += ['--proof', str(path)]
        self.assertEqual(main(args), 0)
        self.assertTrue(verify_web_proof(self.graph, json.loads(output.read_text())))
        for target in [self.path, *paths, output, probe]:
            before = target.read_bytes()
            with self.subTest(target=target):
                self.assertEqual(main(['probe', '--graph', str(self.path), '--out', str(target)]), 2)
                self.assertEqual(main(args[:4] + [str(target)] + args[5:]), 2)
                self.assertEqual(target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
