import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/little-hands/design'))
import publish_design_system


class LittleHandsDesignSystemTests(unittest.TestCase):
    def test_publish_is_byte_stable_and_scoped_to_booking_cta(self):
        with tempfile.TemporaryDirectory() as directory:
            css = Path(directory) / 'design-system.css'
            manifest = Path(directory) / 'manifest.json'
            module = Path(directory) / 'design-system.js'
            first = publish_design_system.publish(css_path=css, manifest_path=manifest, module_path=module)
            first_css = css.read_bytes()
            first_module = module.read_bytes()
            second = publish_design_system.publish(css_path=css, manifest_path=manifest, module_path=module)
            self.assertEqual(first_css, css.read_bytes())
            self.assertEqual(first['cssSha256'], second['cssSha256'])
            self.assertEqual(first_module, module.read_bytes())
            self.assertEqual(first['cssSha256'], hashlib.sha256(first_css).hexdigest())
            self.assertEqual(first['moduleSha256'], hashlib.sha256(first_module).hexdigest())
            self.assertIn('export const graphSha256 =', first_module.decode())
            css_text = first_css.decode()
            primitive = publish_design_system.css_variable('color.bookingCta')
            semantic = publish_design_system.css_variable('color.action.primary')
            self.assertIn(f'{primitive}: #8e3e28;', css_text)
            self.assertIn(f'{semantic}: var({primitive});', css_text)
            self.assertIn(f'.booking-cta {{ background-color: var({semantic}); }}', css_text)
            self.assertNotIn('--color.', css_text)
            self.assertNotIn('rgba(', css_text)
            self.assertNotIn('.button.danger {', first_css.decode())
            data = json.loads(manifest.read_text())
            self.assertEqual(data['nativeBindings']['button.bookingCTA']['instanceKeys'], ['reserve-preview', 'reserve-login'])
            self.assertEqual(data['primitiveRoots']['color.action.primary'], 'color.bookingCta')
            self.assertEqual(data['nativeNamespace'], 'ssot/little-hands')
            self.assertEqual(data['nativeTokenNames']['color.action.primary'], 'ssot/little-hands/color.action.primary')
            graph = json.loads((ROOT / 'apps/little-hands/design/graph.json').read_text())
            self.assertEqual(data['nativeBindings']['button.bookingCTA']['mainKeys'], graph['design_system']['components']['button.bookingCTA']['native']['mainKeys'])

    def test_ssr_uses_generated_css_and_only_tags_booking_controls(self):
        base = (ROOT / 'apps/little-hands/templates/base.html').read_text()
        detail = (ROOT / 'apps/little-hands/templates/booking/session_detail.html').read_text()
        self.assertIn("littlehands/design-system.css", base)
        self.assertEqual(detail.count('booking-cta'), 2)
        self.assertEqual(detail.count('data-graph-sha="{{ design_system_graph_sha }}"'), 2)
        self.assertNotIn('booking-cta', (ROOT / 'apps/little-hands/static/littlehands/app.css').read_text())
