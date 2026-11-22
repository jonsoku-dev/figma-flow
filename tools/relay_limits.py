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


MAX_NODES = read_limits()['maxNodes']
