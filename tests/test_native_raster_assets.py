"""Authored photo readback must match its pinned packet bytes."""
import base64
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_draft as draft

ROOT = Path(__file__).resolve().parents[1]
demo_spec = importlib.util.spec_from_file_location('native_raster_demo', ROOT / 'examples/native-direction-review/demo.py')
demo = importlib.util.module_from_spec(demo_spec)
demo_spec.loader.exec_module(demo)


ASSET = base64.b64encode(b'photo-bytes').decode()


def fixture():
    layer = {'id': 'photo', 'kind': 'image', 'asset': 'cover', 'x': 0, 'y': 0, 'w': 100, 'h': 80}
    node = {
        'id': 'photo-node', 'type': 'RECTANGLE', 'parentId': 'frame', 'rasterAsset': 'cover',
        'rasterImageBytes': ASSET, 'visible': True, 'opacity': 1,
        'fills': [{'type': 'IMAGE', 'imageHash': 'hash', 'scaleMode': 'FIT'}],
    }
    return layer, node, {'cover': ASSET}


class NativeRasterAssets(unittest.TestCase):
    def test_exact_native_photo_bytes_and_paint_pass(self):
        layer, node, assets = fixture()
        self.assertEqual(draft._native_authored_image_findings(node, layer, assets, 'screen.photo'), [])

    def test_screen_verifier_rejects_wrong_native_photo_readback(self):
        layer, photo, assets = fixture()
        photo.update(parentId='frame', x=0, y=0, width=100, height=80)
        frame = {'id': 'frame', 'type': 'FRAME', 'parentId': 'page', 'x': 0, 'y': 0, 'width': 100, 'height': 80}
        candidate = {
            'id': 'screen', 'state_layouts': {'desktop': {'idle': {'width': 100, 'height': 80, 'layers': [layer], 'control_boxes': {}}}},
            'prototype': {'bindings': []}, 'action_notes': {}, 'action_labels': {}, 'control_styles': {'desktop': {}},
        }
        keyed = {'screen.desktop.idle': frame, 'screen.desktop.idle.photo': photo}
        self.assertEqual(draft.native_screen_findings(candidate, 'desktop', 'idle', frame, keyed, page_id='page', assets=assets), [])
        photo['rasterImageBytes'] = base64.b64encode(b'changed-photo').decode()
        codes = {item['code'] for item in draft.native_screen_findings(candidate, 'desktop', 'idle', frame, keyed, page_id='page', assets=assets)}
        self.assertIn('image-asset-drift', codes)

    def test_wrong_or_missing_native_photo_bytes_fail(self):
        for field, value in [('rasterImageBytes', base64.b64encode(b'changed-photo').decode()), ('rasterImageBytes', None), ('rasterAsset', 'other')]:
            layer, node, assets = fixture()
            node[field] = value
            with self.subTest(field=field, value=value):
                self.assertIn('image-asset-drift', {item['code'] for item in draft._native_authored_image_findings(node, layer, assets, 'screen.photo')})

    def test_wrong_node_paint_scale_mode_visibility_and_opacity_fail(self):
        cases = [('type', 'ELLIPSE'), ('visible', False), ('opacity', .5)]
        for field, value in cases:
            layer, node, assets = fixture()
            node[field] = value
            with self.subTest(field=field):
                findings = draft._native_authored_image_findings(node, layer, assets, 'screen.photo')
                self.assertIn('image-missing' if field == 'type' else 'visibility-drift' if field == 'visible' else 'image-opacity-drift', {item['code'] for item in findings})
        for field, value in [('type', 'SOLID'), ('scaleMode', 'FILL')]:
            layer, node, assets = fixture()
            node['fills'][0][field] = value
            with self.subTest(field=field):
                self.assertIn('image-asset-drift', {item['code'] for item in draft._native_authored_image_findings(node, layer, assets, 'screen.photo')})
        layer, node, assets = fixture()
        layer['fit'] = 'CROP'
        node['fills'][0]['scaleMode'] = 'CROP'
        self.assertEqual(draft._native_authored_image_findings(node, layer, assets, 'screen.photo'), [])

    def test_make_packet_checks_format_dimensions_and_preserves_supported_bytes(self):
        from io import BytesIO
        from PIL import Image

        def raster(format, size):
            output = BytesIO()
            Image.new('RGB', size, '#7293a8').save(output, format=format)
            return output.getvalue()

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / 'project'
            fixture = demo.instantiate(project)
            manifest_path = Path(fixture['manifest'])
            manifest = json.loads(manifest_path.read_text())
            layout_path = Path(manifest['native_layout']['path'])
            layout = json.loads(layout_path.read_text())

            def pin_asset(name, format, size):
                relative = f'previews/{name}.{format.lower()}'
                path = layout_path.parent / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                data = raster(format, size)
                path.write_bytes(data)
                layout['assets'][name] = {'path': relative, 'sha256': hashlib.sha256(data).hexdigest()}
                layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
                pin = {'path': str(layout_path), 'sha256': hashlib.sha256(layout_path.read_bytes()).hexdigest()}
                manifest['native_layout'] = pin
                if manifest.get('native_target', {}).get('layout') is not None:
                    manifest['native_target']['layout'] = pin
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
                return data

            png = pin_asset('boundary', 'PNG', (4096, 1))
            jpeg = pin_asset('photo', 'JPEG', (1, 1))
            packet = draft.make_packet(manifest_path)
            self.assertEqual(base64.b64decode(packet['assets']['boundary'], validate=True), png)
            self.assertEqual(base64.b64decode(packet['assets']['photo'], validate=True), jpeg)

            pin_asset('boundary', 'PNG', (4097, 1))
            with self.assertRaisesRegex(ValueError, r"boundary.*4097x1.*4096"):
                draft.make_packet(manifest_path)

            bmp = pin_asset('boundary', 'BMP', (1, 1))
            with self.assertRaisesRegex(ValueError, r"boundary.*unsupported format BMP.*PNG, JPEG, or GIF"):
                draft.make_packet(manifest_path)
            path = layout_path.parent / layout['assets']['boundary']['path']
            self.assertTrue(bmp.startswith(b'BM'))
            path.write_bytes(b'not an image')
            layout['assets']['boundary']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
            pin = {'path': str(layout_path), 'sha256': hashlib.sha256(layout_path.read_bytes()).hexdigest()}
            manifest['native_layout'] = pin
            if manifest.get('native_target', {}).get('layout') is not None:
                manifest['native_target']['layout'] = pin
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            with self.assertRaisesRegex(ValueError, r"boundary.*malformed.*PNG, JPEG, or GIF"):
                draft.make_packet(manifest_path)

            pixels = bytes(index * 37 % 256 for index in range(128 * 128 * 3))
            image = Image.frombytes('RGB', (128, 128), pixels)
            output = BytesIO()
            image.save(output, format='JPEG', quality=95)
            encoded = output.getvalue()
            truncated = encoded[:len(encoded) // 2]
            path.write_bytes(truncated)
            layout['assets']['boundary']['sha256'] = hashlib.sha256(truncated).hexdigest()
            layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
            pin = {'path': str(layout_path), 'sha256': hashlib.sha256(layout_path.read_bytes()).hexdigest()}
            manifest['native_layout'] = pin
            if manifest.get('native_target', {}).get('layout') is not None:
                manifest['native_target']['layout'] = pin
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            with self.assertRaisesRegex(ValueError, r"boundary.*malformed.*PNG, JPEG, or GIF"):
                draft.make_packet(manifest_path)


if __name__ == '__main__':
    unittest.main()
