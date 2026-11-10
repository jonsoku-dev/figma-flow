"""Measure image base64 that is serialized into a Figma plugin's JS payload."""
import re

WARNING_BYTES = 4_000_000
IMAGE_URI = re.compile(r'data:image/[\w.+-]+;base64,([A-Za-z0-9+/]+=*)', re.IGNORECASE)


def embedded_asset_warnings(payload_json, raw_assets=()):
    size = sum(len(asset) for asset in raw_assets)
    size += sum(match.end(1) - match.start(1) for match in IMAGE_URI.finditer(payload_json))
    if size > WARNING_BYTES:
        return [f'Embedded assets total {size / 1_000_000:.2f} MB ({size:,} base64 bytes). '
                'Figma may be slow to load this plugin.']
    return []
