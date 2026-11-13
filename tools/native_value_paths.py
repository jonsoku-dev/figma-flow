#!/usr/bin/env python3
"""Build a pinned, fixed allowlist for native data-object value paths."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'library/figma-recipes/inspection'
POLICY = RECIPE / 'values.json'
API_AUDIT = ROOT / 'library/figma-api/audit/members.json'
ALLOWED_RECEIPTS = {
    'figma-flow-service-inspection-receipt-v1',
    'figma-flow-graph-native-discovery-v1',
}
MAX_RECEIPT_BYTES = 1_000_000
MAX_GRAPH_NODES = 500
MAX_COLLECTION_ITEMS = 8
FILE_KEY = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
PAGE_ID = re.compile(r'\d+:\d+\Z')
PLUGIN_ID = re.compile(r'\d+\Z')
SHA256 = re.compile(r'[a-f0-9]{64}\Z')

sys.path.insert(0, str(ROOT / 'tools'))
from figma_api_inventory import inherited_members, load as load_api_catalog
from review_api_coverage import observed_member_evidence
import api_priority


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _member(catalog, owner, name, kind='PropertySignature'):
    rows = [row for row in inherited_members(catalog, owner)
            if row['owner'] == owner and row['name'] == name and row['kind'] == kind]
    if len(rows) != 1:
        raise ValueError(f'Expected one pinned {kind} for {owner}.{name}, found {len(rows)}.')
    return rows[0]


def _references(member):
    return set(member.get('references') or ())


def _decl(catalog, owner):
    rows = [row for row in catalog['declarations'] if row['name'] == owner]
    if len(rows) != 1:
        raise ValueError(f'Expected one pinned declaration for {owner}, found {len(rows)}.')
    return rows[0]


def _member_signature_has_literal(catalog, owner, name, literal):
    member = _member(catalog, owner, name)
    return re.search(r"(?<![A-Za-z0-9_])['\"]" + re.escape(literal) + r"['\"](?![A-Za-z0-9_])",
                     member['signature']) is not None


def _validate_catalog(catalog, policy):
    if policy.get('schema') != 'figma-flow-native-value-path-catalog-v1':
        raise ValueError('Unsupported native value path catalog schema.')
    if set(policy) != {'schema', 'limits', 'routes', 'projection'}:
        raise ValueError('Unexpected native value path catalog fields.')
    if not isinstance(policy['routes'], list) or not 1 <= len(policy['routes']) <= 16:
        raise ValueError('The value path catalog must contain one to sixteen fixed routes.')
    seen_routes = set()
    for route in policy['routes']:
        if (not isinstance(route, dict) or set(route) != {'id', 'source', 'fixture', 'owners', 'unions'}
                or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', str(route.get('id', '')))
                or route['id'] in seen_routes):
            raise ValueError('Invalid or duplicate fixed value path route.')
        seen_routes.add(route['id'])
        source = route['source']
        if (not isinstance(source, dict) or set(source) != {'owner', 'member', 'target', 'many'}
                or type(source['many']) is not bool):
            raise ValueError('Each fixed route needs one exact typed getter source.')
        source_member = _member(catalog, source['owner'], source['member'])
        source_refs = _references(source_member)
        if source['target'] not in source_refs:
            # Some aliases, such as VectorPaths, wrap their item type in one more declaration.
            target_decl = _decl(catalog, source['target'])
            if source['target'] not in _references(target_decl):
                raise ValueError(f'{source["owner"]}.{source["member"]} does not return {source["target"]}.')
        if source['many'] and 'ReadonlyArray' not in source_refs:
            target_decl = _decl(catalog, source['target'])
            if 'ReadonlyArray' not in _references(target_decl):
                raise ValueError(f'{source["owner"]}.{source["member"]} is not a pinned array getter.')
        if not isinstance(route['fixture'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', route['fixture']):
            raise ValueError(f'Invalid owned fixture label for {route["id"]}.')
        if not isinstance(route['owners'], dict):
            raise ValueError(f'Expected typed owner fields in {route["id"]}.')
        for owner, fields in route['owners'].items():
            _decl(catalog, owner)
            if not isinstance(fields, list) or not fields or len(fields) != len(set(fields)):
                raise ValueError(f'Expected a unique fixed field list for {owner}.')
            for name in fields:
                _member(catalog, owner, name)
        if not isinstance(route['unions'], dict):
            raise ValueError(f'Expected explicit discriminated unions in {route["id"]}.')
        for union_name, union in route['unions'].items():
            declaration = _decl(catalog, union_name)
            if not isinstance(union, dict) or set(union) != {'discriminator', 'branches'}:
                raise ValueError(f'Expected a discriminator and fixed branches for {union_name}.')
            if declaration['kind'] != 'TypeAliasDeclaration' and union_name not in route['owners']:
                raise ValueError(f'{union_name} must be a pinned type alias or listed data owner.')
            branches = union['branches']
            branch_signature = declaration.get('signature') or ''
            if not branch_signature and union_name in route['owners']:
                branch_signature = '\n'.join(_member(catalog, union_name, field)['signature']
                                              for field in route['owners'][union_name])
            if not isinstance(branches, list) or not branches or len(branches) > 32:
                raise ValueError(f'Expected one to 32 fixed branches for {union_name}.')
            tags = set()
            signature = declaration.get('signature') or ''
            for branch in branches:
                if (not isinstance(branch, dict) or not set(branch) <= {
                        'tag', 'owner', 'fields', 'previouslyObserved', 'evidenceMember'}
                        or not isinstance(branch.get('tag'), str) or not branch['tag']
                        or branch['tag'] in tags):
                    raise ValueError(f'Invalid or duplicate branch in {union_name}.')
                if ('previouslyObserved' in branch and type(branch['previouslyObserved']) is not bool
                        or branch.get('previouslyObserved') is True and not isinstance(branch.get('evidenceMember'), str)):
                    raise ValueError(f'Previously observed branches need one exact audit member in {union_name}.')
                tags.add(branch['tag'])
                owner = branch.get('owner')
                if owner:
                    _decl(catalog, owner)
                if branch.get('fields'):
                    fields = branch['fields']
                    if not isinstance(fields, list) or len(fields) != len(set(fields)):
                        raise ValueError(f'Invalid fixed fields for {union_name}.{branch["tag"]}.')
                    for field in fields:
                        if not isinstance(field, str) or not re.search(r'\b' + re.escape(field) + r'\??\s*:', branch_signature):
                            raise ValueError(f'{union_name}.{branch["tag"]} field is absent from the pinned declaration.')
                # The checker-produced declaration index preserves exact TypeScript literals.
                if not _union_tag_present(catalog, union_name, union, branch['tag'], signature):
                    raise ValueError(f'{union_name} does not declare discriminant {branch["tag"]!r}.')


def _union_tag_present(catalog, union_name, union, tag, signature):
    discriminator = union['discriminator']
    if re.search(r'\b' + re.escape(discriminator) + r'\s*:\s*[^;\n]*[\'"]'
                 + re.escape(tag) + r'[\'"]', signature):
        return True
    try:
        discriminant_member = _member(catalog, union_name, discriminator)
    except ValueError:
        discriminant_member = None
    if discriminant_member:
        if re.search(r"['\"]" + re.escape(tag) + r"['\"]", discriminant_member['signature']):
            return True
        for reference in _references(discriminant_member):
            declaration = next((row for row in catalog['declarations'] if row['name'] == reference), None)
            if declaration and re.search(r"['\"]" + re.escape(tag) + r"['\"]", declaration.get('signature') or ''):
                return True
    # Union aliases such as Effect refer to variants that inherit their
    # discriminant from a shared base interface. Follow only pinned references.
    def discriminant_signatures(owner, visited):
        if owner in visited:
            return []
        visited.add(owner)
        declaration = next((row for row in catalog['declarations'] if row['name'] == owner), None)
        if not declaration:
            return []
        if declaration['kind'] == 'TypeAliasDeclaration':
            return [signature for ref in _references(declaration)
                    for signature in discriminant_signatures(ref, visited)]
        return [member['signature'] for member in inherited_members(catalog, owner)
                if member['name'] == discriminator]

    for signature in discriminant_signatures(union_name, set()):
        if re.search(r"['\"]" + re.escape(tag) + r"['\"]", signature):
            return True
    # Some alias branches name a base interface in the separate owner field.
    for branch in union['branches']:
        if branch['tag'] != tag or not branch.get('owner'):
            continue
        try:
            member = _member(catalog, branch['owner'], discriminator)
        except ValueError:
            return False
        return re.search(r"['\"]" + re.escape(tag) + r"['\"]", member['signature']) is not None
    return False


def _receipt_member_ids(path, audit):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError('Observation receipt exceeds the one MB bound.')
    value = json.loads(raw)
    schema = value.get('schema')
    by_key = {row['key']: row for row in audit['members']}
    ids = set()
    if schema == 'figma-flow-service-inspection-receipt-v1':
        observations = value.get('observations')
        if not isinstance(observations, list):
            raise ValueError('Service receipt has no bounded observations list.')
        for row in observations:
            if row.get('status') == 'success' and row.get('id') in by_key:
                ids.add(row['id'])
    elif schema == 'figma-flow-graph-native-discovery-v1':
        probe = value.get('api_probe')
        observations = probe.get('observations') if isinstance(probe, dict) else None
        if not isinstance(observations, list):
            raise ValueError('Native API receipt has no bounded property observations.')
        for row in observations:
            if row.get('status') == 'success' and row.get('api_member_id') in by_key:
                ids.add(row['api_member_id'])
    elif isinstance(value.get('version'), int) and isinstance(value.get('nodes'), list):
        ids.update(observed_member_evidence(audit, value))
    else:
        raise ValueError('Use a validated API observation graph or known native getter receipt.')
    return ids


def _observed_ids(audit, *, exclusions=()):
    baseline = api_priority.build(include_public_overlays=True)
    ids = {row['api_member_id'] for row in baseline['rows']
           if row['evidence_status'] in ('observed', 'observed-in-observation-graph')}
    for receipt in exclusions:
        ids.update(_receipt_member_ids(receipt, audit))
    return ids


def _api_member_index(inventory):
    return {(row['owner'], row['name'], row['kind']): row for row in inventory['rows']}


def _candidate_fields(inventory, policy, observed):
    api = _api_member_index(inventory)
    fields = []
    skipped_observed = []
    for route in policy['routes']:
        for owner, names in route['owners'].items():
            for name in names:
                item = api.get((owner, name, 'PropertySignature'))
                if not item:
                    raise ValueError(f'No exact audited member for {owner}.{name}.')
                record = {'route': route['id'], 'owner': owner, 'name': name,
                          'member_id': item['api_member_id'], 'signature': item['signature'],
                          'source_url': item['official_declaration']['source_url']}
                (skipped_observed if item['api_member_id'] in observed else fields).append(record)
    if len({row['member_id'] for row in fields}) != len(fields):
        raise ValueError('Value path candidate fields must be unique across routes.')
    return fields, skipped_observed


def _stable_key(prefix, value):
    return prefix + hashlib.sha256(str(value).encode()).hexdigest()[:16]


def build_graph(*, receipts=(), catalog=None, policy=None, audit=None):
    policy_bytes = POLICY.read_bytes() if policy is None else canonical(policy).encode()
    catalog = catalog or load_api_catalog()
    policy = policy or json.loads(POLICY.read_bytes())
    audit = audit or json.loads(API_AUDIT.read_bytes())
    _validate_catalog(catalog, policy)
    priority = api_priority.build(include_public_overlays=True)
    observed = _observed_ids(audit, exclusions=receipts)
    fields, skipped = _candidate_fields(priority, policy, observed)
    api = _api_member_index(priority)

    nodes = [{'id': 'REQ-native-value-paths', 'type': 'requirement', 'status': 'planned',
              'title': 'Measure safe native data-object value paths',
              'detail': json.dumps({'getter_policy': 'fixed reviewed routes',
                                    'discriminated_unions': True,
                                    'projection': 'bounded and redacted',
                                    'api_source_ref': catalog['source']['ref'],
                                    'api_source_version': catalog['source']['version'],
                                    'api_declaration_sha256': catalog['source']['files']['plugin-api.d.ts']},
                                   sort_keys=True)}]
    edges = []
    field_ids = {field['member_id'] for field in fields}
    for route in policy['routes']:
        route_id = 'PATH-' + route['id']
        source = route['source']
        source_item = api.get((source['owner'], source['member'], 'PropertySignature'))
        if source_item and source_item['api_member_id'] not in observed:
            raise ValueError(f'Getter root has no successful prior evidence: {source["owner"]}.{source["member"]}.')
        nodes.append({'id': route_id, 'type': 'test', 'status': 'planned', 'title': route['id'],
                      'detail': json.dumps({'source_owner': source['owner'], 'source_member': source['member'],
                                            'target_type': source['target'], 'fixture': route['fixture']},
                                           sort_keys=True)})
        edges.append({'from': 'REQ-native-value-paths', 'to': route_id, 'type': 'measures'})
        owner_node = 'TYPE-' + route['id']
        nodes.append({'id': owner_node, 'type': 'figma', 'status': 'planned',
                      'title': source['target'],
                      'detail': f'{source["owner"]}.{source["member"]} returns this pinned value type.'})
        edges.append({'from': route_id, 'to': owner_node, 'type': 'returns'})
        for owner in route['owners']:
            typed_id = _stable_key('TYPE-', owner)
            if not any(node['id'] == typed_id for node in nodes):
                declaration = _decl(catalog, owner)
                nodes.append({'id': typed_id, 'type': 'figma', 'status': 'planned', 'title': owner,
                              'source': f'https://developers.figma.com/docs/plugins/api/',
                              'detail': f'Pinned {declaration["kind"]} from API source {catalog["source"]["ref"]}.'})
            edges.append({'from': owner_node, 'to': typed_id, 'type': 'reaches'})
        for union_name, union in route['unions'].items():
            union_id = _stable_key('UNION-', union_name)
            if not any(node['id'] == union_id for node in nodes):
                nodes.append({'id': union_id, 'type': 'figma', 'status': 'planned', 'title': union_name,
                              'detail': f'Discriminated by {union["discriminator"]}; only listed branches are inspected.'})
            edges.append({'from': route_id, 'to': union_id, 'type': 'discriminates'})
            for branch in union['branches']:
                branch_status = 'planned'
                branch_detail = f'Pinned {union_name} branch discriminant.'
                if branch.get('previouslyObserved'):
                    observed_owner, observed_name = branch['evidenceMember'].split('.', 1)
                    prior = api.get((observed_owner, observed_name, 'PropertySignature'))
                    if not prior or prior['api_member_id'] not in observed:
                        raise ValueError(f'Branch {union_name}.{branch["tag"]} is marked previously observed without evidence.')
                    branch_status = 'observed'
                    branch_detail = f'Previously observed through {branch["evidenceMember"]}.'
                branch_owner = branch.get('owner')
                if branch_owner:
                    branch_id = _stable_key('TYPE-', branch_owner)
                    if not any(node['id'] == branch_id for node in nodes):
                        declaration = _decl(catalog, branch_owner)
                        nodes.append({'id': branch_id, 'type': 'figma', 'status': branch_status, 'title': branch_owner,
                                      'detail': branch_detail if branch.get('previouslyObserved') else f'Pinned {declaration["kind"]} branch.'})
                    elif branch.get('previouslyObserved'):
                        next(node for node in nodes if node['id'] == branch_id)['status'] = 'observed'
                        next(node for node in nodes if node['id'] == branch_id)['detail'] = branch_detail
                else:
                    branch_id = _stable_key('BRANCH-', union_name + '.' + branch['tag'])
                    nodes.append({'id': branch_id, 'type': 'figma', 'status': branch_status,
                                  'title': union_name + '.' + branch['tag'],
                                  'detail': branch_detail if branch.get('previouslyObserved')
                                  else json.dumps({'union_fields': branch.get('fields', [])}, sort_keys=True)})
                edges.append({'from': union_id, 'to': branch_id, 'type': 'has branch'})
    for field in fields:
        item = api[(field['owner'], field['name'], 'PropertySignature')]
        nodes.append({'id': field['member_id'], 'type': 'figma', 'status': 'planned',
                      'title': f'{field["owner"]}.{field["name"]}', 'source': field['source_url'],
                      'detail': json.dumps({'signature': field['signature'], 'route': field['route'],
                                            'projection': 'bounded and redacted'}, sort_keys=True)})
        edges.append({'from': 'PATH-' + field['route'], 'to': field['member_id'], 'type': 'reads member'})
    if len(nodes) > MAX_GRAPH_NODES:
        raise ValueError('Typed value path graph exceeds the 500-node bound.')
    graph = {'version': 1, 'id': 'native-value-paths-' + hashlib.sha256(
        json.dumps([policy, catalog['source']], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12],
        'title': 'Native Design value paths', 'nodes': nodes, 'edges': edges}
    report = {'schema': 'figma-flow-native-value-path-summary-v1',
              'declaration_ref': catalog['source']['ref'],
              'declaration_version': catalog['source']['version'],
              'declaration_sha256': catalog['source']['files']['plugin-api.d.ts'],
              'policy_sha256': digest(policy_bytes),
              'routes': len(policy['routes']), 'candidate_members': len(fields),
              'already_observed_members': len(skipped),
              'union_branches': sum(len(route['unions'][name]['branches'])
                                    for route in policy['routes'] for name in route['unions']),
              'graph_sha256': digest(canonical(graph).encode()),
              'candidates': fields,
              'already_observed': [{'member_id': row['member_id'], 'owner': row['owner'], 'name': row['name']}
                                   for row in skipped]}
    return graph, report


def _safe_receipt(value, plan, policy):
    allowed = {'schema', 'graph_sha256', 'policy_sha256', 'api_source_ref', 'observed_at',
               'getter_counts', 'scenarios', 'observations', 'union_coverage'}
    if not isinstance(value, dict) or set(value) != allowed:
        raise ValueError('Receipt contains missing or unapproved fields.')
    if value.get('schema') not in {'figma-flow-native-value-observation-v1', 'figma-flow-native-value-observation-v2'} or value.get('graph_sha256') != plan['graph_sha256']:
        raise ValueError('Receipt schema or graph hash does not match the pinned plan.')
    if value.get('policy_sha256') != plan['policy_sha256'] or value.get('api_source_ref') != plan['api_source_ref']:
        raise ValueError('Receipt policy or API declaration source does not match the pinned plan.')
    from review_api_coverage import _valid_observation_time
    if not _valid_observation_time(value.get('observed_at')):
        raise ValueError('Receipt timestamp must be timezone-aware and not in the future.')
    candidates = {row['member_id']: row for row in plan['candidate_members']}
    observations = value.get('observations')
    if not isinstance(observations, list) or len(observations) > 300:
        raise ValueError('Receipt observations exceed the 300-field bound.')
    seen = set()
    for row in observations:
        allowed_row = {'member_id', 'owner', 'name', 'route', 'status', 'value'}
        if not isinstance(row, dict) or set(row) != allowed_row or row.get('status') not in {
                'success', 'unavailable', 'runtime-error', 'unsupported'}:
            raise ValueError('Receipt contains an unapproved member observation.')
        member = row['member_id']
        if member not in candidates or member in seen:
            raise ValueError('Receipt member is not a unique pinned candidate.')
        expected = candidates[member]
        if (row['owner'], row['name'], row['route']) != (expected['owner'], expected['name'], expected['route']):
            raise ValueError('Receipt member owner, name, or getter route drifted from the plan.')
        _validate_projected_value(row.get('value'))
        seen.add(member)
    scenarios = value.get('scenarios')
    route_ids = {route['id'] for route in policy['routes']}
    scenario_fields = {'route', 'status'} if value['schema'].endswith('v1') else {
        'route', 'status', 'assignments_attempted', 'assignments_succeeded', 'assignments_failed', 'readback_objects'}
    if (not isinstance(scenarios, list) or len(scenarios) > len(route_ids)
            or any(not isinstance(row, dict) or set(row) != scenario_fields
                   or row.get('route') not in route_ids
                   or row.get('status') not in {'created', 'reused', 'unavailable', 'seed-error', 'partial'}
                   for row in scenarios)
            or len({row['route'] for row in scenarios}) != len(scenarios)):
        raise ValueError('Receipt scenario states must use fixed route labels and states.')
    if value['schema'].endswith('v2') and any(
        any(type(row[field]) is not int or not 0 <= row[field] <= 100 for field in (
            'assignments_attempted', 'assignments_succeeded', 'assignments_failed', 'readback_objects'))
        or row['assignments_succeeded'] + row['assignments_failed'] != row['assignments_attempted']
        for row in scenarios
    ):
        raise ValueError('Scenario assignment/readback counts do not reconcile.')
    expected_unions = {name: {branch['tag'] for branch in spec['branches']}
                       - {branch['tag'] for branch in spec['branches'] if branch.get('previouslyObserved')}
                       for route in policy['routes'] for name, spec in route['unions'].items()}
    coverage = value.get('union_coverage')
    if not isinstance(coverage, dict) or set(coverage) != set(expected_unions):
        raise ValueError('Receipt union coverage must match the fixed discriminant catalog.')
    for name, entry in coverage.items():
        if (not isinstance(entry, dict) or set(entry) != {'observed'}
                or not isinstance(entry['observed'], list) or len(entry['observed']) > len(expected_unions[name])
                or len(entry['observed']) != len(set(entry['observed']))
                or not set(entry['observed']) <= expected_unions[name]):
            raise ValueError(f'Invalid observed branches for {name}.')
    counts = value.get('getter_counts')
    if (not isinstance(counts, dict) or set(counts) != {'success', 'unavailable', 'runtime_error', 'unsupported'}
            or any(type(number) is not int or not 0 <= number <= 300 for number in counts.values())
            or sum(counts.values()) != len(observations)
            or counts['success'] != sum(row['status'] == 'success' for row in observations)):
        raise ValueError('Receipt getter counts do not match its member rows.')
    return value


def _validate_projected_value(value, depth=0):
    if depth > 8:
        raise ValueError('Projected value exceeds the nesting bound.')
    if value is None or type(value) in (bool, int, float):
        if isinstance(value, float) and not (value == value and abs(value) < 1e12):
            raise ValueError('Projected numbers must be finite and bounded.')
        return
    if isinstance(value, str):
        if len(value) > 80 or not re.fullmatch(r'[A-Z0-9_.:-]*', value):
            raise ValueError('Receipt strings must be fixed enums, never text or identifiers.')
        return
    if isinstance(value, list):
        if len(value) > 16:
            raise ValueError('Projected lists exceed the item bound.')
        for item in value:
            _validate_projected_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 32 or any(not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z][A-Za-z0-9_]{0,63}', key) for key in value):
            raise ValueError('Projected objects exceed the shape bound.')
        for item in value.values():
            _validate_projected_value(item, depth + 1)
        return
    raise ValueError('Receipt contains an unsupported projected value.')


def build_observation_graph(receipt_path, plan_path):
    raw = Path(receipt_path).read_bytes()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError('Value receipt exceeds the one MB bound.')
    value = json.loads(raw)
    plan = json.loads(Path(plan_path).read_bytes())
    policy = json.loads(POLICY.read_bytes())
    receipt = _safe_receipt(value, plan, policy)
    successful = [row for row in receipt['observations'] if row['status'] == 'success']
    if not successful:
        raise ValueError('At least one audited native getter must succeed before graphing evidence.')
    audit = json.loads(API_AUDIT.read_bytes())
    priority = api_priority.build(include_public_overlays=True)
    by_id = {row['api_member_id']: row for row in priority['rows']}
    # Preserve a historical receipt's edges even after its graph enters the default union.
    baseline = {row['api_member_id'] for row in priority['rows']
                if row['evidence_status'] in ('observed', 'observed-in-observation-graph')}
    new = [row for row in successful if row['member_id'] not in baseline]
    receipt_sha = digest(raw)
    evidence_id = 'OBS-native-value-' + receipt_sha[:16]
    nodes = [{'id': evidence_id, 'type': 'test', 'status': 'observed',
              'title': 'Native Design data-object getter readback',
              'source': '../../docs/design-runtime-verification.md',
              'observed_at': receipt['observed_at'], 'receipt_sha256': receipt_sha,
              'getter_counts': receipt['getter_counts'],
              'detail': json.dumps({'graph_sha256': receipt['graph_sha256'],
                                    'policy_sha256': receipt['policy_sha256'],
                                    'union_coverage': receipt['union_coverage']}, sort_keys=True)}]
    edges = []
    for observation in successful:
        row = by_id[observation['member_id']]
        nodes.append({'id': row['api_member_id'], 'type': 'figma', 'status': 'observed',
                      'title': row['owner'] + '.' + row['name'],
                      'source': row['official_declaration']['source_url'],
                      'detail': json.dumps({'signature': row['signature'], 'safe_projection': observation['value']},
                                           sort_keys=True)})
        edges.append({'from': evidence_id, 'to': row['api_member_id'], 'type': 'observed member'})
    union_leftovers = {name: sorted({branch['tag'] for branch in spec['branches']
                                     if not branch.get('previouslyObserved')}
                                    - set(receipt['union_coverage'][name]['observed']))
                       for route in policy['routes'] for name, spec in route['unions'].items()}
    graph = {'version': 1, 'id': 'native-value-observations-' + receipt_sha[:16],
             'title': 'Native data-object value observations', 'nodes': nodes, 'edges': edges}
    return graph, {'receipt_sha256': receipt_sha, 'successful_fields': len(successful),
                   'new_audited_members': len(new), 'skipped_baseline_members': len(successful) - len(new),
                   'union_coverage': receipt['union_coverage'], 'union_leftovers': union_leftovers}


def _write_private_bundle(destination, files):
    private_root = (ROOT / '.figma-flow').resolve()
    requested = Path(destination).absolute()
    if (not requested.resolve().is_relative_to(private_root) or requested.exists()
            or any(part.is_symlink() for part in (requested, *requested.parents))):
        raise ValueError('Choose a new, non-symlink output directory under .figma-flow/.')
    destination = requested.resolve()
    destination.mkdir(parents=True, mode=0o700)
    for name, value in files.items():
        path = destination / name
        with path.open('xb') as output:
            output.write(value)
        path.chmod(0o600)
    return destination


def prepare(destination, *, file_key=None, page_id=None, plugin_id=None, service_receipt, exclusions=(), scope_plan=None):
    if scope_plan:
        raw_scope = Path(scope_plan).read_bytes()
        if len(raw_scope) > MAX_RECEIPT_BYTES:
            raise ValueError('Scope plan exceeds the one MB bound.')
        scope = json.loads(raw_scope)
        if scope.get('schema') != 'figma-flow-native-value-path-plan-v1':
            raise ValueError('Scope plan must be a previously generated private value-path plan.')
        if any(value is not None for value in (file_key, page_id, plugin_id)):
            raise ValueError('Use either --scope-plan or explicit file/page/plugin values.')
        file_key, page_id, plugin_id = scope.get('file'), scope.get('page'), scope.get('plugin_id')
    if (not isinstance(file_key, str) or not FILE_KEY.fullmatch(file_key)
            or not isinstance(page_id, str) or not PAGE_ID.fullmatch(page_id)
            or not isinstance(plugin_id, str) or not PLUGIN_ID.fullmatch(plugin_id)):
        raise ValueError('Provide a valid Design file key, page ID, and assigned numeric development plugin ID.')
    service_raw = Path(service_receipt).read_bytes()
    if len(service_raw) > MAX_RECEIPT_BYTES:
        raise ValueError('Service receipt exceeds the one MB bound.')
    service = json.loads(service_raw)
    if service.get('schema') != 'figma-flow-service-inspection-receipt-v1' or not SHA256.fullmatch(str(service.get('graph_sha256', ''))):
        raise ValueError('The service specimen must come from a validated service inspection receipt.')
    graph, report = build_graph(receipts=[service_receipt, *exclusions])
    graph_raw = canonical(graph).encode()
    graph_sha = digest(graph_raw)
    policy_raw = POLICY.read_bytes()
    policy = json.loads(policy_raw)
    api_catalog = load_api_catalog()
    candidate_members = report.pop('candidates')
    audit = json.loads(API_AUDIT.read_bytes())
    audit_keys = {(row['owner'], row['name']): row['key'] for row in audit['members']}
    service_successes = {row['id'] for row in service.get('observations', []) if row.get('status') == 'success'}
    capability_members = {
        'getLocalVariableCollectionsAsync': ('VariablesAPI', 'getLocalVariableCollectionsAsync'),
        'getVariableByIdAsync': ('VariablesAPI', 'getVariableByIdAsync'),
        'setBoundVariableForEffect': ('VariablesAPI', 'setBoundVariableForEffect'),
        'setBoundVariableForLayoutGrid': ('VariablesAPI', 'setBoundVariableForLayoutGrid'),
    }
    capabilities = {name: bool(audit_keys.get(key) in service_successes)
                    for name, key in capability_members.items()}
    plan = {'schema': 'figma-flow-native-value-path-plan-v1', 'file': file_key, 'page': page_id,
            'plugin_id': plugin_id, 'graph_sha256': graph_sha, 'policy_sha256': digest(policy_raw),
            'receipt_schema': 'figma-flow-native-value-observation-v2',
            'api_source_ref': api_catalog['source']['ref'],
            'api_declaration_sha256': api_catalog['source']['files']['plugin-api.d.ts'],
            'service_graph_sha256': service['graph_sha256'],
            'capabilities': capabilities,
            'candidate_members': candidate_members,
            'routes': policy['routes'], 'limits': policy['limits']}
    code = ('const VALUE_PLAN = ' + json.dumps(plan, ensure_ascii=False, separators=(',', ':')) + ';\n'
            + (RECIPE / 'values.js').read_text())
    manifest = {'id': plugin_id, 'name': 'Figma Flow · Native value paths', 'api': '1.0.0',
                'main': 'code.js', 'editorType': ['figma'], 'documentAccess': 'dynamic-page',
                'networkAccess': {'allowedDomains': ['none']}}
    files = {'graph.json': graph_raw,
             'summary.json': canonical({k: v for k, v in report.items() if k != 'already_observed'}).encode(),
             'plan.json': canonical(plan).encode(),
             'code.js': code.encode(),
             'manifest.json': canonical(manifest).encode()}
    out = _write_private_bundle(destination, files)
    return {'graph_sha256': graph_sha, 'candidate_members': len(candidate_members),
            'already_observed_members': report['already_observed_members'], 'output': str(out)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build', help='Build the offline typed value-path graph.')
    build.add_argument('--exclude-receipt', action='append', type=Path, default=[])
    build.add_argument('--out', type=Path, required=True)
    prep = commands.add_parser('prepare', help='Create a private, file/page-scoped Developer Plugin bundle.')
    prep.add_argument('--file-key')
    prep.add_argument('--page-id')
    prep.add_argument('--plugin-id')
    prep.add_argument('--scope-plan', type=Path, help='Reuse exact private file/page/plugin values from a saved plan.')
    prep.add_argument('--service-receipt', required=True, type=Path)
    prep.add_argument('--exclude-receipt', action='append', type=Path, default=[])
    prep.add_argument('--out', type=Path, required=True)
    normalize = commands.add_parser('normalize', help='Produce an exact-key API observation graph from a sanitized receipt.')
    normalize.add_argument('--receipt', required=True, type=Path)
    normalize.add_argument('--plan', required=True, type=Path)
    normalize.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            graph, report = build_graph(receipts=args.exclude_receipt)
            target = _private_output_file(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(canonical(graph).encode())
            print(json.dumps({k: v for k, v in report.items() if k not in ('candidates', 'already_observed')}))
        elif args.command == 'prepare':
            print(json.dumps(prepare(args.out, file_key=args.file_key, page_id=args.page_id,
                                     plugin_id=args.plugin_id, service_receipt=args.service_receipt,
                                     exclusions=args.exclude_receipt, scope_plan=args.scope_plan)))
        else:
            graph, summary = build_observation_graph(args.receipt, args.plan)
            target = _private_output_file(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(canonical(graph).encode())
            print(json.dumps(summary, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(2, f'native-value-paths: {error}\n')


def _private_output_file(path):
    private_root = (ROOT / '.figma-flow').resolve()
    requested = Path(path).absolute()
    if (not requested.resolve().is_relative_to(private_root) or requested.exists()
            or any(part.is_symlink() for part in (requested, *requested.parents))):
        raise ValueError('Choose a new, non-symlink file under .figma-flow/.')
    return requested.resolve()


if __name__ == '__main__':
    main()
