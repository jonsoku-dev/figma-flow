"""Shared limits used by the native relay, Codex readers, and the published UI."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMITS_FILE = Path('library/figma-profile/read-limits.json')


def read_limits(root=ROOT):
    data = json.loads((root / LIMITS_FILE).read_bytes())
    if type(data.get('maxNodes')) is not int or data['maxNodes'] <= 0:
        raise ValueError('Read limits require a positive integer maxNodes')
    return data


def control_transport(policy):
    limits = policy['controlTransport']
    def positive(value):
        return type(value) is int and 0 < value <= 2**53-1
    for field in ('replyBytes','historyDetailReplyBytes','readinessReplyBytes'):
        if not positive(limits.get(field)):
            raise ValueError(f'Invalid control transport field: {field}')
    for field in ('normal','largeRead'):
        frame = limits[field]
        if (not positive(frame.get('bodyBytes')) or not positive(frame.get('readbackBytes'))
                or frame['bodyBytes'] < frame['readbackBytes']):
            raise ValueError(f'Invalid control transport envelope: {field}')
    if any(limits['normal'][key] >= limits['largeRead'][key] for key in ('bodyBytes','readbackBytes')):
        raise ValueError('Large signed reads require a larger envelope than ordinary traffic')
    return limits


MAX_NODES = read_limits()['maxNodes']
