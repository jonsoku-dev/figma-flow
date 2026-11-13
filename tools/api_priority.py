#!/usr/bin/env python3
"""Rank exact-key Plugin API audit rows for evidence gathering, without claiming runtime support."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_api_coverage import AUDIT, OBSERVATIONS, PUBLIC_OBSERVATION_OVERLAYS, observed_member_evidence
from figma_api_inventory import inherited_members, load as load_catalog

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_SCHEMA = 'figma-flow-api-priority-v1'

ROLE_TERMS = {
    'designer': ('fill', 'stroke', 'color', 'font', 'text', 'layout', 'node', 'component', 'style', 'effect', 'export', 'geometry', 'paint', 'vector', 'corner', 'constraint', 'opacity', 'rotation', 'width', 'height'),
    'developer': ('node', 'parent', 'children', 'plugin', 'code', 'devresource', 'property', 'document', 'selection', 'event', 'message', 'metadata', 'component', 'variable', 'style', 'export', 'font'),
    'planner': ('page', 'section', 'component', 'instance', 'library', 'variable', 'style', 'node', 'team', 'project', 'selection', 'document', 'export', 'design'),
}
NODE_TYPE = re.compile(r"(?:readonly )?type: ['\"]([A-Z_]+)['\"]")
EDITOR_BLOCKERS = ('figjam', 'slides', 'sites', 'buzz', 'draw')
PERMISSION_TERMS = ('permission', 'private', 'proposed', 'restricted', 'enablePrivatePluginApi')

# Read operations have bounded, reviewed scenarios. All other methods remain research candidates.
READ_ONLY_METHODS = {
    ('BaseNodeMixin', 'getCSSAsync'): 'Read selected node CSS through the probe safe projection.',
    ('BaseNonResizableTextMixin', 'getRangeFontName'): 'Read a selected text range font without returning text.',
    ('BaseNonResizableTextMixin', 'getRangeFontSize'): 'Read a selected text range font size.',
    ('BaseNonResizableTextMixin', 'getRangeFontWeight'): 'Read the selected text range font weight.',
    ('BaseNonResizableTextMixin', 'getRangeFills'): 'Read bounded solid fills from a selected text range.',
    ('NonResizableTextMixin', 'getRangeLineHeight'): 'Read line height for a selected text range.',
    ('BaseNonResizableTextMixin', 'getRangeLetterSpacing'): 'Read letter spacing for a selected text range.',
    ('PluginAPI', 'listAvailableFontsAsync'): 'Select a font from this editor font list before applying range styles.',
}

# Only these signature owners have an approved node-scoped write scenario.
# All other write methods require a separate review and cannot be queued as executable.
OWNED_WRITE_METHODS = {
    ('BaseNonResizableTextMixin', 'setRangeFontName'): 'Apply the selected font to a range on an owned typography specimen.',
    ('BaseNonResizableTextMixin', 'setRangeFontSize'): 'Set the type scale on an owned typography specimen.',
    ('NonResizableTextMixin', 'setRangeLineHeight'): 'Set line height on an owned typography specimen.',
    ('BaseNonResizableTextMixin', 'setRangeLetterSpacing'): 'Set tracking on an owned typography specimen.',
    ('BaseNonResizableTextMixin', 'setRangeFills'): 'Set text color on an owned typography specimen.',
    ('LayoutMixin', 'resize'): 'Set geometry on an owned typography specimen frame.',
    ('PluginAPI', 'createComponentFromNode'): 'Convert only the newly created typography specimen into a reusable component.',
}

FEASIBILITY_TIER = {
    'readable-property': 700,
    'read-only-method': 650,
    'owned-write-method': 450,
    'method-needs-scenario': 250,
    'needs-classification': 150,
    'receiver-unresolved': 100,
    'type-only': 0,
    'editor-or-permission-gated': -1000,
}


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
    editors = declaration.get('documented_editors', [])
    permissions = declaration.get('required_permissions', [])
    restricted = declaration.get('restricted_access') is True
    type_only = surface == 'type-contract-member'
    unknown_owner = surface == 'unresolved-owner-member'
    editor_blocked = bool(editors and 'figma' not in editors) or any(term in docs for term in EDITOR_BLOCKERS)
    permission_gated = bool(permissions) or restricted or any(term.lower() in docs for term in PERMISSION_TERMS)
    runtime_class = surface in ('runtime-api-member', 'runtime-object-member')
    write_purpose = OWNED_WRITE_METHODS.get((owner, raw_name))
    if editor_blocked or permission_gated:
        feasible = 'editor-or-permission-gated'
    elif type_only:
        feasible = 'type-only'
    elif unknown_owner:
        feasible = 'receiver-unresolved'
    elif method and runtime_class and (owner, raw_name) in READ_ONLY_METHODS:
        feasible = 'read-only-method'
    elif method and runtime_class and write_purpose:
        feasible = 'owned-write-method'
    elif method and runtime_class:
        feasible = 'method-needs-scenario'
    elif kind == 'PropertySignature' and runtime_class:
        feasible = 'readable-property'
    else:
        feasible = 'needs-classification'
    # Score is an ordering aid only. It never changes audit or evidence status.
    role_scores = {role: min(5, sum(term in name for term in terms)) for role, terms in ROLE_TERMS.items()}
    value = sum(role_scores.values())
    receiver_count = len(receiver_types) or (1 if surface == 'runtime-api-member' else 0)
    role_matches = {role: [term for term in terms if term in name]
                    for role, terms in ROLE_TERMS.items()}
    matched_roles = [role for role, terms in role_matches.items() if terms]
    receiver_list = receiver_types or ([owner] if runtime_class and surface == 'runtime-api-member' else [])
    reasons = []
    if matched_roles:
        reasons.append('Name matches useful API areas for ' + ', '.join(matched_roles) + '.')
    else:
        reasons.append('Name has no direct match to the designer, developer, or planner term lists.')
    reasons.append({'readable-property': 'Property reads are safe even when the declaration permits writes.',
        'read-only-method': 'Method is an explicit static read-only allowlist entry with bounded output.',
        'owned-write-method': 'Method has a purpose-approved write scenario for an owned target.',
        'method-needs-scenario': 'Method has no approved read or owned-write invocation scenario.',
        'needs-classification': 'Runtime surface exists, but safety or receiver applicability needs review.',
        'receiver-unresolved': 'Audit has no resolved runtime receiver surface.',
        'type-only': 'Declaration is a type contract without an executable runtime receiver.',
        'editor-or-permission-gated': 'Editor or permission requirements need explicit setup.'}[feasible])
    if write_purpose:
        reasons.append(write_purpose)
    read_purpose = READ_ONLY_METHODS.get((owner, raw_name))
    if read_purpose:
        reasons.append(read_purpose)
    if receiver_list:
        reasons.append('Catalogued receiver types: ' + ', '.join(receiver_list[:8]) +
                       (' and more.' if len(receiver_list) > 8 else '.'))
    else:
        reasons.append('No concrete node receiver type is mapped in the pinned catalog.')
    return {'priority_score': FEASIBILITY_TIER[feasible] + value * 10 + min(receiver_count, 20),
            'role_value': role_scores, 'feasibility': feasible,
            'role_matches': role_matches, 'priority_reasons': reasons,
            'receiver_types': receiver_list,
            'receiver_basis': ('pinned-node-inheritance' if receiver_types else
                               'catalogued-api-namespace' if surface == 'runtime-api-member' else
                               'runtime-owner-unmapped' if runtime_class else 'unresolved'),
            'access': 'property-read' if kind == 'PropertySignature' else 'method' if method else 'index-or-type',
            'write_capability': ('readonly' if row.get('readonly') else 'writable-property')
                                if kind == 'PropertySignature' else
                                'approved-owned-write' if feasible == 'owned-write-method' else
                                'method-not-approved-for-write' if method else 'not-applicable',
            'method_requirement': ('purpose-approved-read-only-method-map' if feasible == 'read-only-method' else
                                  'owned-target-purpose-map' if feasible == 'owned-write-method' else
                                  'scenario-review-required' if method else 'none'),
            'editor_requirement': ('other-or-unknown' if editor_blocked else
                                   'figma' if 'figma' in editors else
                                   'undocumented' if not editors else 'other-or-unknown'),
            'permission_requirement': 'required' if permission_gated else 'none-declared',
            'evidence_status': ('observed-in-observation-graph' if evidence else _status(row)),
            'observation_evidence': evidence}


def build(audit=None, graph=None, overlays=None, catalog=None, *, include_public_overlays=False):
    audit = audit or json.loads(AUDIT.read_text())
    graph = graph or json.loads(OBSERVATIONS.read_text())
    catalog = catalog or load_catalog()
    overlay_graphs = list(overlays or [])
    if include_public_overlays:
        overlay_graphs.extend(json.loads(path.read_text()) for path in PUBLIC_OBSERVATION_OVERLAYS)
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
        'feasibility_order': ['readable-property', 'read-only-method', 'owned-write-method',
                'method-needs-scenario', 'needs-classification', 'receiver-unresolved', 'type-only',
                'editor-or-permission-gated'],
            'score_formula': 'feasibility tier + 10 * sum(clamped role-term matches) + min(receiver type count, 20)',
            'owned_write_method_map': {owner + '.' + name: purpose for (owner, name), purpose in OWNED_WRITE_METHODS.items()},
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
                ('readable-property', 'read-only-method', 'owned-write-method')]
    if receiver:
        receiver_key = receiver.casefold()
        rows = [row for row in rows if receiver_key in {item.casefold() for item in row['receiver_types']}]
    return rows if limit is None else rows[:limit]


def queue_graph(payload, rows):
    nodes = []
    edges = []
    node_ids = set()
    edge_ids = set()

    def add_node(node):
        if node['id'] not in node_ids:
            node_ids.add(node['id'])
            nodes.append(node)

    def add_edge(source, target, relation):
        key = (source, target, relation)
        if key not in edge_ids:
            edge_ids.add(key)
            edges.append({'from': source, 'to': target, 'type': relation})

    queue_id = 'api-priority-queue'
    add_node({'id': queue_id, 'type': 'requirement', 'title': 'Unobserved Plugin API priority queue',
        'status': 'planned', 'detail': json.dumps({'rows': len(rows),
            'audit_member_count': payload['source']['audit_member_count'],
            'base_observation_graph_id': payload['source']['base_observation_graph_id'],
            'overlay_graph_ids': payload['source']['overlay_graph_ids'],
            'ranking_rules': payload['ranking_rules']}, ensure_ascii=False, sort_keys=True)})
    role_titles = {'designer': 'Designer use case', 'developer': 'Developer use case', 'planner': 'Planner use case'}
    for role, title in role_titles.items():
        add_node({'id': 'use-case:' + role, 'type': 'requirement', 'title': title,
            'status': 'planned', 'detail': json.dumps({'priority_terms': ROLE_TERMS[role]}, ensure_ascii=False)})

    for row in rows:
        api_id = row['api_member_id']
        entry_id = 'priority:' + api_id
        member_id = 'api-member:' + api_id
        owner_id = 'api-owner:' + hashlib.sha256(str(row['owner']).encode()).hexdigest()[:16]
        observed = row['evidence_status'] in ('observed', 'observed-in-observation-graph')
        add_node({'id': entry_id, 'type': 'test', 'title': str(row['owner']) + '.' + str(row['name']) + ' priority',
            'status': 'observed' if observed else 'planned', 'detail': json.dumps({
                'api_member_id': api_id, 'priority_score': row['priority_score'],
                'feasibility': row['feasibility'], 'priority_reasons': row['priority_reasons'],
                'role_value': row['role_value'], 'role_matches': row['role_matches'],
                'receiver_types': row['receiver_types'], 'access': row['access'],
                'readonly': row['readonly'], 'write_capability': row['write_capability'],
                'method_requirement': row['method_requirement'], 'evidence_status': row['evidence_status'],
                'editor_requirement': row['editor_requirement'],
                'permission_requirement': row['permission_requirement']}, ensure_ascii=False, sort_keys=True)})
        add_node({'id': member_id, 'type': 'figma', 'title': str(row['owner']) + '.' + str(row['name']),
            'status': 'observed' if observed else row['release_status'], 'detail': json.dumps({
                'api_member_id': api_id, 'kind': row['kind'], 'signature': row['signature'],
                'release_status': row['release_status'], 'type_surface': row['type_surface'],
                'official_source': row['official_declaration']['source_url']}, ensure_ascii=False, sort_keys=True)})
        add_node({'id': owner_id, 'type': 'figma', 'title': str(row['owner']) + ' owner',
            'status': 'unverified', 'detail': 'Pinned Plugin API member owner.'})
        add_edge(queue_id, entry_id, 'queues')
        add_edge(entry_id, member_id, 'prioritizes')
        add_edge(member_id, owner_id, 'declared by')
        feasibility_id = 'feasibility:' + row['feasibility']
        add_node({'id': feasibility_id, 'type': 'requirement', 'title': row['feasibility'],
            'status': 'planned', 'detail': 'Execution class from the pinned audit and explicit probe/write policies.'})
        add_edge(entry_id, feasibility_id, 'classified as')
        status_id = 'evidence-status:' + str(row['evidence_status'])
        add_node({'id': status_id, 'type': 'evidence', 'title': 'Evidence ' + str(row['evidence_status']),
            'status': 'observed' if observed else 'unverified', 'detail': 'Status is copied from the audit or validated observation graph.'})
        add_edge(entry_id, status_id, 'has evidence status')
        for role, terms in row['role_matches'].items():
            if terms:
                add_edge(entry_id, 'use-case:' + role, 'serves')
        for receiver in row['receiver_types']:
            receiver_id = 'api-receiver:' + receiver
            add_node({'id': receiver_id, 'type': 'figma', 'title': receiver + ' receiver type',
                'status': 'unverified', 'detail': 'Receiver type from pinned node inheritance.'})
            add_edge(entry_id, receiver_id, 'receiver candidate')
        facts = {
            'write-capability': row['write_capability'],
            'editor-requirement': row['editor_requirement'],
            'permission-requirement': row['permission_requirement'],
        }
        for fact_name, fact_value in facts.items():
            fact_id = 'fact:' + api_id + ':' + fact_name
            add_node({'id': fact_id, 'type': 'evidence', 'title': fact_name.replace('-', ' ').title(),
                'status': 'unverified', 'detail': str(fact_value)})
            add_edge(entry_id, fact_id, 'has fact')
        for evidence in row['observation_evidence']:
            evidence_id = 'observation:' + hashlib.sha256(
                (evidence['graph_id'] + '\0' + evidence['evidence_id']).encode()).hexdigest()[:24]
            add_node({'id': evidence_id, 'type': 'evidence', 'title': 'Observed API receipt',
                'status': 'observed', 'detail': json.dumps(evidence, sort_keys=True)})
            add_edge(entry_id, evidence_id, 'supported by')
    return {'schema': 'figma-flow-api-priority-graph-v1', 'version': 1,
            'id': 'figma-flow-api-priority', 'title': 'Plugin API evidence priority graph',
            'nodes': nodes, 'edges': edges}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build_cmd = sub.add_parser('build', help='Build complete exact-key ranked inventory')
    build_cmd.add_argument('--audit', type=Path)
    build_cmd.add_argument('--observations', type=Path)
    build_cmd.add_argument('--overlay', type=Path, action='append', default=[],
                           help='Additional sanitized observation graph. May be repeated; overlays require fresh timestamped receipts.')
    build_cmd.add_argument('--baseline-only', action='store_true',
                           help='Reproduce the original 0.29 queue without the public editable-web observation overlay.')
    build_cmd.add_argument('--out', type=Path, required=True)
    queue_cmd = sub.add_parser('queue', help='Print the next unobserved exact-key rows')
    queue_cmd.add_argument('--inventory', type=Path, required=True)
    queue_cmd.add_argument('--limit', type=int, help='Maximum rows. Defaults to 50 for JSON and the whole queue for graph output.')
    queue_cmd.add_argument('--receiver', help='Filter by exact catalogued receiver node type, such as TEXT or PluginAPI')
    queue_cmd.add_argument('--format', choices=('json', 'graph'), default='json',
                           help='Write row JSON or a portable connected node/edge graph.')
    queue_cmd.add_argument('--feasible-only', action='store_true',
                           help='Keep readable properties and methods with explicit read or owned-write scenarios')
    args = parser.parse_args(argv)
    if args.command == 'build':
        if args.baseline_only and args.overlay:
            parser.error('--baseline-only cannot be combined with --overlay')
        audit = json.loads((args.audit or AUDIT).read_text())
        graph = json.loads((args.observations or OBSERVATIONS).read_text())
        overlays = [json.loads(path.read_text()) for path in args.overlay]
        result = build(audit, graph, overlays=overlays,
                       include_public_overlays=not args.baseline_only)
        args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        print(json.dumps({'path': str(args.out), 'rows': len(result['rows']),
                          'observed_graph_member_ids': result['source']['observed_graph_member_ids'],
                          'sha256': result['sha256']}))
    else:
        limit = args.limit if args.limit is not None else (None if args.format == 'graph' else 50)
        if limit is not None and (limit < 1 or limit > 10000):
            parser.error('--limit must be between 1 and 10000')
        payload = json.loads(args.inventory.read_text())
        if payload.get('schema') != OUTPUT_SCHEMA:
            parser.error('Unsupported API priority inventory schema')
        rows = queue(payload, limit=limit, receiver=args.receiver, feasible_only=args.feasible_only)
        if args.format == 'graph':
            print(json.dumps(queue_graph(payload, rows), ensure_ascii=False, indent=2))
        else:
            print(json.dumps({'schema': OUTPUT_SCHEMA, 'unobserved_members': payload['source']['unobserved_members'],
                'queue': rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
