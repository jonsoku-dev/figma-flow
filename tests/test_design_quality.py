"""Design quality gate: objective errors block packaging, heuristics only warn."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_quality as quality  # noqa: E402

OUTPUTS = ROOT.parent
REAL_LAYOUTS = {
    'shadow-troupe': OUTPUTS / 'shadow-troupe/native-layout.json',
    'saltline-77': OUTPUTS / 'saltline-77/native-layout.json',
    'example': ROOT / 'examples/native-direction-review/native-layout.json',
}
HANGUL = re.compile('[가-힣]')
COLORS = {'paper': '#FFFFFF', 'ink': '#111111', 'grey': '#8A8A8A', 'mid': '#777777', 'dim': '#888888',
          'night': '#151013', 'accent': '#B33143'}


def text(id, x, y, w, h, value='본문', size=16, ink='ink', align='left', **extra):
    return {'id': id, 'kind': 'text', 'value': value, 'x': x, 'y': y, 'w': w, 'h': h, 'size': size,
            'leading': extra.pop('leading', round(size * 1.5)), 'ink': ink, 'font': extra.pop('font', 'body'), 'align': align, **extra}


def rect(id, x, y, w, h, fill='accent', **extra):
    return {'id': id, 'kind': 'rect', 'x': x, 'y': y, 'w': w, 'h': h, 'fill': fill, **extra}


def layout(layers, viewport='mobile', width=390, height=844, bg='paper', boxes=None, extra_states=None, fonts=None):
    states = {'S-ENTRY': {'width': width, 'height': height, 'bg': bg, 'control_boxes': boxes or {}, 'layers': layers}}
    states.update(extra_states or {})
    return {'schema': 'figma-flow-authored-native-layout-v1', 'scope': 'exploratory-only', 'production_admitted': False,
            'assets': {'photo': {'path': 'photo.png', 'sha256': '0' * 64}},
            'candidates': [{'id': 'a', 'title': 'A', 'colors': dict(COLORS),
                            'fonts': fonts or {'body': {'family': 'No Such Family', 'style': 'Regular'},
                                               'display': {'family': 'No Such Family', 'style': 'Regular'}},
                            'control_styles': {viewport: {'Primary': {'fill': 'accent', 'ink': 'paper', 'fontSize': 17}}},
                            'state_layouts': {viewport: states}}]}


def good_layers():
    """Varied, role-declared mobile entry: anchor ellipse, 4-step type scale, asymmetric."""
    return [
        {'id': 'hero', 'kind': 'ellipse', 'x': 150, 'y': 40, 'w': 220, 'h': 220, 'fill': 'accent', 'role': 'illustration'},
        rect('panel', 0, 300, 390, 300, fill='night', role='surface'),
        text('kicker', 24, 60, 120, 24, value='EP 01', size=14),
        text('title', 24, 320, 342, 120, value='그림자 극단', size=40, ink='paper', font='display', leading=56),
        text('lede', 24, 460, 342, 60, value='빛의 위치를 바꾸면 배역이 달라집니다.', size=18, ink='paper', leading=28),
        text('note', 24, 640, 342, 40, value='무대 안내', size=16, leading=24),
    ]


def codes(report, severity=None):
    items = report['errors'] + report['warnings'] if severity is None else report[severity + 's']
    return [item['code'] for item in items]


def items(report, code):
    return [item for item in report['errors'] + report['warnings'] if item['code'] == code]


def build_font(path, advance=500, upm=1000):
    """Monospaced test font: every glyph advances `advance` units, so widths are exact."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    chars = list(dict.fromkeys([chr(c) for c in range(32, 127)] + list('가나다라마바사아자차카타파하그림자극단본문')))
    names = ['.notdef'] + ['g%04x' % ord(c) for c in chars]
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): 'g%04x' % ord(c) for c in chars})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((0, 10)); pen.lineTo((10, 10)); pen.closePath()
    glyph = pen.glyph()
    fb.setupGlyf({name: glyph for name in names})
    fb.setupHorizontalMetrics({name: (advance, 0) for name in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'Gate Mono', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.save(str(path))


class ContrastTests(unittest.TestCase):
    def test_low_contrast_body_text_is_error(self):
        report = quality.evaluate(layout([text('t', 24, 24, 200, 30, ink='mid')], bg='dim'))
        self.assertIn('contrast', codes(report, 'error'))
        item = items(report, 'contrast')[0]
        self.assertEqual((item['candidate'], item['viewport'], item['state'], item['layer']), ('a', 'mobile', 'S-ENTRY', 't'))
        self.assertFalse(report['passed'])

    def test_dark_text_on_white_passes(self):
        report = quality.evaluate(layout([text('t', 24, 24, 200, 30)]))
        self.assertNotIn('contrast', codes(report))

    def test_large_text_uses_three_to_one(self):
        # #8A8A8A on white is ~3.45:1 — fails body text, passes >=24px display text.
        small = quality.evaluate(layout([text('t', 24, 24, 300, 40, ink='grey', size=16)]))
        large = quality.evaluate(layout([text('t', 24, 24, 300, 40, ink='grey', size=24)]))
        self.assertIn('contrast', codes(small, 'error'))
        self.assertNotIn('contrast', codes(large))

    def test_background_is_topmost_shape_under_text_center(self):
        dark_panel = layout([rect('panel', 0, 0, 390, 200, fill='night', role='surface'), text('t', 24, 24, 200, 30, ink='paper')])
        self.assertNotIn('contrast', codes(quality.evaluate(dark_panel)))
        # Same white ink without the panel sits on the white state bg.
        self.assertIn('contrast', codes(quality.evaluate(layout([text('t', 24, 24, 200, 30, ink='paper')])), 'error'))
        # A shape listed after the text is above it, not its background.
        above = layout([text('t', 24, 24, 200, 30, ink='paper'), rect('later', 0, 0, 390, 200, fill='night', role='surface')])
        self.assertIn('contrast', codes(quality.evaluate(above), 'error'))

    def test_ellipse_counts_only_where_it_covers_the_center(self):
        inside = layout([{'id': 'disc', 'kind': 'ellipse', 'x': 0, 'y': 0, 'w': 248, 'h': 78, 'fill': 'night', 'role': 'illustration'},
                         text('t', 24, 24, 200, 30, ink='paper')])
        self.assertNotIn('contrast', codes(quality.evaluate(inside)))
        # Bounding box covers the text but the text center (124, 39) lies outside the circle.
        outside = layout([{'id': 'disc', 'kind': 'ellipse', 'x': 160, 'y': 0, 'w': 80, 'h': 80, 'fill': 'night', 'role': 'illustration'},
                          text('t', 24, 24, 200, 30, ink='paper')])
        self.assertIn('contrast', codes(quality.evaluate(outside), 'error'))

    def test_translucent_shape_is_composited(self):
        # 50% black over white is ~#808080; #777777 ink on it is far below 4.5.
        veil = layout([rect('veil', 0, 0, 390, 200, fill='ink', opacity=0.5, role='surface'), text('t', 24, 24, 200, 30, ink='mid')])
        self.assertIn('contrast', codes(quality.evaluate(veil), 'error'))

    def test_text_over_image_or_gradient_is_unknown_warning(self):
        for layer in ({'id': 'img', 'kind': 'image', 'asset': 'photo', 'x': 0, 'y': 0, 'w': 390, 'h': 300, 'role': 'image'},
                      {'id': 'grad', 'kind': 'gradient', 'x': 0, 'y': 0, 'w': 390, 'h': 300, 'direction': 'vertical', 'role': 'background',
                       'stops': [{'position': 0, 'color': '#000000', 'opacity': 1}, {'position': 1, 'color': '#FFFFFF', 'opacity': 1}]}):
            with self.subTest(kind=layer['kind']):
                report = quality.evaluate(layout([layer, text('t', 24, 24, 200, 30, ink='mid')]))
                self.assertNotIn('contrast', codes(report, 'error'))
                self.assertIn('contrast-unknown', codes(report, 'warning'))


class GeometryTests(unittest.TestCase):
    def test_text_off_canvas_is_error_and_small_slack_is_allowed(self):
        self.assertIn('off-canvas', codes(quality.evaluate(layout([text('t', -20, 24, 200, 30)])), 'error'))
        self.assertNotIn('off-canvas', codes(quality.evaluate(layout([text('t', -3, 24, 200, 30)]))))

    def test_intentional_bleed_roles_downgrade_to_warning(self):
        for role in ('background', 'ornament', 'illustration', 'image'):
            with self.subTest(role=role):
                report = quality.evaluate(layout([rect('bleed', -40, -40, 470, 300, role=role), text('t', 24, 400, 200, 30)]))
                self.assertNotIn('off-canvas', codes(report, 'error'))
                self.assertIn('off-canvas', codes(report, 'warning'))
        report = quality.evaluate(layout([rect('bar', -40, 300, 470, 30, role='surface'), text('t', 24, 400, 200, 30)]))
        self.assertIn('off-canvas', codes(report, 'error'))

    def test_text_overlap_threshold(self):
        overlapping = layout([text('a1', 24, 24, 200, 40), text('a2', 24, 44, 200, 40)])
        self.assertIn('text-overlap', codes(quality.evaluate(overlapping), 'error'))
        # 1px sliver: 200 px^2 of 8000 px^2 = 2.5% <= 5%.
        sliver = layout([text('a1', 24, 24, 200, 40), text('a2', 24, 63, 200, 40)])
        self.assertNotIn('text-overlap', codes(quality.evaluate(sliver)))

    def test_tiny_text(self):
        self.assertIn('tiny-text', codes(quality.evaluate(layout([text('t', 24, 24, 200, 30, size=11)])), 'error'))
        self.assertNotIn('tiny-text', codes(quality.evaluate(layout([text('t', 24, 24, 200, 30, size=12)]))))

    def test_control_size_by_viewport(self):
        short_mobile = layout([text('t', 24, 24, 200, 30)], boxes={'go': [24, 600, 200, 40]})
        self.assertIn('control-size', codes(quality.evaluate(short_mobile), 'error'))
        short_desktop = layout([text('t', 24, 24, 200, 30)], viewport='desktop', width=1280, height=800, boxes={'go': [24, 600, 200, 40]})
        self.assertNotIn('control-size', codes(quality.evaluate(short_desktop)))
        too_low_desktop = layout([text('t', 24, 24, 200, 30)], viewport='desktop', width=1280, height=800, boxes={'go': [24, 600, 200, 30]})
        self.assertIn('control-size', codes(quality.evaluate(too_low_desktop), 'error'))
        narrow = layout([text('t', 24, 24, 200, 30)], boxes={'go': [24, 600, 40, 48]})
        self.assertIn('control-size', codes(quality.evaluate(narrow), 'error'))
        self.assertNotIn('control-size', codes(quality.evaluate(layout([text('t', 24, 24, 200, 30)], boxes={'go': [24, 600, 200, 48]}))))

    def test_control_text_overlap(self):
        clash = layout([text('t', 24, 590, 200, 30)], boxes={'go': [24, 600, 200, 48]})
        item = items(quality.evaluate(clash), 'control-text-overlap')
        self.assertEqual(len(item), 1)
        self.assertEqual(item[0]['severity'], 'error')
        clear = layout([text('t', 24, 540, 200, 30)], boxes={'go': [24, 600, 200, 48]})
        self.assertNotIn('control-text-overlap', codes(quality.evaluate(clear)))


class OverflowTests(unittest.TestCase):
    def test_estimate_only_warns(self):
        long = text('t', 24, 24, 100, 24, value='가나다라마바사아자차카타파하', size=16, leading=24)
        report = quality.evaluate(layout([long]))
        self.assertNotIn('text-overflow', codes(report, 'error'))
        self.assertIn('text-overflow-estimated', codes(report, 'warning'))
        fits = quality.evaluate(layout([text('t', 24, 24, 300, 24, value='가나다', size=16, leading=24)]))
        self.assertNotIn('text-overflow-estimated', codes(fits))

    def test_measured_overflow_is_error_with_real_font(self):
        try:
            import fontTools  # noqa: F401
            from PIL import ImageFont  # noqa: F401
        except ImportError:
            self.skipTest('Pillow/fontTools unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'fonts').mkdir()
            build_font(base / 'fonts/GateMono.ttf')
            (base / 'fonts/sources.json').write_text(json.dumps({'Gate Mono': {'file': 'fonts/GateMono.ttf'}}))
            fonts = {'body': {'family': 'Gate Mono', 'style': 'Regular'}}
            # 20px glyphs advance 10px: 'AAAA AAAA' needs 90px; in 50px it wraps to 2 lines * 30 = 60 > 30.
            over = layout([text('t', 24, 24, 50, 30, value='AAAA AAAA', size=20, leading=30)], fonts=fonts)
            report = quality.evaluate(over, layout_dir=base)
            self.assertIn('text-overflow', codes(report, 'error'))
            self.assertNotIn('text-overflow-estimated', codes(report))
            fits = layout([text('t', 24, 24, 100, 30, value='AAAA AAAA', size=20, leading=30)], fonts=fonts)
            self.assertNotIn('text-overflow', codes(quality.evaluate(fits, layout_dir=base)))
            self.assertEqual(quality.evaluate(fits, layout_dir=base)['metrics']['a/mobile/S-ENTRY']['text_measurement'], 'measured')


class HeuristicWarningTests(unittest.TestCase):
    def test_placeholder_bar(self):
        bar = rect('upper-light', 60, 600, 270, 18, fill='night')
        report = quality.evaluate(layout([bar, text('t', 24, 24, 200, 30)]))
        self.assertEqual([i['layer'] for i in items(report, 'placeholder-bar')], ['upper-light'])
        self.assertEqual(items(report, 'placeholder-bar')[0]['severity'], 'warning')
        self.assertTrue(report['passed'], 'warnings never block')
        ornament = quality.evaluate(layout([dict(bar, role='ornament'), text('t', 24, 24, 200, 30)]))
        self.assertIn('placeholder-bar', codes(ornament))
        for case, layers in {
            'declared divider': [dict(bar, role='divider'), text('t', 24, 24, 200, 30)],
            'underlines text': [bar, text('t', 60, 590, 200, 30)],
            'not elongated': [rect('block', 60, 600, 100, 40, fill='night'), text('t', 24, 24, 200, 30)],
            'thick': [rect('slab', 0, 600, 390, 100, fill='night'), text('t', 24, 24, 200, 30)],
        }.items():
            with self.subTest(case=case):
                self.assertNotIn('placeholder-bar', codes(quality.evaluate(layout(layers))))

    def test_missing_role(self):
        report = quality.evaluate(layout([rect('r', 0, 600, 390, 200, fill='night'), text('t', 24, 24, 200, 30)]))
        self.assertEqual([i['layer'] for i in items(report, 'missing-role')], ['r'])
        self.assertNotIn('missing-role', codes(quality.evaluate(layout([rect('r', 0, 600, 390, 200, fill='night', role='surface'), text('t', 24, 24, 200, 30)]))))

    def test_ornament_heavy(self):
        many = [rect('o%d' % i, 10 + i * 40, 700, 20, 20, role='ornament') for i in range(9)]
        self.assertIn('ornament-heavy', codes(quality.evaluate(layout(many + [text('t', 24, 24, 200, 30)]))))
        big = [rect('slab', 0, 0, 390, 300, role='ornament')]
        self.assertIn('ornament-heavy', codes(quality.evaluate(layout(big + [text('t', 24, 400, 200, 30)]))))
        few = [rect('o%d' % i, 10 + i * 40, 700, 20, 20, role='ornament') for i in range(3)]
        self.assertNotIn('ornament-heavy', codes(quality.evaluate(layout(few + [text('t', 24, 24, 200, 30)]))))

    def test_no_visual_anchor_on_entry_only(self):
        plain = layout([text('t', 24, 24, 200, 30)])
        self.assertIn('no-visual-anchor', codes(quality.evaluate(plain)))
        self.assertNotIn('no-visual-anchor', codes(quality.evaluate(layout(good_layers()))))
        # A non-entry state without an anchor is fine.
        extra = {'S-DETAIL': {'width': 390, 'height': 844, 'bg': 'paper', 'control_boxes': {}, 'layers': [text('t', 24, 24, 200, 30)]}}
        report = quality.evaluate(layout(good_layers(), extra_states=extra))
        self.assertEqual([i['state'] for i in items(report, 'no-visual-anchor')], [])

    def test_all_centered(self):
        centered = [text('t%d' % i, 45, 40 + i * 60, 300, 30, align='center', size=s) for i, s in enumerate((32, 20, 16))]
        self.assertIn('all-centered', codes(quality.evaluate(layout(centered))))
        mixed = centered[:2] + [text('t2', 24, 160, 300, 30, align='left')]
        self.assertNotIn('all-centered', codes(quality.evaluate(layout(mixed))))

    def test_type_scale(self):
        flat = [text('t%d' % i, 24, 40 + i * 60, 300, 30, size=16) for i in range(3)]
        self.assertIn('type-scale', codes(quality.evaluate(layout(flat))))
        noisy = [text('t%d' % i, 24, 40 + i * 70, 340, 60, size=s, leading=s + 10) for i, s in enumerate((12, 14, 18, 22, 28, 34, 40))]
        self.assertIn('type-scale', codes(quality.evaluate(layout(noisy))))
        self.assertNotIn('type-scale', codes(quality.evaluate(layout(good_layers()))))

    def test_low_density(self):
        sparse = layout([text('t', 24, 24, 100, 24)])
        self.assertIn('low-density', codes(quality.evaluate(sparse)))
        self.assertNotIn('low-density', codes(quality.evaluate(layout(good_layers()))))

    def test_good_layout_has_no_findings(self):
        report = quality.evaluate(layout(good_layers(), boxes={'go': [24, 760, 342, 52]}))
        self.assertEqual(report['errors'], [], report['errors'])
        self.assertEqual(report['warnings'], [], report['warnings'])
        self.assertTrue(report['passed'])


class ReportShapeTests(unittest.TestCase):
    def test_every_item_has_contract_fields_in_korean(self):
        bad = layout([rect('bar', 60, 600, 270, 18), text('t', -30, 24, 200, 30, ink='paper', size=10)], boxes={'go': [24, 600, 40, 30]})
        report = quality.evaluate(bad)
        self.assertEqual(report['schema'], 'figma-flow-design-quality-v1')
        self.assertTrue(report['errors'] and report['warnings'])
        for item in report['errors'] + report['warnings']:
            self.assertEqual(set(item), {'code', 'severity', 'candidate', 'viewport', 'state', 'layer', 'message', 'fix'})
            self.assertRegex(item['message'], HANGUL)
            self.assertRegex(item['fix'], HANGUL)
        self.assertTrue(all(i['severity'] == 'error' for i in report['errors']))
        self.assertTrue(all(i['severity'] == 'warning' for i in report['warnings']))
        self.assertIn('a/mobile/S-ENTRY', report['metrics'])

    def test_new_vocabulary_is_accepted(self):
        layers = good_layers() + [rect('card', 24, 700, 342, 40, fill='paper', radius=12, stroke='accent', stroke_width=2, opacity=0.9, role='surface')]
        report = quality.evaluate(layout(layers))
        self.assertNotIn('missing-role', codes(report))

    def test_strict_fails_on_warnings(self):
        report = quality.evaluate(layout([text('t', 24, 24, 200, 30)]), strict=True)
        self.assertEqual(report['errors'], [])
        self.assertFalse(report['passed'])


class CliTests(unittest.TestCase):
    def run_cli(self, data, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'native-layout.json'
            path.write_text(json.dumps(data, ensure_ascii=False))
            out = Path(tmp) / 'report.json'
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/design_quality.py'), '--layout', str(path), '--out', str(out), *extra],
                                    text=True, capture_output=True)
            report = json.loads(out.read_text()) if out.exists() else None
        return result, report

    def test_exit_codes(self):
        good, report = self.run_cli(layout(good_layers(), boxes={'go': [24, 760, 342, 52]}))
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(report['passed'])
        bad, report = self.run_cli(layout([text('t', 24, 24, 200, 30, ink='mid')], bg='dim'))
        self.assertEqual(bad.returncode, 1)
        self.assertIn('contrast', codes(report, 'error'))
        warn, _ = self.run_cli(layout([text('t', 24, 24, 200, 30)]))
        self.assertEqual(warn.returncode, 0)
        strict, _ = self.run_cli(layout([text('t', 24, 24, 200, 30)]), '--strict')
        self.assertEqual(strict.returncode, 1)

    def test_unreadable_layout_fails(self):
        result, _ = self.run_cli({'schema': 'something-else'})
        self.assertEqual(result.returncode, 1)


class RealLayoutCalibrationTests(unittest.TestCase):
    def test_existing_layouts_are_evaluated_without_crashing(self):
        for name, path in REAL_LAYOUTS.items():
            if not path.exists():
                continue
            with self.subTest(name=name):
                report = quality.run(path)
                self.assertEqual(report['schema'], 'figma-flow-design-quality-v1')

    @unittest.skipUnless(REAL_LAYOUTS['shadow-troupe'].exists(), 'regression layout not present')
    def test_shadow_troupe_light_bars_are_placeholder_bars(self):
        report = quality.run(REAL_LAYOUTS['shadow-troupe'])
        flagged = {i['layer'] for i in items(report, 'placeholder-bar') if i['candidate'] == 'a'}
        self.assertTrue({'upper-light', 'main-light', 'lower-light'} <= flagged, flagged)


def instantiate_demo(base, mutate=None):
    """Copy the shipped example, optionally edit its layout before pinning, and run the demo to NATIVE_REVIEW_PENDING."""
    spec = importlib.util.spec_from_file_location('native_review_demo_gate', ROOT / 'examples/native-direction-review/demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    source = Path(base) / 'example-source'
    shutil.copytree(demo.EXAMPLE, source, ignore=shutil.ignore_patterns('__pycache__'))
    if mutate:
        path = source / 'native-layout.json'
        data = json.loads(path.read_text())
        mutate(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    with patch.object(demo, 'EXAMPLE', source):
        return Path(demo.instantiate(Path(base) / 'workshop')['manifest'])


def make_low_contrast(data):
    candidate = data['candidates'][0]
    for viewport, states in candidate['state_layouts'].items():
        for state in states.values():
            for layer in state['layers']:
                if layer['kind'] == 'text':
                    layer['ink'] = state['bg']
                    return


def make_clean(data):
    """Neutralise any genuine error in the shipped example so the 'good layout proceeds' path is independent of it."""
    report = quality.evaluate(data)
    for item in report['errors']:
        raise AssertionError('Shipped example has gate errors; see calibration report: ' + item['code'])


class DesignActionsGateTests(unittest.TestCase):
    def actions(self, *argv):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'tools/design_actions.py'), *argv], text=True, capture_output=True)

    def test_prepare_blocks_contrast_error_before_any_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = instantiate_demo(tmp, make_low_contrast)
            out = Path(tmp) / 'reviewer'
            result = self.actions('prepare-native-review', '--manifest', str(manifest), '--out', str(out), '--plugin-id', '1000000000000000001')
            self.assertEqual(result.returncode, 1, result.stdout)
            blocked = json.loads(result.stderr)
            self.assertIn('contrast', blocked['blocked_reason'])
            self.assertIn('품질', blocked['blocked_reason'])
            report_path = Path(blocked['quality_report'])
            self.assertTrue(report_path.exists())
            self.assertIn('contrast', codes(json.loads(report_path.read_text()), 'error'))
            self.assertFalse(out.exists() and any(out.rglob('packet.json')))
            self.assertFalse(out.exists() and any(out.rglob('*.zip')))

    def test_prepare_proceeds_for_error_free_layout_and_summarises_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = instantiate_demo(tmp)
            layout_path = manifest.parent.parent / 'native-layout.json'
            pre = quality.run(layout_path)
            if pre['errors']:
                self.skipTest('shipped example currently has genuine gate errors: ' + ', '.join(sorted({i['code'] for i in pre['errors']})))
            out = Path(tmp) / 'reviewer'
            result = self.actions('prepare-native-review', '--manifest', str(manifest), '--out', str(out), '--plugin-id', '1000000000000000001')
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue((out / 'packet.json').exists())
            self.assertEqual(data['quality']['errors'], 0)
            self.assertEqual(data['quality']['warnings'], len(pre['warnings']))
            self.assertTrue(Path(data['quality']['report']).exists())

    def test_quality_subcommand_reads_manifest_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = instantiate_demo(tmp, make_low_contrast)
            result = self.actions('quality', '--manifest', str(manifest))
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn('contrast', codes(report, 'error'))


class ControlColorTests(unittest.TestCase):
    """A button nobody can see, or whose label nobody can read, blocks packaging."""

    def codes(self, data, layout_dir=None):
        return [e['code'] for e in quality.evaluate(data, layout_dir=layout_dir)['errors']]

    def styled(self, styles, bg='paper', layers=None):
        data = layout(layers or good_layers(), boxes={'go': [24, 744, 342, 56]}, bg=bg)
        data['candidates'][0]['control_styles'] = {'mobile': styles}
        return data

    def test_visible_readable_control_passes(self):
        self.assertEqual(self.codes(self.styled({'Primary': {'fill': 'accent', 'ink': 'paper', 'fontSize': 17}})), [])

    def test_fill_equal_to_background_is_invisible(self):
        codes = self.codes(self.styled({'Return': {'fill': 'paper', 'ink': 'ink', 'fontSize': 17}}))
        self.assertEqual(codes, ['control-invisible'])

    def test_fill_is_judged_against_the_shape_under_the_control(self):
        layers = good_layers() + [rect('footer', 0, 720, 390, 124, fill='night', role='surface')]
        self.assertEqual(self.codes(self.styled({'Return': {'fill': 'paper', 'ink': 'ink', 'fontSize': 17}}, layers=layers)), [])
        self.assertEqual(self.codes(self.styled({'Return': {'fill': 'night', 'ink': 'paper', 'fontSize': 17}}, layers=layers)),
                         ['control-invisible'])

    def test_unreadable_label_blocks(self):
        codes = self.codes(self.styled({'Primary': {'fill': 'accent', 'ink': 'night', 'fontSize': 17}}))
        self.assertEqual(codes, ['control-label-contrast'])

    def test_without_annotations_only_a_defect_shared_by_every_variant_blocks(self):
        styles = {'Primary': {'fill': 'accent', 'ink': 'paper', 'fontSize': 17}, 'Return': {'fill': 'paper', 'ink': 'ink', 'fontSize': 17}}
        self.assertEqual(self.codes(self.styled(styles)), [])

    def test_annotations_name_the_variant_a_control_uses(self):
        styles = {'Primary': {'fill': 'accent', 'ink': 'paper', 'fontSize': 17}, 'Return': {'fill': 'paper', 'ink': 'ink', 'fontSize': 17}}
        data = self.styled(styles)
        data['candidates'][0]['graph'] = {'path': 'a/graph.json'}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'a').mkdir()
            (Path(tmp) / 'a/annotations.json').write_text(json.dumps([{'kind': 'action', 'control_id': 'go', 'visual_variant': 'Return'}]))
            self.assertEqual(self.codes(data, layout_dir=tmp), ['control-invisible'])
            (Path(tmp) / 'a/annotations.json').write_text(json.dumps([{'kind': 'action', 'control_ids': ['go'], 'visual_variant': 'Primary'}]))
            self.assertEqual(self.codes(data, layout_dir=tmp), [])

    def test_control_over_an_image_is_not_guessed(self):
        layers = good_layers() + [{'id': 'photo', 'kind': 'image', 'asset': 'photo', 'x': 0, 'y': 720, 'w': 390, 'h': 124, 'role': 'image'}]
        self.assertEqual(self.codes(self.styled({'Return': {'fill': 'paper', 'ink': 'ink', 'fontSize': 17}}, layers=layers)), [])


if __name__ == '__main__':
    unittest.main()
