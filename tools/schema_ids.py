"""Wire schema IDs shared by more than one file (SSoT: ``library/schema-ids.json``).

Python code reads IDs from :data:`ID` instead of repeating ``figma-flow-*-vN`` literals.
JavaScript bundles cannot import this module, so their copies are declared as
``mirrors`` in the registry and verified by ``tools/ssot_scan.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from types import MappingProxyType

REGISTRY_PATH = Path(__file__).resolve().parents[1] / 'library' / 'schema-ids.json'
_PATTERN = re.compile(r'figma-flow-[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+')


def _load(path: Path = REGISTRY_PATH) -> MappingProxyType:
    data = json.loads(path.read_bytes())
    if data.get('schema') != 'figma-flow-schema-id-registry-v1' or not isinstance(data.get('ids'), dict):
        raise ValueError('Unknown schema ID registry')
    ids = {}
    for name, entry in data['ids'].items():
        value = entry.get('id') if isinstance(entry, dict) else None
        if not isinstance(value, str) or not _PATTERN.fullmatch(value) or value in ids.values():
            raise ValueError(f'Invalid schema ID registry entry: {name}')
        ids[name] = value
    return MappingProxyType(ids)


ID = _load()
