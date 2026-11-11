"""0.17 native layer vocabulary: every new property is validated before any Figma write."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_draft as draft  # noqa: E402

COLORS = {'paper': '#FFFFFF', 'ink': '#111111', 'accent': '#AA4422'}
ASSETS = {'art': {'path': 'art.png', 'sha256': '0' * 64}}


def shipped_layouts():
    return sorted((ROOT / 'examples').glob('**/native-layout.json'))


def check(layer):
    draft.check_layer(layer, COLORS, ASSETS, 'a.mobile.S')


def shape(**extra):
    return {'id': 's', 'kind': 'rect', 'x': 0, 'y': 0, 'w': 100, 'h': 40, 'fill': 'paper', **extra}


def gradient(**extra):
    return {'id': 'g', 'kind': 'gradient', 'x': 0, 'y': 0, 'w': 100, 'h': 40, 'direction': 'vertical',
            'stops': [{'position': 0, 'color': '#000000', 'opacity': .2}, {'position': 1, 'color': '#FFFFFF', 'opacity': 0}], **extra}


class CheckLayerTests(unittest.TestCase):
    def test_image_fit_must_be_a_figma_scale_mode(self):
        for fit in ('FILL', 'FIT', 'CROP', 'TILE'):
            check({'id': 'i', 'kind': 'image', 'asset': 'art', 'x': 0, 'y': 0, 'w': 80, 'h': 80, 'fit': fit, 'role': 'image'})
        for fit in ('cover', 'fill', '', None):
            with self.assertRaisesRegex(ValueError, 'Image fit must be one of'):
                check({'id': 'i', 'kind': 'image', 'asset': 'art', 'x': 0, 'y': 0, 'w': 80, 'h': 80, 'fit': fit, 'role': 'image'})

    def test_new_vocabulary_is_accepted(self):
        check(shape(radius=20, stroke='accent', stroke_width=2, opacity=.5, role='surface'))
        check({'id': 'e', 'kind': 'ellipse', 'x': 0, 'y': 0, 'w': 80, 'h': 80, 'fill': 'accent', 'stroke': 'ink', 'stroke_width': 4,
               'opacity': 1, 'role': 'illustration'})
        check({'id': 'i', 'kind': 'image', 'asset': 'art', 'x': 0, 'y': 0, 'w': 80, 'h': 80, 'fit': 'FILL', 'opacity': .8, 'role': 'image'})

    def test_invalid_layers_fail_before_writing(self):
        cases = {
            'unknown kind': ({'id': 'v', 'kind': 'vector', 'x': 0, 'y': 0, 'w': 1, 'h': 1}, 'Only declared native draft layer kinds'),
            'unknown property': (shape(blur=4), 'Undeclared native draft layer property blur'),
            'text radius': ({'id': 't', 'kind': 'text', 'value': 'x', 'x': 0, 'y': 0, 'w': 10, 'h': 10, 'size': 12, 'leading': 14,
                             'ink': 'ink', 'font': 'body', 'align': 'left', 'radius': 2}, 'Undeclared native draft layer property radius'),
            'stroke without width': (shape(stroke='accent'), 'stroke and stroke_width'),
            'width without stroke': (shape(stroke_width=2), 'stroke and stroke_width'),
            'zero stroke': (shape(stroke='accent', stroke_width=0), 'stroke_width must be'),
            'fat stroke': (shape(stroke='accent', stroke_width=21), 'stroke_width must be'),
            'undeclared stroke': (shape(stroke='ghost', stroke_width=2), 'Declared color role required for stroke'),
            'undeclared fill': (shape(fill='ghost'), 'Declared color role required for fill'),
            'radius beyond half': (shape(radius=21), 'radius must be'),
            'negative radius': (shape(radius=-1), 'radius must be'),
            'zero opacity': (shape(opacity=0), 'opacity'),
            'opacity above one': (shape(opacity=1.5), 'opacity'),
            'unknown role': (shape(role='hero'), 'Unknown native layer role'),
            'zero size': (shape(w=0), 'Finite positive native layer geometry'),
            'nan geometry': (shape(x=float('nan')), 'Finite positive native layer geometry'),
            'missing raster': ({'id': 'i', 'kind': 'image', 'asset': 'nope', 'x': 0, 'y': 0, 'w': 8, 'h': 8}, 'Pinned raster asset required'),
            'one gradient stop': (gradient(stops=[{'position': 0, 'color': '#000000', 'opacity': 1}]), 'at least two stops'),
            'short hex stop': (gradient(stops=[{'position': 0, 'color': '#000', 'opacity': 1}, {'position': 1, 'color': '#FFFFFF', 'opacity': 1}]), 'Gradient stops need'),
            'decreasing stops': (gradient(stops=[{'position': .8, 'color': '#000000', 'opacity': 1}, {'position': .2, 'color': '#FFFFFF', 'opacity': 1}]), 'Gradient stops need'),
            'stop opacity': (gradient(stops=[{'position': 0, 'color': '#000000', 'opacity': 2}, {'position': 1, 'color': '#FFFFFF', 'opacity': 1}]), 'Gradient stops need'),
            'diagonal': (gradient(direction='diagonal'), 'Gradient direction'),
        }
        for name, (layer, message) in cases.items():
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, message):
                check(layer)

    def test_every_shipped_authored_layer_still_validates(self):
        paths = shipped_layouts()
        check(gradient())
        seen = 0
        for path in [p for p in paths if p.exists()]:
            data = json.loads(path.read_text())
            for candidate in data['candidates']:
                for viewport, states in candidate['state_layouts'].items():
                    for state_id, state in states.items():
                        for layer in state['layers']:
                            draft.check_layer(layer, candidate['colors'], data['assets'], f"{candidate['id']}.{viewport}.{state_id}")
                            seen += 1
        self.assertGreater(seen, 0)

    def test_layout_discovery_preserves_neighbor_project_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'plugin'
            example = root / 'examples' / 'review' / 'native-layout.json'
            example.parent.mkdir(parents=True)
            example.write_text('{}')
            neighbor = Path(tmp) / 'other-project' / 'native-layout.json'
            neighbor.parent.mkdir()
            neighbor.write_text('not a plugin layout')
            with patch(__name__ + '.ROOT', root):
                self.assertEqual(shipped_layouts(), [example])


def instantiate_demo(base, mutate):
    spec = importlib.util.spec_from_file_location('native_review_demo_vocab', ROOT / 'examples/native-direction-review/demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    source = Path(base) / 'example-source'
    shutil.copytree(demo.EXAMPLE, source, ignore=shutil.ignore_patterns('__pycache__'))
    path = source / 'native-layout.json'
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    with patch.object(demo, 'EXAMPLE', source):
        return Path(demo.instantiate(Path(base) / 'workshop')['manifest'])


def entry_layers(data):
    candidate = data['candidates'][0]
    for states in candidate['state_layouts'].values():
        yield candidate, next(iter(states.values()))['layers']


def add_shapes(stroke):
    def mutate(data):
        for candidate, layers in entry_layers(data):
            ink = next(layer['ink'] for layer in layers if layer['kind'] == 'text')
            layers.insert(0, {'id': 'halo', 'kind': 'ellipse', 'x': 8, 'y': 8, 'w': 96, 'h': 96, 'fill': candidate['bg'] if 'bg' in candidate else ink,
                              'opacity': .2, 'role': 'illustration'})
            layers.insert(1, {'id': 'card', 'kind': 'rect', 'x': 8, 'y': 120, 'w': 160, 'h': 64, 'fill': ink, 'radius': 12,
                              'stroke': stroke or ink, 'stroke_width': 2, 'role': 'surface'})
    return mutate


class LayoutErrorsTests(unittest.TestCase):
    def test_every_problem_is_reported_at_once(self):
        data = json.loads((ROOT / 'examples/native-direction-review/native-layout.json').read_text())
        self.assertEqual(draft.layout_errors(data), [])
        state = next(iter(data['candidates'][0]['state_layouts']['desktop'].values()))
        control = next(iter(state['control_boxes']))
        state['layers'] += [shape(id=control), shape(id='dup'), shape(id='dup'), gradient(stops=[]),
                            {'id': 'note', 'kind': 'text', 'value': 'x', 'x': 0, 'y': 0, 'w': 10, 'h': 10, 'size': 14, 'leading': 20,
                             'ink': 'ink', 'font': 'serif', 'align': 'left'}]
        problems = draft.layout_errors(data)
        for fragment in ('collides with control id', 'duplicate layer id', 'at least two stops', "unknown font role 'serif'"):
            self.assertTrue(any(fragment in p for p in problems), (fragment, problems))

    def test_every_shipped_layout_is_clean(self):
        for path in shipped_layouts():
            with self.subTest(path=str(path)):
                self.assertEqual(draft.layout_errors(json.loads(path.read_text())), [])


class PacketTests(unittest.TestCase):
    def test_new_shapes_reach_the_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = instantiate_demo(tmp, add_shapes(None))
            packet = draft.make_packet(manifest)
            kinds = {layer['kind'] for c in packet['candidates'] for states in c['state_layouts'].values()
                     for state in states.values() for layer in state['layers']}
            self.assertIn('ellipse', kinds)
            card = next(layer for c in packet['candidates'] for states in c['state_layouts'].values()
                        for state in states.values() for layer in state['layers'] if layer['id'] == 'card')
            self.assertEqual((card['radius'], card['stroke_width']), (12, 2))

    def test_undeclared_stroke_stops_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Rejected while the draft itself is created, so no review manifest or packet ever exists.
            with self.assertRaisesRegex(ValueError, "Unknown/unbound authored paint name 'ghost'"):
                instantiate_demo(tmp, add_shapes('ghost'))
            self.assertFalse(any(Path(tmp).rglob('packet.json')))


if __name__ == '__main__':
    unittest.main()
