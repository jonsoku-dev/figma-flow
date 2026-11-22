"""Reservation rules shared by the HTTP form, transactional service and database model."""
import json
from pathlib import Path


def load_group_bounds():
    bounds = json.loads(Path(__file__).with_suffix('.json').read_bytes())['groupSize']
    low, high = bounds['minimum'], bounds['maximum']
    if type(low) is not int or type(high) is not int or not 1 <= low <= high <= 32767:
        raise ValueError('Booking group bounds must fit a positive small integer.')
    return low, high


MIN_GROUP_SIZE, MAX_GROUP_SIZE = load_group_bounds()
