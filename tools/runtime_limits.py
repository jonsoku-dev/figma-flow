"""Shared size/count/geometry/timing limits (SSoT: ``library/runtime-limits.json``)."""
from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

LIMITS_PATH = Path(__file__).resolve().parents[1] / 'library' / 'runtime-limits.json'


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    return value


def _validate(node, path='') -> None:
    for key, value in node.items():
        where = f'{path}.{key}' if path else key
        if isinstance(value, dict):
            _validate(value, where)
        elif type(value) not in (int, float) or not value > 0:
            raise ValueError(f'Runtime limit {where} must be a positive number')


def _load(path: Path = LIMITS_PATH):
    data = json.loads(path.read_bytes())
    if data.get('schema') != 'figma-flow-runtime-limits-v1':
        raise ValueError('Unknown runtime limits schema')
    groups = {key: value for key, value in data.items() if isinstance(value, dict)}
    _validate(groups)
    return _freeze(groups)


LIMITS = _load()
NETWORK = LIMITS['network']
WEB_DESIGN = LIMITS['webDesign']
EVIDENCE = LIMITS['evidence']
TCP_PORTS = range(1, NETWORK['maxTcpPort'] + 1)
UNPRIVILEGED_PORTS = range(NETWORK['minUnprivilegedPort'], NETWORK['maxTcpPort'] + 1)
