#!/usr/bin/env python3
"""Rank exact-key Plugin API audit rows for evidence gathering, without claiming runtime support."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_api_coverage import observed_member_evidence
from figma_api_inventory import inherited_members, load as load_catalog
from native_api_probe import SAFE_METHODS

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'library/figma-api/audit/members.json'
OBSERVATIONS = ROOT / 'specs/graph-review/api-observations.json'
OUTPUT_SCHEMA = 'figma-flow-api-priority-v1'

ROLE_TERMS = {
    'designer': ('fill', 'stroke', 'color', 'font', 'text', 'layout', 'node', 'component', 'style', 'effect', 'export', 'geometry', 'paint', 'vector', 'corner', 'constraint', 'opacity', 'rotation', 'width', 'height'),
    'developer': ('node', 'parent', 'children', 'plugin', 'code', 'devresource', 'property', 'document', 'selection', 'event', 'message', 'metadata', 'component', 'variable', 'style', 'export', 'font'),
    'planner': ('page', 'section', 'component', 'instance', 'library', 'variable', 'style', 'node', 'team', 'project', 'selection', 'document', 'export', 'design'),
}
NODE_TYPE = re.compile(r"(?:readonly )?type: ['\"]([A-Z_]+)['\"]")
READONLY_OWNER_HINTS = ('Node', 'Mixin', 'PluginAPI', 'Document', 'Page', 'Style', 'Paint', 'Text')
EDITOR_BLOCKERS = ('figjam', 'slides', 'sites', 'buzz', 'draw')
PERMISSION_TERMS = ('permission', 'private', 'proposed', 'restricted', 'enablePrivatePluginApi')


def _status(row):
    return row.get('release_status', {}).get('candidate', {}).get('status', 'unresolved')


def _receivers(audit, catalog):
    member_keys = {}
    for item in audit['members']:
        member_keys.setdefault((item['owner'], item['name'], item['signature']), []).append(item['key'])
    result = {item['key']: set() for item in audit['members']}
    for node in catalog['nodes']:
        matches = [NODE_TYPE.fullmatch(signature) for signature in node.get('type_signatures', [])]
        node_types = {match.group(1) for match in matches if match}
        if not node_types:
            continue
        for member in inherited_members(catalog, node['name']):
            for key in member_keys.get((member['owner'], member['name'], member['signature']), []):
                result[key].update(node_types)
    return {key: sorted(values) for key, values in result.items()}


def _priority(row, evidence, receiver_types):
    name = row.get('name', '').casefold()
    raw_name = row.get('name', '')
    owner = row.get('owner', '')
    declaration = row.get('official_declaration', {})
    restrictions = declaration.get('restrictions', [])
    docs = (row.get('signature', '') + ' ' + str(row.get('type_surface', {}).get('class', ''))
            + ' ' + ' '.join(str(item) for item in restrictions)).casefold()
    surface = row.get('type_surface', {}).get('class', 'unresolved-owner-member')
    kind = row.get('kind', '')
    method = kind == 'MethodSignature'
    getter_like = kind == 'PropertySignature' and row.get('readonly') is True
    editors = declaration.get('documented_editors', [])
    permissions = declaration.get('required_permissions', [])
    restricted = declaration.get('restricted_access') is True
    type_only = surface == 'type-contract-member'
    unknown_owner = surface == 'unresolved-owner-member'
    editor_blocked = bool(editors and 'figma' not in editors) or any(term in docs for term in EDITOR_BLOCKERS)
    permission_gated = bool(permissions) or restricted or any(term.lower() in docs for term in PERMISSION_TERMS)
    runtime_class = surface in ('runtime-api-member', 'runtime-object-member')
    feasible = 'read-only-property' if getter_like and runtime_class else (
        'read-only-method' if method and runtime_class and raw_name in SAFE_METHODS else
        'owned-disposable-method' if method and runtime_class else
        'type-only' if type_only else 'receiver-unresolved' if unknown_owner else
        'editor-or-permission-gated' if editor_blocked or permission_gated else 'needs-classification')
    # Score is an ordering aid only. It never changes audit or evidence status.
    role_scores = {role: min(5, sum(term in name for term in terms)) for role, terms in ROLE_TERMS.items()}
    value = sum(role_scores.values())
    receiver = 0 if runtime_class and any(hint in owner for hint in READONLY_OWNER_HINTS) else 2
    feasibility = {'read-only-property': 0, 'read-only-method': 1, 'owned-disposable-method': 2,
                   'needs-classification': 3, 'receiver-unresolved': 4,
                   'type-only': 5, 'editor-or-permission-gated': 6}[feasible]
    role_matches = {role: [term for term in terms if term in name]
                    for role, terms in ROLE_TERMS.items()}
    matched_roles = [role for role, terms in role_matches.items() if terms]
    receiver_list = receiver_types or ([owner] if runtime_class and surface == 'runtime-api-member' else [])
    reasons = []
    if matched_roles:
        reasons.append('Name matches useful API areas for ' + ', '.join(matched_roles) + '.')
    else:
        reasons.append('Name has no direct match to the designer, developer, or planner term lists.')
    reasons.append({'read-only-property': 'Read-only property on a catalogued runtime surface.',
        'read-only-method': 'Method is an explicit static read-only allowlist entry with bounded output.',
        'owned-disposable-method': 'Method requires an owned disposable target before any call.',
        'needs-classification': 'Runtime surface exists, but safety or receiver applicability needs review.',
        'receiver-unresolved': 'Audit has no resolved runtime receiver surface.',
        'type-only': 'Declaration is a type contract without an executable runtime receiver.',
        'editor-or-permission-gated': 'Editor or permission requirements need explicit setup.'}[feasible])
    if receiver_list:
        reasons.append('Catalogued receiver types: ' + ', '.join(receiver_list[:8]) +
                       (' and more.' if len(receiver_list) > 8 else '.'))
    else:
        reasons.append('No concrete node receiver type is mapped in the pinned catalog.')
    return {'priority_score': value * 10 - feasibility * 2 - receiver,
            'role_value': role_scores, 'feasibility': feasible,
            'role_matches': role_matches, 'priority_reasons': reasons,
            'receiver_types': receiver_list,
            'receiver_basis': ('pinned-node-inheritance' if receiver_types else
                               'catalogued-api-namespace' if surface == 'runtime-api-member' else
                               'runtime-owner-unmapped' if runtime_class else 'unresolved'),
            'access': 'read-only' if getter_like else 'method' if method else 'index-or-type',
            'method_requirement': ('read-only-static-allowlist' if feasible == 'read-only-method' else
                                  'owned-disposable-target' if feasible == 'owned-disposable-method' else
                                  'not-callable-with-current-probe' if method else 'none'),
            'editor_requirement': ('other-or-unknown' if editor_blocked else
                                   'figma' if 'figma' in editors else
                                   'undocumented' if not editors else 'other-or-unknown'),
            'permission_requirement': 'required' if permission_gated else 'none-declared',
            'evidence_status': ('observed-in-observation-graph' if evidence else _status(row)),
            'observation_evidence': evidence}


def build(audit=None, graph=None, overlays=None, catalog=None):
    audit = audit or json.loads(AUDIT.read_text())
    graph = graph or json.loads(OBSERVATIONS.read_text())
    catalog = catalog or load_catalog()
    overlay_graphs = overlays or []
    graph_evidence = observed_member_evidence(audit, graph)
    graph_ids = {graph.get('id')}
    for overlay in overlay_graphs:
        if overlay.get('id') in graph_ids:
            raise ValueError('Observation graph IDs must be unique across base and overlays.')
        graph_ids.add(overlay.get('id'))
        overlay_evidence = observed_member_evidence(audit, overlay, require_receipts=True)
        for key, sources in overlay_evidence.items():
            graph_evidence.setdefault(key, []).extend(sources)
    graph_evidence_ids = {}
    for sources in graph_evidence.values():
        for source in sources:
            graph_evidence_ids.setdefault(source['graph_id'], set()).add(source['evidence_id'])
    all_ids = [evidence_id for ids in graph_evidence_ids.values() for evidence_id in ids]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('Observation evidence IDs must be unique across graphs.')
    observed = set(graph_evidence)
    receivers = _receivers(audit, catalog)
    rows = []
    for item in audit.get('members', []):
        key = item.get('key')
        if not isinstance(key, str) or not key.startswith('member:'):
            raise ValueError('Every audit row must have an exact member key.')
        rank = _priority(item, graph_evidence.get(key, []), receivers.get(key, []))
        rows.append({'api_member_id': key, 'owner': item.get('owner'), 'name': item.get('name'),
                     'kind': item.get('kind'), 'signature': item.get('signature'),
                     'readonly': item.get('readonly'), 'optional': item.get('optional'),
                     'release_status': _status(item), 'type_surface': item.get('type_surface'),
                     'official_declaration': item.get('official_declaration'),
                     'route': item.get('route'), 'candidate_evidence': item.get('evidence'),
                     **rank})
    rows.sort(key=lambda row: (-row['priority_score'], row['api_member_id']))
    payload = {'schema': OUTPUT_SCHEMA, 'source': {'audit': str(AUDIT.relative_to(ROOT)),
        'observations': str(OBSERVATIONS.relative_to(ROOT)), 'audit_member_count': len(rows),
        'observed_graph_member_ids': len(observed), 'base_observation_graph_id': graph['id'],
        'overlay_graph_ids': [item['id'] for item in overlay_graphs],
        'already_observed_members': sum(row['evidence_status'] in ('observed', 'observed-in-observation-graph')
                                        for row in rows),
        'unobserved_members': sum(row['evidence_status'] not in ('observed', 'observed-in-observation-graph')
                                  for row in rows)},
        'ranking_rules': {'role_value': ROLE_TERMS,
        'feasibility_order': ['read-only-property', 'read-only-method', 'owned-disposable-method',
                'needs-classification', 'receiver-unresolved', 'type-only',
                'editor-or-permission-gated'],
            'score_formula': '10 * sum(clamped role-term matches) - 2 * feasibility rank - receiver penalty',
            'runtime_claims': 'None. Status is copied from the audit or exact observed graph nodes.'},
        'rows': rows}
    payload['sha256'] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    return payload


def queue(payload, *, limit=50, receiver=None, feasible_only=False):
    rows = [row for row in payload['rows']
            if row['evidence_status'] not in ('observed', 'observed-in-observation-graph')]
    if feasible_only:
        rows = [row for row in rows if row['feasibility'] in
                ('read-only-property', 'read-only-method', 'owned-disposable-method')]
    if receiver:
        rows = [row for row in rows if receiver.casefold() in str(row['owner']).casefold()
                or receiver.casefold() in row['signature'].casefold()]
    return rows[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build_cmd = sub.add_parser('build', help='Build complete exact-key ranked inventory')
    build_cmd.add_argument('--audit', type=Path)
    build_cmd.add_argument('--observations', type=Path)
    build_cmd.add_argument('--overlay', type=Path, action='append', default=[],
                           help='Additional sanitized observation graph. May be repeated; overlays require fresh timestamped receipts.')
    build_cmd.add_argument('--out', type=Path, required=True)
    queue_cmd = sub.add_parser('queue', help='Print the next unobserved exact-key rows')
    queue_cmd.add_argument('--inventory', type=Path, required=True)
    queue_cmd.add_argument('--limit', type=int, default=50)
    queue_cmd.add_argument('--receiver', help='Filter by owner or declared receiver name')
    queue_cmd.add_argument('--feasible-only', action='store_true',
                           help='Keep only read-only properties and methods needing owned disposable targets')
    args = parser.parse_args(argv)
    if args.command == 'build':
        audit = json.loads((args.audit or AUDIT).read_text())
        graph = json.loads((args.observations or OBSERVATIONS).read_text())
        overlays = [json.loads(path.read_text()) for path in args.overlay]
        result = build(audit, graph, overlays=overlays)
        args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        print(json.dumps({'path': str(args.out), 'rows': len(result['rows']),
                          'observed_graph_member_ids': result['source']['observed_graph_member_ids'],
                          'sha256': result['sha256']}))
    else:
        if args.limit < 1 or args.limit > 10000:
            parser.error('--limit must be between 1 and 10000')
        payload = json.loads(args.inventory.read_text())
        if payload.get('schema') != OUTPUT_SCHEMA:
            parser.error('Unsupported API priority inventory schema')
        print(json.dumps({'schema': OUTPUT_SCHEMA, 'unobserved_members': payload['source']['unobserved_members'],
            'queue': queue(payload, limit=args.limit, receiver=args.receiver,
                           feasible_only=args.feasible_only)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
