#!/usr/bin/env python3
"""Check owned example provenance and delegate NF-01 compile/prepare to core tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import design_system  # noqa: E402
import figma_bridge  # noqa: E402

PRIVATE_LEAK_RE = re.compile(r'(#id_password|password=|sessionid=|csrfmiddlewaretoken|https?://)', re.I)


def check_example_provenance(data, *, manifest_path=HERE / 'manifest.json'):
    """Check lightweight MIT/sample-only safety boundaries; core compiler owns NF-01 validation."""
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('version must be 1')
    raw_text = json.dumps(data, ensure_ascii=False)
    if PRIVATE_LEAK_RE.search(raw_text) or ('/' + 'Users/') in raw_text:
        raise ValueError('forbidden secret, external URL, or personal path in example input')
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if manifest.get('license') != 'MIT' or manifest.get('ssot') != 'design.json':
        raise ValueError('owned example manifest must declare MIT license and design.json SSOT')
    return {
        'example_id': manifest.get('example_id'),
        'license': manifest.get('license'),
        'ssot': manifest.get('ssot'),
    }


def prepare_bundle(input_path, out_dir, *, plugin_id=None, selection=None, product_graph=None, draft_only=False):
    """Delegate compilation, HTML/SVG previews, and Figma plugin packaging to repo core tools."""
    data = json.loads(Path(input_path).read_text(encoding='utf-8'))
    provenance = check_example_provenance(data)

    out_dir = Path(out_dir)
    preview_dir = out_dir / 'preview'
    plugin_dir = out_dir / 'plugin'
    preview_dir.mkdir(parents=True, exist_ok=True)

    resolved = design_system.compile_design(data)
    resolved_path = preview_dir / 'resolved.json'
    resolved_bytes = (json.dumps(resolved, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    resolved_path.write_bytes(resolved_bytes)

    wireframe_html, wireframe_css = design_system.render(resolved, styled=False)
    styled_html, _ = design_system.render(resolved, styled=True)
    (preview_dir / 'tokens.css').write_text(wireframe_css, encoding='utf-8')
    (preview_dir / 'wireframe.html').write_text(wireframe_html, encoding='utf-8')
    (preview_dir / 'styled.html').write_text(styled_html, encoding='utf-8')
    for screen in resolved['screens']:
        (preview_dir / f"{screen['id']}-wireframe.svg").write_text(
            design_system.render_svg(resolved, screen, styled=False),
            encoding='utf-8',
        )
        (preview_dir / f"{screen['id']}-styled.svg").write_text(
            design_system.render_svg(resolved, screen, styled=True),
            encoding='utf-8',
        )

    reviewed_sha256 = hashlib.sha256(resolved_bytes).hexdigest()
    bridge_result = figma_bridge.compile_plugin(
        resolved_path,
        reviewed_sha256,
        plugin_dir,
        plugin_id=plugin_id,
        selection_path=selection,
        product_graph=product_graph,
        draft_only=draft_only,
    )
    return {
        'provenance': provenance,
        'status': resolved.get('status'),
        'resolved': str(resolved_path),
        'resolved_sha256': reviewed_sha256,
        'plugin': bridge_result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=HERE / 'design.json')
    parser.add_argument('--out', type=Path, required=True, help='Output directory for compiled preview + plugin bundle.')
    parser.add_argument('--plugin-id', help='Numeric Figma plugin ID for compile_plugin.')
    parser.add_argument('--selection', type=Path, help='Reviewed selection receipt path for strict plugin build.')
    parser.add_argument('--product-graph', type=Path, help='Pinned product graph path for strict plugin build.')
    parser.add_argument('--draft-only', action='store_true', help='Write non-native draft bundle via figma_bridge.')
    args = parser.parse_args()

    result = prepare_bundle(
        args.input,
        args.out,
        plugin_id=args.plugin_id,
        selection=args.selection,
        product_graph=args.product_graph,
        draft_only=args.draft_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
