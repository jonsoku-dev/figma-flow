"""Null is an explicit control fill; pixel/source checks do not claim Figma execution."""
import tempfile
import unittest
from pathlib import Path
from test_draft_color_consumers import source_fixture, authored_color_consumers
from test_native_control_icons import draft
from test_design_quality_pixels import quality, Image, document, picture


class TransparentControls(unittest.TestCase):
    def test_named_consumers_skip_only_explicit_null_for_prototype_and_product(self):
        source, graph = source_fixture()
        for viewport in ('desktop', 'mobile'):
            source['control_styles'][viewport]['Return']['fill'] = None
            source['control_styles'][viewport]['Return']['stroke'] = 'ink'
            source['state_layouts'][viewport]['DETAIL']['product_buttons'] = {'clear': {'box': [10, 190, 100, 46], 'variant': 'Return', 'label': 'Clear'}}
        rows = authored_color_consumers(source, graph)
        targets = [target for row in rows for target in row['consumers']]
        for viewport in ('desktop', 'mobile'):
            for control in ('back', 'clear'):
                key = f'x.{viewport}.DETAIL.{control}'
                self.assertNotIn({'key': key, 'field': 'fills'}, targets)
                self.assertIn({'key': key, 'field': 'strokes'}, targets)
                self.assertIn({'key': key+'.label', 'field': 'fills'}, targets)
        del source['control_styles']['desktop']['Return']['fill']
        with self.assertRaisesRegex(ValueError, 'Unknown/unbound authored paint'):
            authored_color_consumers(source, graph)

    def test_actual_getters_require_empty_fills_and_no_binding(self):
        for key in ('x.desktop.component.Return', 'x.desktop.DETAIL.back', 'x.desktop.DETAIL.clear', 'review.palette.x.Return'):
            self.assertEqual(draft._native_control_fill_findings({'fills': []}, {'fill': None}, key), [])
            for node in ({}, {'fills': [{'type': 'SOLID'}]}, {'fills': [], 'boundVariables': {'fills': [{'id': 'v'}]}}):
                self.assertEqual(draft._native_control_fill_findings(node, {'fill': None}, key)[0]['layer'], key)
            self.assertEqual(draft._native_control_fill_findings({}, {'fill': 'paper'}, key), [])

    @unittest.skipUnless(Image, 'Pillow required for composite background proof')
    def test_transparent_label_uses_underlying_pixels_and_remains_text_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for color, failing in [((0,0,0,255), False), ((255,255,255,255), True)]:
                import hashlib
                path=root/'art.png';Image.new('RGBA',(64,64),color).save(path)
                assets={'art': {'path':'art.png','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
                doc=document([picture()],assets)
                candidate=doc['candidates'][0]
                candidate['control_styles']['mobile']['Return']={'fill':None,'ink':'paper','fontSize':16,'paddingX':4,'paddingY':4}
                state=candidate['state_layouts']['mobile']['entry']
                state['product_buttons']={'back': {'variant':'Return','label':'Back','box':[4,4,56,48]}}
                report=quality.evaluate(doc,root)
                errors=[item['code'] for item in report['errors']]
                self.assertEqual('control-label-contrast' in errors,failing)
                self.assertNotIn('control-invisible',errors)
                measured=report['metrics']['a/mobile/entry']['contrast_measurements']['back.label']
                self.assertEqual(measured['method'],'pinned-raster-composite-all-bounding-pixels')
                self.assertEqual(measured['min_ratio'],1 if failing else 21)
