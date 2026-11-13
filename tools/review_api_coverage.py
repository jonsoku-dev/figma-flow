#!/usr/bin/env python3
"""Join sanitized real-editor observations to the pinned per-member audit graph."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'library/figma-api/audit/members.json'
OBSERVATIONS = ROOT / 'specs/graph-review/api-observations.json'


def coverage(audit, observations):
    members = {row['key']: row for row in audit['members']}
    if len(members) != len(audit['members']):
        raise ValueError('Duplicate audit member')
    by_id = {node['id']: node for node in observations['nodes']}
    if len(by_id) != len(observations['nodes']):
        raise ValueError('Duplicate observation node')
    previous = {key for key, row in members.items() if row['release_status']['candidate']['status'] == 'observed'}
    live = set()
    for edge in observations['edges']:
        if edge['from'] not in by_id or edge['to'] not in by_id:
            raise ValueError('Unresolved observation edge')
        if edge['type'] != 'observed member':
            continue
        evidence, member = by_id[edge['from']], by_id[edge['to']]
        key = member['id']
        if (evidence.get('type') != 'test' or evidence.get('status') != 'observed' or
                member.get('type') != 'figma' or key not in members or not evidence.get('source') or
                member.get('title') != members[key]['owner'] + '.' + members[key]['name']):
            raise ValueError('Observation must identify the exact official member and runtime evidence')
        live.add(key)
    return {'baseline_release': '0.28.0', 'inventory_members': len(members),
            'baseline_observed': len(previous), 'this_release_observed': len(live),
            'newly_observed': len(live - previous), 'distinct_observed_through_release': len(previous | live),
            'remaining_without_live_member_evidence': len(members.keys() - previous - live)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=AUDIT)
    parser.add_argument('--observations', type=Path, default=OBSERVATIONS)
    args = parser.parse_args()
    result = coverage(json.loads(args.audit.read_bytes()), json.loads(args.observations.read_bytes()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
