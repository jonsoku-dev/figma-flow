import hashlib
import fcntl
import json
from pathlib import Path
import sys
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/little-hands/design'))
import publish_design_system
sys.path.insert(0, str(ROOT / 'tools'))
import graph_design_system
import graph_sync


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
            self.assertEqual({stat.S_IMODE(path.stat().st_mode) for path in (css, module, manifest)}, {0o644})
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
            self.assertEqual(data['nativeTokenNames']['color.action.primary'], 'ssot/little-hands/color/action/primary')
            graph = json.loads((ROOT / 'apps/little-hands/design/graph.json').read_text())
            self.assertEqual(data['nativeBindings']['button.bookingCTA']['mainKeys'], graph['design_system']['components']['button.bookingCTA']['native']['mainKeys'])
            namespace, native_names = graph_sync.token_native_names(graph, require_namespace=True)
            self.assertEqual(data['nativeNamespace'], namespace)
            self.assertEqual(data['nativeTokenNames'], native_names)
            self.assertIn('designFoundations', data)

    def test_css_variable_encoding_is_injective(self):
        names = ['color.bookingCta', 'color/bookingCta', 'color.book.ingCta', '色.予約']
        encoded = [publish_design_system.css_variable(name) for name in names]
        self.assertEqual(len(set(encoded)), len(names))
        self.assertTrue(all(name.startswith('--ff-token-') for name in encoded))

    def test_publisher_resolves_graph_once_for_all_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(publish_design_system, 'resolve_design_system',
                              wraps=graph_design_system.resolve_design_system) as resolve:
                publish_design_system.publish(css_path=root / 'design-system.css',
                    manifest_path=root / 'manifest.json', module_path=root / 'design-system.js')
            self.assertEqual(resolve.call_count, 1)

    def test_graph_lock_covers_all_publication_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_write = publish_design_system._atomic_write
            checked_modes = []

            def check_locked_write(path, content, *, mode=None):
                lock_path = publish_design_system.GRAPH.with_name(publish_design_system.GRAPH.name + '.lock')
                with lock_path.open('a+b') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                checked_modes.append(mode)
                real_write(path, content, mode=mode)

            with patch.object(publish_design_system, '_atomic_write', side_effect=check_locked_write):
                publish_design_system.publish(css_path=root / 'design-system.css',
                    manifest_path=root / 'manifest.json', module_path=root / 'design-system.js')
            self.assertEqual(checked_modes, [0o644, 0o644, 0o644])

    def test_ssr_uses_generated_css_and_only_tags_booking_controls(self):
        base = (ROOT / 'apps/little-hands/templates/base.html').read_text()
        detail = (ROOT / 'apps/little-hands/templates/booking/session_detail.html').read_text()
        self.assertIn("littlehands/design-system.css", base)
        self.assertEqual(detail.count('booking-cta'), 2)
        self.assertEqual(detail.count('data-graph-sha="{{ design_system_graph_sha }}"'), 2)
        self.assertNotIn('booking-cta', (ROOT / 'apps/little-hands/static/littlehands/app.css').read_text())
