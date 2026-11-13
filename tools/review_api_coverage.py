#!/usr/bin/env python3
"""Join sanitized real-editor observations to the pinned per-member audit graph."""
import argparse
from datetime import datetime, timezone
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'library/figma-api/audit/members.json'
OBSERVATIONS = ROOT / 'specs/graph-review/api-observations.json'
PUBLIC_OBSERVATION_OVERLAYS = (
    ROOT / 'specs/editable-web/api-observations.json',
    ROOT / 'specs/responsive-web/api-observations.json',
)
RECEIPT_SHA256 = re.compile(r'[a-f0-9]{64}\Z')


def _valid_observation_time(value):
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(timezone.utc)


def _validate_graph_shape(observations):
    if (not isinstance(observations, dict) or observations.get('version') != 1
            or not isinstance(observations.get('id'), str) or not observations['id'].strip()
            or not isinstance(observations.get('nodes'), list)
            or not isinstance(observations.get('edges'), list)
            or len(observations['nodes']) > 10000 or len(observations['edges']) > 100000):
        raise ValueError('Invalid API observation graph envelope')
    by_id = {}
    for node in observations['nodes']:
        if (not isinstance(node, dict) or not isinstance(node.get('id'), str)
                or not node['id'] or not isinstance(node.get('type'), str)):
            raise ValueError('Invalid observation graph node')
        if node['id'] in by_id:
            raise ValueError('Duplicate observation node')
        by_id[node['id']] = node
    edge_keys = set()
    for edge in observations['edges']:
        if (not isinstance(edge, dict) or not isinstance(edge.get('from'), str)
                or not isinstance(edge.get('to'), str) or not isinstance(edge.get('type'), str)
                or edge['from'] not in by_id or edge['to'] not in by_id):
            raise ValueError('Unresolved or malformed observation edge')
        edge_key = (edge['from'], edge['to'], edge['type'])
        if edge_key in edge_keys:
            raise ValueError('Duplicate observation edge')
        edge_keys.add(edge_key)
    return by_id


def observed_member_evidence(audit, observations, *, require_receipts=False):
    """Return exact member keys linked to observed evidence nodes in a validated graph."""
    members = {row['key']: row for row in audit['members']}
    if len(members) != len(audit['members']):
        raise ValueError('Duplicate audit member')
    by_id = _validate_graph_shape(observations)
    evidence_by_member = {}
    for edge in observations['edges']:
        if edge['type'] != 'observed member':
            continue
        evidence, member = by_id[edge['from']], by_id[edge['to']]
        key = member['id']
        counts = evidence.get('getter_counts')
        if (evidence.get('type') != 'test' or evidence.get('status') != 'observed'
                or member.get('type') != 'figma' or member.get('status') != 'observed'
                or key not in members or not isinstance(evidence.get('source'), str)
                or not evidence['source'].strip()
                or member.get('title') != members[key]['owner'] + '.' + members[key]['name']):
            raise ValueError('Observation edge must identify the exact official member and observed evidence node')
        receipt_sha = evidence.get('receipt_sha256')
        observed_at = evidence.get('observed_at')
        if require_receipts or receipt_sha is not None or observed_at is not None:
            if (not _valid_observation_time(observed_at)
                    or not isinstance(receipt_sha, str) or not RECEIPT_SHA256.fullmatch(receipt_sha)
                    or not isinstance(counts, dict) or isinstance(counts.get('success'), bool)
                    or not isinstance(counts.get('success'), int) or counts['success'] < 1):
                raise ValueError('New observation overlays require a timestamped receipt with successful calls')
        evidence_by_member.setdefault(key, []).append({
            'graph_id': observations['id'], 'evidence_id': evidence['id'],
            'observed_at': observed_at, 'receipt_sha256': receipt_sha})
    return evidence_by_member


def coverage(audit, observations):
    members = {row['key']: row for row in audit['members']}
    live = set(observed_member_evidence(audit, observations))
    previous = {key for key, row in members.items() if row['release_status']['candidate']['status'] == 'observed'}
    return {'baseline_release': '0.28.0', 'inventory_members': len(members),
            'baseline_observed': len(previous), 'this_release_observed': len(live),
            'newly_observed': len(live - previous), 'distinct_observed_through_release': len(previous | live),
            'remaining_without_live_member_evidence': len(members.keys() - previous - live)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=AUDIT)
    parser.add_argument('--observations', type=Path, default=OBSERVATIONS)
    parser.add_argument('--baseline-only', action='store_true', help='Show the original 0.29 report without later receipts.')
    args = parser.parse_args()
    audit = json.loads(args.audit.read_bytes())
    base = json.loads(args.observations.read_bytes())
    result = coverage(audit, base)
    if not args.baseline_only and args.observations.resolve() == OBSERVATIONS.resolve():
        baseline = {r['key'] for r in audit['members'] if r['release_status']['candidate']['status'] == 'observed'}
        baseline.update(observed_member_evidence(audit, base))
        release_030 = observed_member_evidence(audit, json.loads(PUBLIC_OBSERVATION_OVERLAYS[0].read_bytes()),
                                               require_receipts=True)
        baseline.update(release_030)
        release_031 = set(observed_member_evidence(audit, json.loads(PUBLIC_OBSERVATION_OVERLAYS[1].read_bytes()),
                                                   require_receipts=True))
        through_031 = baseline | release_031
        result.update(baseline_release='0.30.0', baseline_observed=len(baseline),
                      before_031_unobserved=len(audit['members']) - len(baseline),
                      this_release='0.31.0', this_release_observed=len(release_031),
                      newly_observed=len(release_031 - baseline),
                      distinct_observed_through_release=len(through_031),
                      remaining_without_live_member_evidence=len(audit['members']) - len(through_031))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
