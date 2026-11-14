import json
import hashlib
import base64
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
import shutil
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import web_design, native_edit

def png_chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)


PNG_SAMPLE = (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
              + png_chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00\xff')) + png_chunk(b'IEND', b''))


def graph():
    return {
        'version': 1,
        'id': 'magic-ui-demo',
        'title': 'Magic UI',
        'nodes': [
            {
                'id': 'WEB-home',
                'type': 'screen',
                'title': 'Home',
                'status': 'observed',
                'layout': {'width': 390, 'height': 844, 'background': '#ffffff'},
                'elements': [
                    {
                        'id': 'heading',
                        'kind': 'text',
                        'path': [],
                        'box': {'x': 24, 'y': 40, 'width': 300, 'height': 48},
                        'text': {
                            'characters': 'Hello',
                            'fontFamily': 'Inter',
                            'fontSize': 32,
                            'fontWeight': '700',
                            'color': '#111111',
                        },
                    }
                ],
            }
        ],
        'edges': [],
    }


def carousel_graph():
    value = graph()
    value['nodes'] = [
        {'id': f'WEB-saas-feature-{index + 1}', 'type': 'screen', 'title': f'Feature {index + 1}',
         'status': 'observed', 'layout': {'width': 390, 'height': 844, 'background': '#ffffff'}, 'elements': []}
        for index in range(4)
    ]
    states = [{'id': f'feature-{i + 1}', 'screenId': f'WEB-saas-feature-{i + 1}', 'index': i,
               'railBounds': {'x': 0, 'y': 200, 'width': 390, 'height': 420},
               'capture': {'path': f'capture-{i + 1}.png', 'sha256': hashlib.sha256(PNG_SAMPLE).hexdigest()}}
              for i in range(4)]
    transitions = []
    for i, state in enumerate(states):
        for trigger, delta in (('swipe_left', 1), ('swipe_right', -1), ('autoplay', 1)):
            transitions.append({'id': f"{state['id']}-{trigger}", 'from': state['id'], 'trigger': trigger,
                                'to': states[(i + delta) % len(states)]['id'], 'observed': True,
                                'evidence': {'path': 'transition.png', 'sha256': hashlib.sha256(PNG_SAMPLE).hexdigest()}})
    value['carousel'] = {
        'frameKey': 'WEB-saas-features-rail', 'states': states, 'initialState': 'feature-3',
        'source': {'url': 'https://acme.example/', 'title': 'Acme', 'browser': 'Chromium',
                   'viewport': {'width': 390, 'height': 844}, 'dpr': 1, 'capturedAt': '2026-11-14T00:00:00Z'},
        'autoplay': {'enabled': True, 'intervalMs': 5000}, 'wrap': {'manual': True, 'autoplay': True}, 'transitions': transitions,
    }
    return value


def write_carousel_evidence(directory):
    for filename in [f'capture-{index}.png' for index in range(1, 5)] + ['transition.png']:
        (directory / filename).write_bytes(PNG_SAMPLE)


def tab_screens():
    value = graph()
    value['id'] = 'devtool-tabs-demo'
    value['nodes'] = []
    for index, (label, code) in enumerate((('Single Queue Pipeline', 'queue.execute()'),
                                           ('Parallel Worker Handshake', 'stage.sync()')), start=1):
        value['nodes'].append({'id': f'WEB-tabs-{index}', 'type': 'screen', 'title': label, 'status': 'observed',
            'layout': {'width': 1425, 'height': 900, 'background': '#0d0e12'},
            'elements': [
                {'id': f's{index}-tab-a', 'kind': 'frame', 'path': [], 'box': {'x': 20, 'y': 40, 'width': 300, 'height': 98}},
                {'id': f's{index}-tab-b', 'kind': 'frame', 'path': [], 'box': {'x': 20, 'y': 146, 'width': 300, 'height': 98}},
                {'id': f's{index}-code', 'kind': 'text', 'path': [], 'box': {'x': 400, 'y': 40, 'width': 600, 'height': 24},
                 'text': {'characters': code, 'fontFamily': 'Inter', 'fontSize': 14, 'fontWeight': '400', 'color': '#ffffff'}},
            ]})
    return value


def tab_observations():
    pin = {'path': 'state.png', 'sha256': hashlib.sha256(PNG_SAMPLE).hexdigest()}
    return {
        'schemaVersion': 1,
        'source': {'url': 'http://127.0.0.1:8873/', 'title': 'Devtool', 'browser': 'Chromium',
                   'viewport': {'width': 1440, 'height': 900}, 'dpr': 1, 'capturedAt': '2026-11-14T00:00:00Z'},
        'tabs': {'frameKey': 'devtool-examples', 'initialState': 'WEB-tabs-1'},
        'states': [{'id': 'WEB-tabs-1', 'label': 'Single Queue Pipeline', 'contentSha256': 'a' * 64, 'capture': pin},
                   {'id': 'WEB-tabs-2', 'label': 'Parallel Worker Handshake', 'contentSha256': 'b' * 64, 'capture': pin}],
        'transitions': [
            {'from': 'WEB-tabs-1', 'to': 'WEB-tabs-2', 'input': 'click', 'controlElementId': 's1-tab-b', 'observed': True, 'evidence': pin},
            {'from': 'WEB-tabs-2', 'to': 'WEB-tabs-1', 'input': 'click', 'controlElementId': 's2-tab-a', 'observed': True, 'evidence': pin},
        ],
    }


def write_tab_inputs(directory, observations=None):
    (directory / 'state.png').write_bytes(PNG_SAMPLE)
    (directory / 'screens.json').write_text(json.dumps(tab_screens()))
    (directory / 'observations.json').write_text(json.dumps(observations or tab_observations()))
    return directory / 'screens.json', directory / 'observations.json'


def representative_graph(asset_path, asset_hash, count=506):
    elements = [
        {
            'id': 'root',
            'kind': 'frame',
            'path': [],
            'box': {'x': 0, 'y': 0, 'width': 1265, 'height': 11678},
            'paint': {'background': '#ffffff'},
        }
    ]
    for index in range(count - 14):
        elements.append(
            {
                'id': f'text-{index}',
                'kind': 'text',
                'path': ['root'],
                'box': {'x': 32, 'y': index * 20, 'width': 300, 'height': 18},
                'text': {
                    'characters': f'Observed line {index}',
                    'fontFamily': 'Inter',
                    'fontSize': 14,
                    'fontWeight': 400,
                    'lineHeight': 20,
                    'textAlign': 'left',
                    'color': '#111111',
                },
            }
        )
    for index, label in enumerate(('Create an account', 'Join now')):
        elements.append(
            {
                'id': f'button-{index}',
                'kind': 'component',
                'componentKey': 'primary-button',
                'path': ['root'],
                'box': {'x': 24, 'y': 11000 + index * 48, 'width': 280 - index * 40, 'height': 36},
                'props': {
                    'label': label,
                    'labelBox': {'x': 0, 'y': 8, 'width': 200 - index * 40, 'height': 20},
                },
                'paint': {'background': '#e7000b', 'borderRadius': 8},
                'text': {
                    'characters': label,
                    'fontFamily': 'Inter',
                    'fontSize': 14,
                    'fontWeight': 500,
                    'lineHeight': 20,
                    'textAlign': 'center',
                    'color': '#ffffff',
                },
            }
        )
    for index in range(11):
        elements.append(
            {
                'id': f'image-{index}',
                'kind': 'image',
                'path': ['root'],
                'box': {'x': 24 + index * 42, 'y': 11200, 'width': 40, 'height': 40},
                'asset': {'path': asset_path, 'sha256': asset_hash, 'mimeType': 'image/png'},
                'objectFit': 'cover',
            }
        )
    return {
        'version': 1,
        'id': 'representative-magic-ui',
        'title': 'Representative capture',
        'nodes': [
            {
                'id': 'WEB-representative',
                'type': 'screen',
                'title': 'Representative capture',
                'status': 'observed',
                'layout': {'width': 1265, 'height': 11678, 'background': '#ffffff'},
                'elements': elements,
            }
        ],
        'edges': [],
    }


class WebDesignTests(unittest.TestCase):
    def test_intersecting_linear_and_radial_alpha_masks_are_validated_as_layers(self):
        sample = graph()
        sample['nodes'][0]['elements'][0]['paint'] = {
            'alphaMaskComposite': 'intersect',
            'alphaMasks': [
                {'kind': 'linear', 'angle': 90, 'stops': [
                    {'position': 0, 'color': '#00000000'}, {'position': 1, 'color': '#000000ff'},
                ]},
                {'kind': 'radial', 'centerX': 0.5, 'centerY': 0.5, 'stops': [
                    {'position': 0, 'color': '#000000ff'}, {'position': 1, 'color': '#00000000'},
                ]},
            ],
        }
        self.assertEqual(len(web_design.validate_graph(sample)), 1)
        sample['nodes'][0]['elements'][0]['paint']['alphaMaskComposite'] = 'add'
        with self.assertRaisesRegex(ValueError, 'Intersecting CSS alpha masks'):
            web_design.validate_graph(sample)

    def test_graph_to_pinned_native_plan(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            src.write_text(json.dumps(graph()))
            out = Path(d) / 'plan.json'
            receipt = web_design.build_plan(src, 'file', '1:1', out)
            plan = json.loads(out.read_text())
            native_edit.validate_plan(plan)
            self.assertEqual(receipt['screen_count'], 1)
            self.assertEqual(plan['web_design']['screens'][0]['layout']['width'], 390)
            with self.assertRaises(FileExistsError):
                web_design.build_plan(src, 'file', '1:1', out)

    def test_observed_tab_clicks_compile_into_a_pinned_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            graph_path, observations_path = write_tab_inputs(root)
            completed = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/native_edit.py'), 'web-tabs',
                                        '--graph', str(graph_path), '--observations', str(observations_path),
                                        '--out', str(root / 'tabs-graph.json')], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(completed.stdout)['transition_count'], 2)
            joined = json.loads((root / 'tabs-graph.json').read_text())
            self.assertEqual(joined['tabs']['initialState'], 'tab-1')
            self.assertEqual([(e['from'], e['to'], e['controlElementId']) for e in joined['tabs']['transitions']],
                             [('tab-1', 'tab-2', 's1-tab-b'), ('tab-2', 'tab-1', 's2-tab-a')])
            web_design.build_plan(root / 'tabs-graph.json', 'file', '1:1', root / 'plan.json')
            plan = json.loads((root / 'plan.json').read_text())
            native_edit.validate_plan(plan)
            plan['web_design']['tabs']['transitions'][0]['controlElementId'] = 's1-tab-a'
            with self.assertRaisesRegex(ValueError, 'tabs plan must exactly match'):
                native_edit.validate_plan(plan)
            (root / 'state.png').write_bytes(PNG_SAMPLE + b'x')
            with self.assertRaisesRegex(ValueError, 'evidence'):
                native_edit.validate_plan(json.loads((root / 'plan.json').read_text()))

    def test_tab_join_refuses_unobserved_or_ambiguous_transitions(self):
        cases = {
            'unobserved': lambda o: o['transitions'][0].update(observed=False),
            'self-loop': lambda o: o['transitions'][0].update(to='WEB-tabs-1'),
            'foreign control': lambda o: o['transitions'][0].update(controlElementId='s2-tab-b'),
            'text control': lambda o: o['transitions'][0].update(controlElementId='s1-code'),
            'duplicate content': lambda o: o['states'][1].update(contentSha256='a' * 64),
            'unreached state': lambda o: o.update(transitions=o['transitions'][1:]),
            'non-click input': lambda o: o['transitions'][0].update(input='hover'),
        }
        for name, mutate in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                observations = tab_observations()
                mutate(observations)
                graph_path, observations_path = write_tab_inputs(Path(d), observations)
                with self.assertRaises(ValueError):
                    web_design.join_tab_observations(graph_path, observations_path, Path(d) / 'out.json')
                self.assertFalse((Path(d) / 'out.json').exists())

    def test_finite_carousel_compiles_into_exact_pinned_plan(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            value = carousel_graph()
            write_carousel_evidence(Path(d))
            src.write_text(json.dumps(value))
            out = Path(d) / 'plan.json'
            web_design.build_plan(src, 'file', '1:1', out)
            plan = json.loads(out.read_text())
            native_edit.validate_plan(plan)
            self.assertEqual(plan['web_design']['carousel']['initialState'], 'feature-3')
            self.assertEqual(len(plan['web_design']['carousel']['transitions']), 12)

    def test_browser_observations_join_four_captured_screens_into_canonical_graph(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = carousel_graph()
            source.pop('carousel')
            graph_path, observations_path, output_path = root / 'screens.json', root / 'observations.json', root / 'joined.json'
            graph_path.write_text(json.dumps(source))
            observed_graph = carousel_graph()
            transitions = []
            for edge in observed_graph['carousel']['transitions']:
                transitions.append({'from': f"WEB-saas-{edge['from'].replace('feature-', 'feature-')}",
                                'to': f"WEB-saas-{edge['to'].replace('feature-', 'feature-')}",
                                    'input': edge['trigger'], 'observed': edge['observed'], 'evidence': edge['evidence']})
            observations = {
                'schemaVersion': 1,
                'source': {'url': 'https://acme.example/', 'title': 'Acme', 'browser': 'Chromium',
                           'viewport': {'width': 390, 'height': 844}, 'dpr': 1, 'capturedAt': '2026-11-14T00:00:00Z'},
                'carousel': {'frameKey': 'WEB-saas-features-rail', 'stateIds': [f'WEB-saas-feature-{i}' for i in range(1, 5)],
                             'initialState': 'WEB-saas-feature-1', 'intervalMs': 5000,
                             'wrap': {'manual': True, 'autoplay': True},
                             'rail': {'rect': {'x': 0, 'y': 200, 'width': 390, 'height': 420}}},
                'states': [{'id': f'WEB-saas-feature-{i}', 'index': i - 1,
                            'capture': {'path': f'capture-{i}.png', 'sha256': hashlib.sha256(PNG_SAMPLE).hexdigest()}}
                           for i in range(1, 5)],
                'transitions': transitions,
            }
            write_carousel_evidence(root)
            observations_path.write_text(json.dumps(observations))
            completed = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/native_edit.py'), 'web-carousel',
                                         '--graph', str(graph_path), '--observations', str(observations_path),
                                         '--out', str(output_path)], capture_output=True, text=True, check=True)
            result = json.loads(completed.stdout)
            joined = json.loads(output_path.read_text())
            self.assertEqual(result['state_count'], 4)
            self.assertEqual(joined['carousel']['initialState'], 'feature-1')
            self.assertEqual(joined['carousel']['states'][0]['railBounds']['width'], 390)
            observations['states'][0]['capture']['sha256'] = '0' * 64
            observations_path.write_text(json.dumps(observations))
            with self.assertRaisesRegex(ValueError, 'SHA-256 changed'):
                web_design.join_carousel_observations(graph_path, observations_path, root / 'bad-joined.json')

    def test_checked_in_synthetic_fixture_runs_through_both_public_commands(self):
        fixture = ROOT / 'tests/fixtures/web_carousel_synthetic'
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / 'synthetic'
            shutil.copytree(fixture, work)
            joined, plan_path = work / 'joined.json', work / 'plan.json'
            result = subprocess.run(
                [sys.executable, '-B', str(ROOT / 'tools/native_edit.py'), 'web-carousel',
                 '--graph', str(work / 'screens.json'), '--observations', str(work / 'observations.json'),
                 '--out', str(joined)], capture_output=True, text=True, check=True)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['state_count'], 4)
            self.assertEqual(receipt['shared_image_main_count'], 1)
            joined_graph = json.loads(joined.read_text())
            family_keys = {
                element['componentKey']
                for screen in joined_graph['nodes'] if screen.get('type') == 'screen'
                for element in screen['elements'] if element['kind'] == 'image'
            }
            self.assertEqual(len(family_keys), 1)
            web_design.build_plan(joined, 'fixture', '1:1', plan_path)
            plan = json.loads(plan_path.read_text())
            native_edit.validate_plan(plan)
            self.assertEqual(plan['web_design']['carousel']['wrap'], {'manual': False, 'autoplay': True})
            self.assertEqual(sum(element['kind'] == 'image' and 'componentKey' in element
                                 for screen in plan['web_design']['screens'] for element in screen['elements']), 4)

    def test_observation_join_rejects_bad_types_duplicate_states_and_symlink_evidence(self):
        fixture = ROOT / 'tests/fixtures/web_carousel_synthetic'
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / 'synthetic'
            shutil.copytree(fixture, work)
            graph_path, observation_path = work / 'screens.json', work / 'observations.json'
            observations = json.loads(observation_path.read_text())
            observations['states'][0]['id'] = {}
            observation_path.write_text(json.dumps(observations))
            with self.assertRaisesRegex(ValueError, 'two to sixteen ordered carousel states'):
                web_design.join_carousel_observations(graph_path, observation_path, work / 'bad-type.json')
            observations = json.loads((fixture / 'observations.json').read_text())
            observations['carousel']['stateIds'][1] = observations['carousel']['stateIds'][0]
            observation_path.write_text(json.dumps(observations))
            with self.assertRaisesRegex(ValueError, 'two to sixteen ordered carousel states'):
                web_design.join_carousel_observations(graph_path, observation_path, work / 'duplicate.json')
            observations = json.loads((fixture / 'observations.json').read_text())
            observations['transitions'][0]['input'] = []
            observation_path.write_text(json.dumps(observations))
            with self.assertRaisesRegex(ValueError, 'string state and input IDs'):
                web_design.join_carousel_observations(graph_path, observation_path, work / 'bad-input.json')
            observation_path.write_text((fixture / 'observations.json').read_text())
            (work / 'capture.png').unlink()
            (work / 'capture.png').symlink_to(fixture / 'capture.png')
            with self.assertRaisesRegex(ValueError, 'symbolic link'):
                web_design.join_carousel_observations(graph_path, observation_path, work / 'symlink.json')
            (work / 'capture.png').unlink()
            shutil.copy2(fixture / 'capture.png', work / 'capture.png')
            observations = json.loads(observation_path.read_text())
            observations['states'][0]['capture']['path'] = '../capture.png'
            observation_path.write_text(json.dumps(observations))
            with self.assertRaisesRegex(ValueError, 'relative to the canonical graph'):
                web_design.join_carousel_observations(graph_path, observation_path, work / 'escaped.json')

    def test_carousel_evidence_pin_detects_replacement_and_plan_output_is_immutable(self):
        fixture = ROOT / 'tests/fixtures/web_carousel_synthetic'
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / 'synthetic'
            shutil.copytree(fixture, work)
            graph_path, observation_path = work / 'screens.json', work / 'observations.json'
            joined = work / 'joined.json'
            web_design.join_carousel_observations(graph_path, observation_path, joined)
            plan_path = work / 'plan.json'
            web_design.build_plan(joined, 'fixture', '1:1', plan_path)
            native_edit.validate_plan(json.loads(plan_path.read_text()))
            with self.assertRaises(FileExistsError):
                web_design.build_plan(joined, 'fixture', '1:1', plan_path)
            replacement_png = (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
                               + png_chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff'))
                               + png_chunk(b'IEND', b''))
            (work / 'capture.png').write_bytes(replacement_png)
            with self.assertRaisesRegex(ValueError, 'SHA-256 changed'):
                native_edit.validate_plan(json.loads(plan_path.read_text()))

    def test_carousel_join_shares_only_image_families_with_matching_fitting_and_paint(self):
        fixture = ROOT / 'tests/fixtures/web_carousel_synthetic'
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / 'synthetic'
            shutil.copytree(fixture, work)
            graph_path = work / 'screens.json'
            graph = json.loads(graph_path.read_text())
            graph['nodes'][1]['elements'][0]['objectFit'] = 'contain'
            graph_path.write_text(json.dumps(graph))
            joined = work / 'unshared.json'
            receipt = web_design.join_carousel_observations(graph_path, work / 'observations.json', joined)
            self.assertEqual(receipt['shared_image_main_count'], 0)
            result = json.loads(joined.read_text())
            self.assertTrue(all('componentKey' not in element for screen in result['nodes'] if screen.get('type') == 'screen'
                                for element in screen['elements']))

    def test_graph_rejects_an_explicit_image_family_with_incompatible_rendering(self):
        value = json.loads((ROOT / 'tests/fixtures/web_carousel_synthetic/screens.json').read_text())
        for screen in value['nodes']:
            if screen.get('type') == 'screen':
                screen['elements'][0]['componentKey'] = 'shared-image'
        value['nodes'][2]['elements'][0]['paint'] = {'opacity': 0.5}
        with self.assertRaisesRegex(ValueError, 'identical appearance'):
            web_design.validate_graph(value)

    def test_legacy_component_keys_keep_their_existing_json_identity_format(self):
        value = graph()
        element = value['nodes'][0]['elements'][0]
        element['kind'] = 'component'
        element['componentKey'] = '["a",21,{},"Geist",16,500,"#101828","left"]'
        self.assertEqual(len(web_design.validate_graph(value)), 1)
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d) / 'legacy.json', Path(d) / 'plan.json'
            source.write_text(json.dumps(value))
            web_design.build_plan(source, 'file', '1:1', output)
            native_edit.validate_plan(json.loads(output.read_text()))

    def test_carousel_rejects_ambiguous_or_inconsistent_transition_graphs(self):
        bad = carousel_graph()
        bad['carousel']['transitions'][0]['to'] = 'feature-1'
        with self.assertRaisesRegex(ValueError, 'destination must match'):
            web_design.validate_graph(bad)
        bad = carousel_graph()
        bad['carousel']['transitions'].pop()
        with self.assertRaisesRegex(ValueError, 'Every carousel state'):
            web_design.validate_graph(bad)
        bad = carousel_graph()
        bad['carousel']['autoplay']['intervalMs'] = 999
        with self.assertRaisesRegex(ValueError, 'interval must be bounded'):
            web_design.validate_graph(bad)
        bad = carousel_graph()
        bad['carousel']['states'][1]['index'] = 0
        with self.assertRaisesRegex(ValueError, 'consecutive ordered indices'):
            web_design.validate_graph(bad)
        bad = carousel_graph()
        bad['carousel']['wrap']['manual'] = False
        with self.assertRaisesRegex(ValueError, 'destination must match'):
            web_design.validate_graph(bad)
        bad = carousel_graph()
        bad['carousel']['controls'] = {'nextElementId': 'missing-next'}
        with self.assertRaisesRegex(ValueError, 'matching transition edges'):
            web_design.validate_graph(bad)

    def test_signed_plan_cannot_change_carousel_edges(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            value = carousel_graph()
            write_carousel_evidence(Path(d))
            src.write_text(json.dumps(value))
            out = Path(d) / 'plan.json'
            web_design.build_plan(src, 'file', '1:1', out)
            plan = json.loads(out.read_text())
            plan['web_design']['carousel']['transitions'][0]['to'] = 'feature-4'
            with self.assertRaisesRegex(ValueError, 'exactly match the pinned canonical transition graph'):
                native_edit.validate_plan(plan)

    def test_signed_plan_cannot_omit_a_carousel_screen(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            write_carousel_evidence(Path(d))
            src.write_text(json.dumps(carousel_graph()))
            plan_path = Path(d) / 'plan.json'
            web_design.build_plan(src, 'file', '1:1', plan_path)
            plan = json.loads(plan_path.read_text())
            plan['web_design']['screens'].pop()
            with self.assertRaisesRegex(ValueError, 'include every pinned carousel state'):
                native_edit.validate_plan(plan)

    def test_forged_plan_cannot_change_pinned_screen_content_or_graph_edges(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            src.write_text(json.dumps(graph()))
            plan_path = Path(d) / 'plan.json'
            web_design.build_plan(src, 'file', '1:1', plan_path)
            plan = json.loads(plan_path.read_text())
            plan['web_design']['screens'][0]['elements'][0]['text']['characters'] = 'Forged'
            with self.assertRaisesRegex(ValueError, 'exactly match selected pinned canonical screen content'):
                native_edit.validate_plan(plan)
            source = json.loads(src.read_text())
            source['edges'] = [{'from': 'WEB-home', 'to': 'missing', 'type': 'evidence'}]
            src.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, 'source graph changed'):
                native_edit.validate_plan(json.loads(plan_path.read_text()))

    def test_rejects_unpinned_or_unsafe_geometry_and_assets(self):
        bad = graph()
        bad['nodes'][0]['elements'][0]['box']['x'] = float('nan')
        with self.assertRaises(ValueError):
            web_design.validate_graph(bad)
        for svg in (
            '<svg><script/></svg>',
            '<svg><path onclick="alert(1)"/></svg>',
            '<svg><path fill="url(https://x)"/></svg>',
        ):
            bad = graph()
            element = bad['nodes'][0]['elements'][0]
            element['kind'] = 'vector'
            element['svg'] = svg
            with self.subTest(svg=svg), self.assertRaises(ValueError):
                web_design.validate_graph(bad)

    def test_local_svg_clip_references_and_hash_pinned_video_fallback_are_bounded(self):
        sample = graph()
        element = sample['nodes'][0]['elements'][0]
        element.update(kind='vector', svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<g clip-path="url(#clip0)"><path d="M0 0h10v10H0z" fill="#ffffff" fill-rule="evenodd"/></g>'
            '<defs><clipPath id="clip0"><rect x="0" y="0" width="10" height="10"/></clipPath></defs></svg>'
        ))
        self.assertEqual(len(web_design.validate_graph(sample)), 1)
        element['svg'] = element['svg'].replace('url(#clip0)', 'url(#missing)')
        with self.assertRaisesRegex(ValueError, 'resolve locally'):
            web_design.validate_graph(sample)
        element['svg'] = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<defs><linearGradient id="paint0" x1="0" y1="0" x2="10" y2="10" gradientUnits="userSpaceOnUse">'
            '<stop offset="0" stop-color="#000000"/><stop offset="100%" stop-color="#ffffff" stop-opacity="0.5"/>'
            '</linearGradient></defs><path d="M0 0h10v10H0z" fill="url(#paint0)"/></svg>'
        )
        self.assertEqual(len(web_design.validate_graph(sample)), 1)
        element['svg'] = element['svg'].replace('paint0)', 'missing)')
        with self.assertRaisesRegex(ValueError, 'resolve locally'):
            web_design.validate_graph(sample)
        element.pop('svg')
        element.update(
            kind='video', objectFit='cover',
            asset={'path': 'media/a.mp4', 'sha256': 'a' * 64, 'mimeType': 'video/mp4'},
            fallbackAsset={'path': 'media/a.png', 'sha256': 'b' * 64, 'mimeType': 'image/png'},
        )
        self.assertEqual(len(web_design.validate_graph(sample)), 1)
        element['fallbackAsset']['mimeType'] = 'image/gif'
        with self.assertRaisesRegex(ValueError, 'supported raster fallback'):
            web_design.validate_graph(sample)

    def test_screen_selection_and_image_signature_are_enforced(self):
        data = b'not a png'
        digest = hashlib.sha256(data).hexdigest()
        sample = graph()
        image = dict(
            id='hero-image',
            kind='image',
            box={'x': 0, 'y': 0, 'width': 10, 'height': 10},
            asset={'path': 'hero.png', 'sha256': digest, 'mimeType': 'image/png'},
        )
        sample['nodes'][0]['elements'].append(image)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            src.write_text(json.dumps(sample))
            (Path(d) / 'hero.png').write_bytes(data)
            plan = Path(d) / 'bad.json'
            web_design.build_plan(src, 'file', '1:1', plan)
            with self.assertRaises(ValueError):
                native_edit.prepare(plan, Path(d) / 'plugin')
            with self.assertRaises(ValueError):
                web_design.build_plan(src, 'file', '1:1', Path(d) / 'missing.json', ['WEB-absent'])

    def test_full_length_plan_deduplicates_verified_local_raster_content(self):
        with tempfile.TemporaryDirectory() as d:
            asset = b'\x89PNG\r\n\x1a\n' + b'bounded representative raster bytes'
            digest = hashlib.sha256(asset).hexdigest()
            asset_path = Path(d) / 'assets/shared.png'
            asset_path.parent.mkdir()
            asset_path.write_bytes(asset)
            source = Path(d) / 'capture.json'
            source.write_text(json.dumps(representative_graph('assets/shared.png', digest)))
            plan = Path(d) / 'plan.json'
            web_design.build_plan(source, 'file', '1:1', plan, preview_width=420)
            self.assertLess(plan.stat().st_size, 400_000)
            native = json.loads(plan.read_text())
            native_edit.validate_plan(native)
            self.assertEqual(native['web_design']['preview_width'], 420)
            self.assertFalse(
                any(
                    'data' in element.get('asset', {})
                    for screen in native['web_design']['screens']
                    for element in screen['elements']
                )
            )
            bundle = Path(d) / 'bundle'
            native_edit.prepare(plan, bundle)
            code = (bundle / 'code.js').read_text()
            encoded = base64.b64encode(asset).decode()
            self.assertEqual(code.count(encoded), 1)
            pins = json.loads((bundle / 'source-inputs.json').read_text())['pins']
            self.assertEqual(len(pins), len({row['path'] for row in pins}))
            self.assertEqual(pins[0]['path'], str(plan.resolve()))
            self.assertEqual(
                pins[1], {'path': str(source.resolve()), 'sha256': native['web_design']['graph_sha256']}
            )
            self.assertEqual(pins[2], {'path': str(asset_path.resolve()), 'sha256': digest})
            import subprocess

            result = subprocess.run(
                ['node', '--check', str(bundle / 'code.js')], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_prepare_builds_graph_panel_bundle_and_bridge_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'graph.json'
            src.write_text(json.dumps(graph()))
            plan = Path(d) / 'plan.json'
            web_design.build_plan(src, 'file', '1:1', plan)
            out = Path(d) / 'plugin'
            native_edit.prepare(plan, out)
            code = (out / 'code.js').read_text()
            self.assertIn('async function webApply(figma, plan)', code)
            self.assertIn('figma-flow-web-design-id', code)
            import subprocess

            result = subprocess.run(['node', '--check', str(out / 'code.js')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
