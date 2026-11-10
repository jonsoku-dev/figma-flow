#!/usr/bin/env python3
"""Finite, scoped graph/native token exchange. Readbacks are evidence, not authority."""
import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
import sys
import tempfile

from graph_design_system import load_graph, resolve_design_system, emit_web_module, update_graph_values, _atomic_write, _encode, _validate_value, _validate_property, SUPPORTED_PROPERTY_TYPES

SCHEMA = 'figma-flow-graph-token-sync-v1'
RECEIPT = 'figma-flow-graph-pairing-v1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    _atomic_write(path, _encode(value))


def same_value(first, second):
    if isinstance(first, dict) and isinstance(second, dict) and set('rgb') <= set(first) and set('rgb') <= set(second):
        try:
            _validate_value('COLOR', first, 'comparison')
            _validate_value('COLOR', second, 'comparison')
        except ValueError:
            return False
        return all(math.isclose(first[channel], second[channel], rel_tol=0, abs_tol=1e-6) for channel in 'rgb')
    return first == second


def unique(items, key, label):
    matches = [item for item in items if item.get('id') == key or item.get('semanticKey') == key]
    if len(matches) != 1:
        raise ValueError(f'missing or ambiguous {label}: {key}')
    return matches[0]


def token_native_names(graph, require_namespace=False):
    design = graph['design_system']
    namespace = design.get('namespace')
    if namespace is None and design.get('id'):
        if not isinstance(design['id'], str):
            raise ValueError('invalid design system ID')
        namespace = 'ssot/' + design['id']
    if namespace is None:
        if require_namespace:
            raise ValueError('adoption requires design_system.id or namespace')
        return None, {key: key for key in design['tokens']}
    namespace = namespace.rstrip('/') if isinstance(namespace, str) else ''
    if not re.fullmatch(r'ssot/[A-Za-z0-9][A-Za-z0-9_-]*', namespace):
        raise ValueError('invalid design system native namespace')
    names = {key: key if key.startswith(namespace + '/') else namespace + '/' + key for key in design['tokens']}
    if any(not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or '..' in name.split('/') for name in names.values()) or len(set(names.values())) != len(names):
        raise ValueError('invalid or duplicate native token names')
    return namespace, names


def plan_scope(graph, baseline, plan):
    declared = graph['design_system'].get('native', {})
    pages = declared.get('allowed_page_ids', [plan['page_id']])
    if not isinstance(pages, list) or not pages or len(set(pages)) != len(pages) or not all(isinstance(page, str) and page for page in pages) or plan['page_id'] not in pages:
        raise ValueError('explicit allowed native page IDs required')
    if baseline.get('schema') == 'figma-flow-graph-native-discovery-v1' and set(baseline.get('allowed_page_ids', [])) != set(pages):
        raise ValueError('discovery allowed pages differ from graph native scope')
    plan['allowed_page_ids'] = pages
    plan['node_page_ids'] = {}
    nodes = {node['id']: node for node in baseline['nodes']}
    for component in plan['components']:
        for identity in component['main_keys'] + component['instance_keys']:
            cursor, seen = identity, set()
            while cursor in nodes and cursor not in pages:
                if cursor in seen:
                    raise ValueError('native node parent cycle')
                seen.add(cursor)
                cursor = nodes[cursor].get('parentId')
            if cursor not in pages:
                raise ValueError(f'component outside allowed native pages: {identity}')
            plan['node_page_ids'][identity] = cursor


def consumer_targets(node, descendants, field):
    if field not in SUPPORTED_PROPERTY_TYPES:
        raise ValueError(f'unsupported native component property: {field}')
    return [target for target in [node] + descendants if target['type'] == 'TEXT'] if field in {'fontFamily', 'fontSize', 'color'} else [node]


def native_property(node, field):
    """Read one supported canonical property, rejecting lossy native projections."""
    if field not in SUPPORTED_PROPERTY_TYPES:
        raise ValueError(f'unsupported native component property: {field}')
    bound = node.get('boundVariables', {})
    if field in {'backgroundColor', 'color', 'borderColor'}:
        paint_field = 'strokes' if field == 'borderColor' else 'fills'
        if node.get('strokeStyleId' if field == 'borderColor' else 'fillStyleId'):
            raise ValueError(f'style-backed native paint is unsupported: {node["id"]}.{field}')
        paints = node.get(paint_field)
        if not isinstance(paints, list) or len(paints) != 1 or paints[0].get('type') != 'SOLID' or paints[0].get('visible') is False or paints[0].get('opacity', 1) != 1:
            raise ValueError(f'unsupported or mixed native paint: {node["id"]}.{field}')
        paint = paints[0]
        value = {**paint['color'], 'a': 1}
        binding = paint.get('boundVariables', {}).get('color', bound.get(paint_field))
    elif field == 'borderRadius':
        corners = ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius']
        values = [node.get(corner, node.get('cornerRadius')) for corner in corners]
        if any(value != values[0] for value in values):
            raise ValueError(f'mixed native corner radii: {node["id"]}')
        value = values[0]
        bindings = [bound.get(corner, bound.get('cornerRadius')) for corner in corners]
        if any(binding != bindings[0] for binding in bindings):
            raise ValueError(f'mixed native corner bindings: {node["id"]}')
        binding = bindings[0]
    else:
        native_field = {'gap': 'itemSpacing', 'borderWidth': 'strokeWeight'}.get(field, field)
        if field in {'width', 'height'} and node.get('layoutSizingHorizontal' if field == 'width' else 'layoutSizingVertical') != 'FIXED':
            raise ValueError(f'native {field} requires fixed layout sizing')
        value = node.get('nativeFontFamily', node.get('fontName', {}).get('family')) if field == 'fontFamily' else node.get(native_field)
        binding = bound.get(native_field)
    if isinstance(binding, list):
        if not binding or any(item != binding[0] for item in binding):
            raise ValueError('mixed native bindings')
        binding = binding[0]
    if binding is not None and (not isinstance(binding, dict) or binding.get('type') != 'VARIABLE_ALIAS' or not isinstance(binding.get('id'), str) or not binding['id']):
        raise ValueError('unsupported native binding')
    _validate_value(SUPPORTED_PROPERTY_TYPES[field], value, field)
    _validate_property(field, SUPPORTED_PROPERTY_TYPES[field], value)
    return value, binding


def declared_binding_collection(graph, baseline):
    """Infer ownership solely from the exact fields admitted for migration."""
    variables = {variable['id']: variable for variable in baseline['variables']}
    collections = set()
    for declaration in graph['design_system']['components'].values():
        native = declaration['native']
        for key in native['mainKeys'] + native['instanceKeys']:
            node = unique(baseline['nodes'], key, 'component')
            descendants, frontier = [], [node['id']]
            while frontier:
                children = [child for child in baseline['nodes'] if child.get('parentId') in frontier]
                descendants.extend(children)
                frontier = [child['id'] for child in children]
            for field in declaration['properties']:
                targets = consumer_targets(node, descendants, field)
                if not targets:
                    raise ValueError('adoption requires actual consumers')
                for target in targets:
                    _, binding = native_property(target, field)
                    if binding is None:
                        continue
                    if binding['id'] not in variables:
                        raise ValueError('adoption requires actual existing binding variable')
                    collections.add(variables[binding['id']]['variableCollectionId'])
    if not collections and graph['design_system'].get('native', {}).get('collection_id'):
        return graph['design_system']['native']['collection_id']
    if len(collections) != 1:
        raise ValueError('declared migration fields must share one exact native collection')
    return next(iter(collections))


def build_adoption_plan(graph, baseline, previous=None):
    """Explicitly migrate declared consumers onto new, independently owned tokens."""
    resolved = resolve_design_system(graph)
    definitions = graph['design_system']['tokens']
    namespace, native_names = token_native_names(graph, require_namespace=True)
    existing_names = {variable['name'] for variable in baseline['variables']}
    existing_tokens = {}
    if previous is None:
        if existing_names.intersection(native_names.values()):
            raise ValueError('adoption tokens already exist; pair their actual identities instead')
    else:
        if previous.get('schema') != RECEIPT:
            raise ValueError('previous pairing receipt required for topology extension')
        existing_tokens = {token['key']: token for token in previous['plan']['tokens']}
        if not set(existing_tokens) <= set(definitions):
            raise ValueError('extension cannot remove owned tokens')
        if previous.get('native_scope', {}) != graph['design_system'].get('native', {}):
            raise ValueError('extension cannot change native page or collection scope')
        prior_components = previous['declarations']
        declarations = graph['design_system']['components']
        if not set(prior_components) <= set(declarations):
            raise ValueError('extension cannot remove existing components')
        for key, old in prior_components.items():
            current = declarations[key]
            if old.get('native') != current.get('native') or old.get('web') != current.get('web') or any(current['properties'].get(field) != token for field, token in old['properties'].items()):
                raise ValueError('extension cannot change existing component mappings')
        verify_readback(previous['plan'], normalize(baseline, previous['plan']), previous['tokens'], previous['consumer_ids'])
        previous_names = {token['variable_id']: token['variable_name'] for token in existing_tokens.values()}
        for key, old in existing_tokens.items():
            chain, cursor = [], key
            while True:
                chain.append(native_names[cursor])
                if 'alias' not in definitions[cursor]:
                    break
                cursor = definitions[cursor]['alias']
            if old['variable_name'] != native_names[key] or old['type'] != definitions[key]['type'] or chain != [previous_names.get(identity) for identity in old['alias_chain']] or not same_value(resolved['tokens'][key], previous['tokens'][key]):
                raise ValueError('extension cannot change existing owned token values or topology')
        for key in set(definitions) - set(existing_tokens):
            if native_names[key] in existing_names:
                raise ValueError('new extension token name already exists')
    scope = graph['design_system'].get('native', {})
    collections = baseline['collections']
    collection_id = declared_binding_collection(graph, baseline)
    if scope.get('collection_id', collection_id) != collection_id:
        raise ValueError('declared migration collection differs from graph scope')
    collection = unique(collections, collection_id, 'collection')
    if baseline.get('schema') == 'figma-flow-graph-native-discovery-v1':
        owner = collection.get('owner')
        if not isinstance(owner, dict) or owner.get('pageId') != baseline.get('pageId') or owner.get('collectionId') != collection_id:
            raise ValueError('native collection ownership mismatch')
    if len(collection['modes']) != 1:
        raise ValueError('single native mode required')
    mode = collection['defaultModeId']
    plan = {'schema': SCHEMA, 'graph_sha256': resolved['graphSha256'], 'pairing': True,
            'previous_graph_sha256': None, 'adopt': True,
            'file_key': baseline.get('fileKey'), 'page_id': baseline.get('pageId'),
            'collection_id': collection_id, 'tokens': [], 'components': [], 'migrations': [], 'namespace': namespace, 'system_id': namespace.split('/', 1)[1]}
    for field in ('file_key', 'page_id', 'collection_id'):
        if not plan[field] or field in scope and scope[field] != plan[field]:
            raise ValueError(f'wrong native {field}')
    # The old page marker is an explicit CAS pin when replacing an earlier pairing.
    marker = baseline.get('graphSSOT', baseline.get('baseline'))
    if isinstance(marker, dict):
        if marker.get('page_id') != plan['page_id'] or marker.get('collection_id') != collection_id:
            raise ValueError('adoption marker scope mismatch')
        plan['previous_graph_sha256'] = marker.get('graph_sha256')
    if previous is not None and plan['previous_graph_sha256'] != previous['graph_sha256']:
        raise ValueError('extension requires exact current pairing marker')
    for key, definition in definitions.items():
        if key in existing_tokens:
            plan['tokens'].append({**copy.deepcopy(existing_tokens[key]), 'value': resolved['tokens'][key], 'before': previous['tokens'][key]})
            continue
        chain, cursor = [], key
        while True:
            chain.append(cursor)
            if 'alias' not in definitions[cursor]:
                break
            cursor = definitions[cursor]['alias']
        plan['tokens'].append({'key': key, 'type': definition['type'], 'value': resolved['tokens'][key],
            'variable_name': native_names[key], 'create': True, 'root_variable_name': native_names[chain[-1]],
            'alias_chain_names': [native_names[name] for name in chain]})
    for key, declaration in graph['design_system']['components'].items():
        native = declaration['native']
        plan['components'].append({'id': key, 'properties': declaration['properties'],
            'main_keys': [unique(baseline['nodes'], k, 'main')['id'] for k in native['mainKeys']],
            'instance_keys': [unique(baseline['nodes'], k, 'instance')['id'] for k in native['instanceKeys']]})
    plan_scope(graph, baseline, plan)
    mains = {identity for component in plan['components'] for identity in component['main_keys']}
    admitted_instances = {identity for component in plan['components'] for identity in component['instance_keys']}
    for node in baseline['nodes']:
        if node.get('type') == 'INSTANCE' and node.get('mainComponentId') in mains and node['id'] not in admitted_instances:
            raise ValueError('adoption main has undeclared instance consumer')
    actual = normalize(baseline, {**plan, 'tokens': []})
    assigned = set()
    for group in actual['components']:
        for consumer in group['consumers']:
            identity = (consumer['node_id'], consumer['field'])
            if identity in assigned:
                raise ValueError('overlapping component field assignments are unsupported')
            assigned.add(identity)
    variables = {variable['id']: variable for variable in baseline['variables']}
    for component in plan['components']:
        for node_id in component['main_keys'] + component['instance_keys']:
            group = next(group for group in actual['components'] if group['id'] == component['id'] and group['node_id'] == node_id)
            main = node_id in component['main_keys']
            if group['type'] != ('COMPONENT' if main else 'INSTANCE') or group['main_component_id'] not in component['main_keys']:
                raise ValueError('adoption component source mismatch')
            for field, key in component['properties'].items():
                if previous is not None and field in previous['declarations'].get(component['id'], {}).get('properties', {}):
                    continue
                if key in existing_tokens:
                    raise ValueError('new migration properties require a new dedicated token')
                consumers = [consumer for consumer in group['consumers'] if consumer['field'] == field]
                if not consumers:
                    raise ValueError('adoption requires actual consumers')
                for consumer in consumers:
                    binding = consumer.get('binding')
                    if binding is None:
                        plan['migrations'].append({'node_id': consumer['node_id'], 'field': field,
                            'before_variable_id': None, 'before_value': consumer['value'], 'token': key})
                        continue
                    if not isinstance(binding, dict) or binding.get('type') != 'VARIABLE_ALIAS':
                        raise ValueError('adoption requires valid old binding')
                    variable_id, seen = binding['id'], set()
                    while True:
                        if variable_id in seen or variable_id not in variables:
                            raise ValueError('invalid old native alias chain')
                        seen.add(variable_id)
                        variable = variables[variable_id]
                        if variable['variableCollectionId'] != collection_id or variable['resolvedType'] != definitions[key]['type']:
                            raise ValueError('old binding scope/type mismatch')
                        value = variable['valuesByMode'][mode]
                        if not isinstance(value, dict) or value.get('type') != 'VARIABLE_ALIAS':
                            break
                        variable_id = value['id']
                    if not same_value(value, consumer['value']):
                        raise ValueError('old native binding/getter mismatch')
                    _validate_value(definitions[key]['type'], value, key)
                    plan['migrations'].append({'node_id': consumer['node_id'], 'field': field,
                        'before_variable_id': binding['id'], 'before_value': value, 'token': key})
    return plan


def bind_adopted_plan(plan, data):
    """Replace creation declarations with IDs observed after native migration."""
    if "status" in data or data.get("migration_pending"):
        raise ValueError("native readback reports failed or pending migration")
    if not any(token.get('create') for token in plan['tokens']):
        return plan
    bound = copy.deepcopy(plan)
    actual = {token['key']: token for token in data['tokens']}
    if len(actual) != len(plan['tokens']):
        raise ValueError('adopted token coverage mismatch')
    names = {token['variable_id']: token['variable_name'] for token in actual.values()}
    if len(names) != len(actual) or len(set(names.values())) != len(actual):
        raise ValueError('ambiguous adopted token identities')
    for token in bound['tokens']:
        if not token.get('create'):
            continue
        observed = actual.get(token['key'])
        if not observed or observed.get('variable_name') != token['variable_name'] or observed.get('type') != token['type']:
            raise ValueError('adopted token name/type mismatch')
        chain = observed.get('alias_chain', [])
        if [names.get(identity) for identity in chain] != token['alias_chain_names'] or names.get(observed.get('root_variable_id')) != token['root_variable_name']:
            raise ValueError('adopted alias topology mismatch')
        token.update({field: observed[field] for field in ('variable_id', 'root_variable_id', 'alias_chain')})
        token['before'] = observed['resolved']
        for field in ('create', 'root_variable_name', 'alias_chain_names'):
            token.pop(field, None)
    bound.pop('migrations', None)
    bound.pop('adopt', None)
    return bound


def build_plan(graph, baseline, adopt=False):
    """Pin actual identities and alias edges from the full native getter."""
    if adopt:
        return build_adoption_plan(graph, baseline)
    resolved = resolve_design_system(graph)
    definitions = graph['design_system']['tokens']
    variables = baseline['variables']
    namespace, native_names = token_native_names(graph)
    named = {}
    for key in definitions:
        found = [v for v in variables if v.get('name') == native_names[key]]
        if len(found) != 1:
            raise ValueError(f'missing or ambiguous native token: {key}')
        named[key] = found[0]
    collection_ids = {v['variableCollectionId'] for v in named.values()}
    if len(collection_ids) != 1:
        raise ValueError('canonical tokens must share one native collection')
    collection_id = next(iter(collection_ids))
    collection = unique(baseline['collections'], collection_id, 'collection')
    if len(collection['modes']) != 1:
        raise ValueError('single native mode required')
    mode = collection['defaultModeId']
    plan = {'schema': SCHEMA, 'graph_sha256': resolved['graphSha256'],
            'previous_graph_sha256': None, 'pairing': True,
            'file_key': baseline.get('fileKey'), 'page_id': baseline.get('pageId'),
            'collection_id': collection_id, 'tokens': [], 'components': []}
    if not plan['file_key'] or not plan['page_id']:
        raise ValueError('actual file/page identity required')
    declared_scope = graph['design_system'].get('native', {})
    for field in ('file_key', 'page_id', 'collection_id'):
        if field in declared_scope and declared_scope[field] != plan[field]:
            raise ValueError(f'wrong native {field}')
    for key, definition in definitions.items():
        item = named[key]
        chain, cursor = [], key
        while True:
            current = named[cursor]
            if current.get('resolvedType') != definitions[cursor]['type']:
                raise ValueError(f'native token type mismatch: {cursor}')
            chain.append(current['id'])
            value = current['valuesByMode'][mode]
            alias = definitions[cursor].get('alias')
            if alias is None:
                if not same_value(value, resolved['tokens'][cursor]):
                    raise ValueError(f'native token value mismatch: {cursor}')
                break
            if value != {'type': 'VARIABLE_ALIAS', 'id': named[alias]['id']}:
                raise ValueError(f'alias topology mismatch: {cursor}')
            cursor = alias
        plan['tokens'].append({'key': key, 'type': definition['type'], 'value': resolved['tokens'][key],
            'before': resolved['tokens'][key], 'variable_id': item['id'], 'variable_name': native_names[key],
            'root_variable_id': chain[-1], 'alias_chain': chain})
    for key, declaration in graph['design_system']['components'].items():
        native = declaration['native']
        plan['components'].append({'id': key, 'properties': declaration['properties'],
            'main_keys': [unique(baseline['nodes'], k, 'main')['id'] for k in native['mainKeys']],
            'instance_keys': [unique(baseline['nodes'], k, 'instance')['id'] for k in native['instanceKeys']]})
    plan_scope(graph, baseline, plan)
    actual = normalize(baseline, plan)
    verify_readback(plan, actual, resolved['tokens'])
    reject_shared_consumers(baseline, plan, actual)
    return plan


def reject_shared_consumers(baseline, plan, actual):
    allowed = {(consumer['node_id'], consumer['field']) for component in actual['components'] for consumer in component['consumers']}
    roots = {token['root_variable_id'] for token in plan['tokens']}
    variables = {variable['id']: variable for variable in baseline['variables']}
    collection = unique(baseline['collections'], plan['collection_id'], 'collection')
    mode = collection['defaultModeId']
    def root_of(identity):
        seen = set()
        while identity in variables:
            if identity in seen:
                raise ValueError('native alias cycle')
            seen.add(identity)
            variable = variables[identity]
            if variable['variableCollectionId'] != plan['collection_id']:
                return None
            value = variable['valuesByMode'][mode]
            if not isinstance(value, dict) or value.get('type') != 'VARIABLE_ALIAS':
                return identity
            identity = value['id']
        return None
    for node in baseline['nodes']:
        bindings_by_field = list(node.get('boundVariables', {}).items())
        for paint_field in ('fills', 'strokes'):
            for paint in node.get(paint_field, []):
                if paint.get('boundVariables', {}).get('color'):
                    bindings_by_field.append((paint_field, paint['boundVariables']['color']))
        for field, bindings in bindings_by_field:
            canonical = {'fills': 'color' if node['type'] == 'TEXT' else 'backgroundColor',
                         'strokes': 'borderColor', 'strokeWeight': 'borderWidth', 'itemSpacing': 'gap',
                         'cornerRadius': 'borderRadius', 'topLeftRadius': 'borderRadius', 'topRightRadius': 'borderRadius',
                         'bottomLeftRadius': 'borderRadius', 'bottomRightRadius': 'borderRadius'}.get(field, field)
            for binding in bindings if isinstance(bindings, list) else [bindings]:
                if isinstance(binding, dict) and binding.get('type') == 'VARIABLE_ALIAS' and root_of(binding['id']) in roots and (node['id'], canonical) not in allowed:
                    raise ValueError(f'shared native token has undeclared consumer: {node["id"]}.{field}; use explicit adoption')


def normalize(data, plan):
    if data.get('schema') == 'figma-flow-graph-token-readback-v1':
        return data
    nodes = data['nodes']
    variables = {v['id']: v for v in data['variables']}
    collection = unique(data['collections'], plan['collection_id'], 'collection')
    mode = collection['defaultModeId']
    result = {'file_key': data.get('fileKey'), 'page_id': data.get('pageId'),
              'collection_id': collection['id'], 'tokens': [], 'components': []}
    for token in plan['tokens']:
        variable = variables[token['variable_id']]
        chain, current = [], variable
        while True:
            if current['id'] in chain:
                raise ValueError('native alias cycle')
            chain.append(current['id'])
            value = current['valuesByMode'][mode]
            if not isinstance(value, dict) or value.get('type') != 'VARIABLE_ALIAS':
                break
            current = variables[value['id']]
        result['tokens'].append({'key': token['key'], 'variable_id': variable['id'],
            'variable_name': variable['name'], 'type': variable['resolvedType'],
            'root_variable_id': current['id'], 'alias_chain': chain, 'resolved': value})
    for component in plan['components']:
        for key in component['main_keys'] + component['instance_keys']:
            node = unique(nodes, key, 'component')
            descendants = []
            frontier = [node['id']]
            while frontier:
                children = [n for n in nodes if n.get('parentId') in frontier]
                descendants.extend(children)
                frontier = [n['id'] for n in children]
            consumers = []
            for field in component['properties']:
                targets = consumer_targets(node, descendants, field)
                for target in targets:
                    value, binding = native_property(target, field)
                    consumers.append({'node_id': target['id'], 'field': field, 'value': value, 'binding': binding})
            result['components'].append({'id': component['id'], 'node_id': node['id'], 'type': node['type'],
                'main_component_id': node.get('mainComponentId', node['id']),
                'page_id': plan.get('node_page_ids', {}).get(node['id']), 'consumers': consumers})
    return result


def verify_readback(plan, data, expected=None, identities=None, allow_node_edits=False):
    if 'status' in data or data.get('migration_pending'):
        raise ValueError('native readback reports failed or pending migration')
    for field in ('file_key', 'page_id', 'collection_id'):
        if data.get(field) != plan[field]:
            raise ValueError(f'wrong native {field}')
    if len(data.get('tokens', [])) != len(plan['tokens']):
        raise ValueError('native token coverage mismatch')
    observed, root_values = {}, {}
    for token in plan['tokens']:
        matches = [t for t in data['tokens'] if t.get('key') == token['key']]
        if len(matches) != 1:
            raise ValueError('native token coverage mismatch')
        actual = matches[0]
        for field in ('variable_id', 'variable_name', 'type', 'root_variable_id', 'alias_chain'):
            if actual.get(field) != token[field]:
                raise ValueError(f'native alias/identity mismatch: {token["key"]}.{field}')
        _validate_value(token['type'], actual['resolved'], token['key'])
        root = token['root_variable_id']
        if root in root_values and not same_value(root_values[root], actual['resolved']):
            raise ValueError('inconsistent native alias root values')
        root_values[root] = actual['resolved']
        observed[token['key']] = actual['resolved']
        if expected is not None and not same_value(actual['resolved'], expected[token['key']]):
            raise ValueError(f'native value mismatch: {token["key"]}')
    expected_nodes = set()
    consumer_ids = {}
    for component in plan['components']:
        if not component['main_keys'] or not component['instance_keys']:
            raise ValueError('main and instance scope required')
        for key in component['main_keys'] + component['instance_keys']:
            expected_nodes.add((component['id'], key))
            matches = [c for c in data.get('components', []) if c.get('id') == component['id'] and c.get('node_id') == key]
            if len(matches) != 1:
                raise ValueError('native component coverage mismatch')
            actual = matches[0]
            if plan.get('node_page_ids') and actual.get('page_id') != plan['node_page_ids'][key]:
                raise ValueError('native component page mismatch')
            is_main = key in component['main_keys']
            if actual.get('type') != ('COMPONENT' if is_main else 'INSTANCE') or actual.get('main_component_id') not in component['main_keys']:
                raise ValueError('native main/instance identity mismatch')
            for field, token_key in component['properties'].items():
                consumers = [c for c in actual.get('consumers', []) if c.get('field') == field]
                if not consumers:
                    raise ValueError(f'missing native consumer: {key}.{field}')
                ids = sorted(c['node_id'] for c in consumers)
                identity_key = f'{component["id"]}:{key}:{field}'
                if identities is not None and identities.get(identity_key) != ids:
                    raise ValueError('native consumer identity changed')
                consumer_ids[identity_key] = ids
                token = next(t for t in plan['tokens'] if t['key'] == token_key)
                for consumer in consumers:
                    binding = consumer.get('binding')
                    if binding is not None and (not isinstance(binding, dict) or binding.get('type') != 'VARIABLE_ALIAS' or not isinstance(binding.get('id'), str) or not binding['id']):
                        raise ValueError('invalid native consumer binding')
                    _validate_value(token['type'], consumer.get('value'), token_key)
                    _validate_property(field, token['type'], consumer.get('value'))
                    if consumer.get('token', token_key) != token_key or not same_value(consumer.get('root_value', observed[token_key]), observed[token_key]):
                        raise ValueError('native consumer token/root observation mismatch')
                    if not allow_node_edits and (binding != {'type': 'VARIABLE_ALIAS', 'id': token['variable_id']} or not same_value(consumer.get('value'), observed[token_key])):
                        raise ValueError(f'native binding/getter mismatch: {key}.{field}')
    if len(data.get('components', [])) != len(expected_nodes):
        raise ValueError('unexpected native component scope')
    return observed, consumer_ids


def receipt(graph, plan, data):
    plan = copy.deepcopy(bind_adopted_plan(plan, data))
    plan.pop('repair_bindings', None)
    resolved = resolve_design_system(graph)
    definitions = graph['design_system']['tokens']
    for field, value in graph['design_system'].get('native', {}).items():
        if field in ('file_key', 'page_id', 'collection_id') and plan.get(field) != value:
            raise ValueError('plan native scope differs from graph')
    _, native_names = token_native_names(graph)
    token_map = {token['key']: token for token in plan['tokens']}
    if set(token_map) != set(definitions):
        raise ValueError('plan token topology differs from graph')
    for key, token in token_map.items():
        if token['variable_name'] != native_names[key]:
            raise ValueError('plan native token namespace differs from graph')
        chain, cursor = [], key
        while True:
            chain.append(token_map[cursor]['variable_id'])
            if 'alias' not in definitions[cursor]:
                break
            cursor = definitions[cursor]['alias']
        if token['type'] != definitions[key]['type'] or token['alias_chain'] != chain or token['root_variable_id'] != chain[-1]:
            raise ValueError('plan alias topology differs from graph')
    components = graph['design_system']['components']
    if len(plan['components']) != len(components) or any(c['id'] not in components or c['properties'] != components[c['id']]['properties'] for c in plan['components']):
        raise ValueError('plan component properties differ from graph')
    tokens, identities = verify_readback(plan, data, resolved['tokens'])
    return {'schema': RECEIPT, 'graph_sha256': resolved['graphSha256'], 'tokens': tokens,
            'primitive_roots': resolved['primitiveRoots'], 'plan': plan, 'consumer_ids': identities,
            'declarations': copy.deepcopy(graph['design_system']['components']),
            'native_scope': copy.deepcopy(graph['design_system'].get('native', {}))}


def check_pairing(graph, pairing):
    resolved = resolve_design_system(graph)
    if pairing.get('schema') != RECEIPT or pairing['primitive_roots'] != resolved['primitiveRoots']:
        raise ValueError('pairing token topology changed')
    declarations = graph['design_system']['components']
    _, native_names = token_native_names(graph)
    if any(token['variable_name'] != native_names.get(token['key']) for token in pairing['plan']['tokens']):
        raise ValueError('pairing native namespace changed')
    if pairing.get('native_scope', {}) != graph['design_system'].get('native', {}):
        raise ValueError('pairing native scope changed')
    if set(declarations) != {c['id'] for c in pairing['plan']['components']}:
        raise ValueError('pairing component topology changed')
    if pairing.get('declarations') != declarations:
        raise ValueError('pairing native/web declarations changed')
    for component in pairing['plan']['components']:
        if declarations[component['id']]['properties'] != component['properties']:
            raise ValueError('pairing component properties changed')
    return resolved


def merge_roots(graph, pairing, observed):
    current = check_pairing(graph, pairing)
    updates = {}
    for key, root in current['primitiveRoots'].items():
        base, local, remote = pairing['tokens'][key], current['tokens'][key], observed[key]
        if not same_value(remote, base) and not same_value(local, base) and not same_value(local, remote):
            raise ValueError(f'divergent same-token edit: {root}')
        if not same_value(remote, base):
            if root in updates and not same_value(updates[root], remote):
                raise ValueError(f'conflicting native aliases: {root}')
            updates[root] = remote
    return {k: v for k, v in updates.items() if not same_value(current['tokens'][k], v)}


def component_node_edits(graph, pairing, data, observed):
    """Promote explicit, unambiguous direct edits to the shared component roots."""
    resolved = check_pairing(graph, pairing)
    plan = pairing['plan']
    token_map = {token['key']: token for token in plan['tokens']}
    direct, repairs = {}, {}
    unsupported = copy.deepcopy(data.get('unsupported_changes', []))
    for group in data['components']:
        declaration = next(component for component in plan['components'] if component['id'] == group['id'])
        unsupported.extend(copy.deepcopy(group.get('unsupported_changes', [])))
        for consumer in group['consumers']:
            field = consumer['field']
            if field not in declaration['properties']:
                unsupported.append({'node_id': consumer['node_id'], 'field': field, 'reason': 'unmapped component property; no graph promotion'})
                continue
            key = declaration['properties'][field]
            token = token_map[key]
            binding = consumer.get('binding')
            if binding == {'type': 'VARIABLE_ALIAS', 'id': token['variable_id']} and same_value(consumer['value'], observed[key]):
                continue
            root = resolved['primitiveRoots'][key]
            value = consumer['value']
            if root in direct and not same_value(direct[root], value):
                raise ValueError(f'conflicting direct node edits for token: {root}')
            direct[root] = value
            identity = (consumer['node_id'], field)
            repair = {'node_id': consumer['node_id'], 'field': field, 'token': key,
                      'before_variable_id': binding['id'] if binding else None, 'before_value': value}
            if identity in repairs and repairs[identity] != repair:
                raise ValueError('conflicting direct node repair scope')
            repairs[identity] = repair
    effective = copy.deepcopy(observed)
    for root, value in direct.items():
        base, variable = pairing['tokens'][root], observed[root]
        if not same_value(variable, base) and not same_value(variable, value):
            raise ValueError(f'divergent variable and direct node edits: {root}')
        for key, primitive in resolved['primitiveRoots'].items():
            if primitive == root:
                effective[key] = value
    return effective, list(repairs.values()), unsupported


def affected_component_scope(graph, pairing, updates, repairs):
    resolved = resolve_design_system(graph)
    roots = set(updates) | {resolved['primitiveRoots'][repair['token']] for repair in repairs}
    affected = []
    for component in pairing['plan']['components']:
        fields = [field for field, key in component['properties'].items() if resolved['primitiveRoots'][key] in roots]
        if fields:
            declaration = graph['design_system']['components'][component['id']]
            affected.append({'component': component['id'], 'fields': fields,
                'main_ids': component['main_keys'], 'instance_ids': component['instance_keys'],
                'page_ids': {identity: pairing['plan'].get('node_page_ids', {}).get(identity) for identity in component['main_keys'] + component['instance_keys']},
                'web_selector': declaration.get('web', {}).get('selector')})
    return affected


def verify_web_proof(graph, proof):
    resolved = resolve_design_system(graph)
    declarations = {key: value for key, value in graph['design_system']['components'].items() if value.get('web', {}).get('selector')}
    if proof.get('schema') != 'figma-flow-graph-web-readback-v1' or proof.get('graph_sha256') != resolved['graphSha256']:
        raise ValueError('missing or stale actual web proof')
    if not isinstance(proof.get('url'), str) or not proof['url'] or not isinstance(proof.get('observed_at'), str) or not proof['observed_at']:
        raise ValueError('web proof URL and observation time required')
    components = proof.get('components', [])
    if len(components) != len(declarations):
        raise ValueError('web proof component coverage mismatch')
    for key, declaration in declarations.items():
        matches = [component for component in components if component.get('id') == key]
        if len(matches) != 1:
            raise ValueError('web proof component coverage mismatch')
        actual = matches[0]
        if actual.get('selector') != declaration['web']['selector'] or actual.get('graph_sha256') != resolved['graphSha256']:
            raise ValueError('web proof selector or graph identity mismatch')
        for field, value in resolved['components'][key].items():
            observed = actual.get('properties', {}).get(field)
            if isinstance(value, (int, float)) and (isinstance(observed, bool) or not isinstance(observed, (int, float))):
                raise ValueError(f'web proof requires measured numeric pixels: {key}.{field}')
            if SUPPORTED_PROPERTY_TYPES[field] == 'COLOR':
                _validate_value('COLOR', observed, field)
                # Browser computed RGB serializes channels at 8-bit precision.
                same = all(math.isclose(observed[channel], value[channel], rel_tol=0, abs_tol=0.5 / 255 + 1e-6) for channel in 'rgb')
            else:
                same = observed == value
            if not same:
                raise ValueError(f'web measured property mismatch: {key}.{field}')
    return True


def web_probe(graph):
    declarations = {key: {'selector': value['web']['selector'], 'properties': list(value['properties'])}
                    for key, value in graph['design_system']['components'].items() if value.get('web', {}).get('selector')}
    return r"""(() => {
  const declarations = %s;
  const components = Object.entries(declarations).map(([id, declaration]) => {
    const elements = document.querySelectorAll(declaration.selector);
    if (elements.length !== 1) throw Error('Missing or ambiguous web selector: ' + declaration.selector);
    const element = elements[0], style = getComputedStyle(element), properties = {};
    for (const field of declaration.properties) {
      const value = style[field];
      if (['backgroundColor', 'color', 'borderColor'].includes(field)) {
        const channels = value.match(/^rgba?\(([^)]+)\)$/)?.[1].split(',').map(part => Number(part.trim()));
        if (!channels || ![3, 4].includes(channels.length) || channels.some(channel => !Number.isFinite(channel))) throw Error('Unsupported computed color: ' + value);
        properties[field] = {r: channels[0] / 255, g: channels[1] / 255, b: channels[2] / 255, a: channels[3] ?? 1};
      }
      else if (field === 'fontFamily') properties[field] = value.split(',')[0].trim().replace(/^['"]|['"]$/g, '');
      else if (/^-?(?:\d+\.?\d*|\.\d+)px$/.test(value)) properties[field] = Number(value.slice(0, -2));
      else properties[field] = value;
    }
    return {id, selector: declaration.selector, graph_sha256: element.getAttribute('data-graph-sha'), properties};
  });
  const hashes = [...new Set(components.map(component => component.graph_sha256))];
  return {schema: 'figma-flow-graph-web-readback-v1', graph_sha256: hashes.length === 1 ? hashes[0] : null,
    components, observed_at: new Date().toISOString(), url: location.href};
})()
""" % json.dumps(declarations)


def export_bundle(graph_path, out, web_module, baseline=None, pairing=None, plugin_id=None, adopt=False, import_report=None):
    graph = load_graph(graph_path)
    resolved = resolve_design_system(graph)
    if adopt:
        if baseline is None or import_report is not None:
            raise ValueError('adoption requires full native baseline without node import repair')
        plan = build_adoption_plan(graph, baseline, previous=pairing)
    elif pairing is None:
        if import_report is not None:
            raise ValueError('accepted node import requires pairing')
        plan = build_plan(graph, baseline)
    else:
        check_pairing(graph, pairing)
        plan = copy.deepcopy(pairing['plan'])
        plan.update(graph_sha256=resolved['graphSha256'], previous_graph_sha256=pairing['graph_sha256'], pairing=False)
        before = pairing['tokens']
        if import_report is not None and baseline is None:
            raise ValueError('accepted node import requires actual --native-readback')
        if baseline is not None:
            normalized = normalize(baseline, plan)
            before, _ = verify_readback(plan, normalized, identities=pairing['consumer_ids'], allow_node_edits=import_report is not None)
            if import_report is not None:
                if import_report.get('schema') != 'figma-flow-graph-import-report-v1' or import_report.get('applied') is not True or import_report.get('node_edit_scope') != 'component' or import_report.get('graph_sha256_after') != resolved['graphSha256'] or import_report.get('pairing_graph_sha256') != pairing['graph_sha256'] or import_report.get('readback_sha256') != hashlib.sha256(_encode(baseline)).hexdigest():
                    raise ValueError('stale or unaccepted direct-node import report')
                effective, repairs, _ = component_node_edits(graph, pairing, normalized, before)
                if repairs != import_report.get('repair_bindings') or merge_roots(graph, pairing, effective):
                    raise ValueError('accepted direct-node repair differs from current graph')
                plan['repair_bindings'] = repairs
            marker = baseline.get('baseline')
            if not isinstance(marker, dict) or marker.get('graph_sha256') != pairing['graph_sha256']:
                raise ValueError('native graph marker differs from pairing')
        for token in plan['tokens']:
            token.update(value=resolved['tokens'][token['key']], before=before[token['key']])
    output = Path(out)
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'native-plan.json', plan)
    (output / 'web-probe.js').write_text(web_probe(graph), encoding='utf-8')
    bridge = Path(__file__).resolve().parents[1] / 'figma-bridge' / 'graph_token_sync.js'
    (output / 'code.js').write_text('const GRAPH_SYNC_PLAN = ' + json.dumps(plan) + ';\n' + bridge.read_text(), encoding='utf-8')
    manifest = {'name': 'Graph canonical token sync', 'api': '1.0.0', 'main': 'code.js', 'editorType': ['figma'], 'documentAccess': 'dynamic-page', 'networkAccess': {'allowedDomains': ['none']}}
    if plugin_id:
        manifest['id'] = plugin_id
    save(output / 'manifest.json', manifest)
    emit_web_module(graph_path, web_module, expected_sha256=resolved['graphSha256'])
    return {'graph_sha256': resolved['graphSha256'], 'native_plan': str(output / 'native-plan.json')}


def import_values(graph_path, pairing, readback, web_module, out, apply=False, node_edit_scope=None):
    if Path(graph_path).resolve() == Path(web_module).resolve():
        raise ValueError('web module must not overwrite graph')
    graph = load_graph(graph_path)
    check_pairing(graph, pairing)
    if node_edit_scope not in (None, 'component'):
        raise ValueError('only explicit component scope is supported for direct node edits')
    normalized = normalize(readback, pairing['plan'])
    observed, _ = verify_readback(pairing['plan'], normalized, identities=pairing['consumer_ids'], allow_node_edits=node_edit_scope == 'component')
    if readback.get('schema') == 'figma-flow-graph-token-readback-v1':
        marker = readback.get('baseline')
        if not isinstance(marker, dict) or marker.get('graph_sha256') != pairing['graph_sha256']:
            raise ValueError('native graph marker differs from pairing')
    repairs, unsupported = [], copy.deepcopy(normalized.get('unsupported_changes', []))
    if node_edit_scope == 'component':
        observed, repairs, unsupported = component_node_edits(graph, pairing, normalized, observed)
    updates = merge_roots(graph, pairing, observed)
    output = Path(out)
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'figma-flow-graph-import-report-v1',
              'graph_sha256_before': graph.source_sha256, 'updates': updates, 'applied': False,
              'pairing_advanced': False, 'pairing_graph_sha256': pairing['graph_sha256'],
              'readback_sha256': hashlib.sha256(_encode(readback)).hexdigest(),
              'node_edit_scope': node_edit_scope, 'repair_bindings': repairs,
              'unsupported_changes': unsupported,
              'affected_components': affected_component_scope(graph, pairing, updates, repairs)}
    # Validate and generate everything before changing canonical files.
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        staged_graph = Path(temporary) / 'graph.json'
        staged_web = Path(temporary) / 'tokens.mjs'
        staged_graph.write_bytes(Path(graph_path).read_bytes())
        if updates:
            update_graph_values(staged_graph, updates, graph.source_sha256)
        emit_web_module(staged_graph, staged_web)
        report['graph_sha256_after'] = load_graph(staged_graph).source_sha256
        save(output / 'import-report.json', report)
        if apply:
            print(json.dumps({'applying_component_scope': report['affected_components'], 'unsupported_changes': unsupported}, ensure_ascii=False), file=sys.stderr)
            projection = output / 'web.after.mjs'
            projection.write_bytes(staged_web.read_bytes())
            recovery = {'graph_path': str(Path(graph_path).resolve()),
                'web_module': str(Path(web_module).resolve()), 'before_sha256': graph.source_sha256,
                'after_sha256': report['graph_sha256_after'], 'projection_path': str(projection.resolve()),
                'projection_sha256': hashlib.sha256(projection.read_bytes()).hexdigest(), 'state': 'prepared'}
            save(output / 'recovery.json', recovery)
            (output / 'graph.before.json').write_bytes(Path(graph_path).read_bytes())
            if Path(web_module).exists():
                (output / 'web.before.mjs').write_bytes(Path(web_module).read_bytes())
            try:
                update_graph_values(graph_path, updates, graph.source_sha256, web_module=web_module)
            except ValueError:
                raise
            except Exception as error:
                # The graph remains canonical; recover its projection without rolling back another writer.
                raise RuntimeError(f'publication failed; recover canonical files using {output / "recovery.json"}') from error
            report['applied'] = True
            save(output / 'recovery.json', {**recovery, 'state': 'complete'})
    save(output / 'import-report.json', report)
    return report


def discovery_bundle(file_key, page_id, include_page_ids, out, plugin_id=None):
    pages = list(dict.fromkeys([page_id] + include_page_ids))
    if not file_key or not page_id or not all(pages):
        raise ValueError('explicit native file and page IDs required')
    output = Path(out)
    output.mkdir(parents=True, exist_ok=False)
    source = (Path(__file__).resolve().parents[1] / 'figma-bridge' / 'native_semantic_read.js').read_text()
    source += '\nconst DISCOVERY_SCOPE = ' + json.dumps({'file_key': file_key, 'page_id': page_id, 'allowed_page_ids': pages}) + ';\n'
    source += r"""
async function discoverGraphNative(figma, scope) {
  if (figma.fileKey !== scope.file_key || figma.currentPage.id !== scope.page_id) throw Error('Wrong native discovery file or main page');
  const result = {schema: 'figma-flow-graph-native-discovery-v1', fileKey: figma.fileKey,
    pageId: scope.page_id, allowed_page_ids: scope.allowed_page_ids, collections: [], variables: [], nodes: [], observed_at: new Date().toISOString()};
  const collections = new Map(), variables = new Map();
  for (const pageId of scope.allowed_page_ids) {
    const page = await figma.getNodeByIdAsync(pageId);
    if (!page || page.type !== 'PAGE') throw Error('Missing admitted discovery page: ' + pageId);
    const actual = await readNativeSemantics(figma, page);
    const nativeNodes = new Map([page, ...page.findAll(() => true)].map(node => [node.id, node]));
    for (const row of actual.nodes) {
      const node = nativeNodes.get(row.id);
      if (typeof node.strokeWeight === 'number') row.strokeWeight = node.strokeWeight;
      if (node.type === 'TEXT' && node.characters.length) {
        const families = [...new Set(node.getRangeAllFontNames(0, node.characters.length).map(font => font.family))];
        if (families.length === 1) row.nativeFontFamily = families[0];
        const familyBinding = node.getRangeBoundVariable(0, node.characters.length, 'fontFamily');
        if (typeof familyBinding === 'symbol') throw Error('Mixed native font-family binding: ' + node.id);
        row.boundVariables = {...row.boundVariables, fontFamily: familyBinding || undefined};
      }
    }
    result.nodes.push(...actual.nodes);
    for (const variable of actual.variables) variables.set(variable.id, variable);
    for (const collection of actual.collections) {
      const native = await figma.variables.getVariableCollectionByIdAsync(collection.id);
      collections.set(collection.id, {...collection, owner: JSON.parse(native.getPluginData('bloomSemanticTokens') || 'null')});
    }
    if (pageId === scope.page_id) result.graphSSOT = JSON.parse(page.getPluginData('graphSSOT') || 'null');
  }
  result.collections = [...collections.values()]; result.variables = [...variables.values()];
  if (figma.fileKey !== scope.file_key || figma.currentPage.id !== scope.page_id) throw Error('Discovery scope changed during read');
  return result;
}
figma.showUI('<button id="read">Read scoped native graph baseline</button><pre id="status"></pre><script>document.getElementById("read").onclick=()=>parent.postMessage({pluginMessage:{type:"read"}},"*");onmessage=e=>{const msg=e.data.pluginMessage;document.getElementById("status").textContent=msg.error||"Actual native baseline saved";if(msg.readback){const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(msg.readback,null,2)],{type:"application/json"}));a.download="graph-native-discovery.json";a.click();URL.revokeObjectURL(a.href);}};</script>', {width: 440, height: 160});
let discoveryBusy = false;
figma.ui.onmessage = async message => {
  if (message?.type !== 'read' || discoveryBusy) return;
  discoveryBusy = true;
  try { figma.ui.postMessage({readback: await discoverGraphNative(figma, DISCOVERY_SCOPE)}); }
  catch (error) { figma.ui.postMessage({error: error.message || String(error)}); }
  finally { discoveryBusy = false; }
};
"""
    (output / 'code.js').write_text(source, encoding='utf-8')
    manifest = {'name': 'Graph scoped native discovery', 'api': '1.0.0', 'main': 'code.js',
                'editorType': ['figma'], 'documentAccess': 'dynamic-page', 'networkAccess': {'allowedDomains': ['none']}}
    if plugin_id:
        manifest['id'] = plugin_id
    save(output / 'manifest.json', manifest)
    return {'discovery_plugin': str(output / 'manifest.json'), 'allowed_page_ids': pages}


def recover_projection(journal_path):
    recovery = read(journal_path)
    graph_path, web_module = Path(recovery['graph_path']), Path(recovery['web_module'])
    if graph_path.resolve() == web_module.resolve():
        raise ValueError('web module must not overwrite graph')
    graph = load_graph(graph_path)
    if graph.source_sha256 != recovery['after_sha256']:
        raise ValueError('stale recovery: graph drifted; export again')
    projection = Path(recovery['projection_path']).read_bytes()
    if hashlib.sha256(projection).hexdigest() != recovery['projection_sha256']:
        raise ValueError('staged web projection hash mismatch')
    with tempfile.TemporaryDirectory() as temporary:
        snapshot, expected = Path(temporary) / 'graph.json', Path(temporary) / 'tokens.mjs'
        snapshot.write_bytes(graph_path.read_bytes())
        if load_graph(snapshot).source_sha256 != recovery['after_sha256']:
            raise ValueError('stale recovery: graph changed')
        emit_web_module(snapshot, expected)
        if expected.read_bytes() != projection:
            raise ValueError('staged projection differs from canonical graph')
        emit_web_module(graph_path, web_module, expected_sha256=recovery['after_sha256'])
    recovery['state'] = 'complete'
    save(journal_path, recovery)
    return {'recovered': True, 'graph_sha256': graph.source_sha256, 'pairing_advanced': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('export', 'pair', 'import', 'status'):
        p = sub.add_parser(command)
        p.add_argument('--graph', required=True)
        if command in ('export', 'import', 'status'):
            p.add_argument('--pairing')
        if command in ('pair', 'import', 'status'):
            p.add_argument('--readback', required=command != 'status')
        if command != 'status':
            p.add_argument('--out', required=True)
        if command in ('export', 'import', 'pair'):
            p.add_argument('--web-module', required=command != 'pair')
        if command == 'pair':
            p.add_argument('--plan')
            p.add_argument('--web-proof')
        if command == 'export':
            p.add_argument('--native-readback')
            p.add_argument('--plugin-id')
            p.add_argument('--adopt', action='store_true', help='Explicitly create or extend scoped graph tokens; existing systems require their previous pairing')
            p.add_argument('--import-report', help='Applied component node-edit report authorizing repairs for this exact native readback')
        if command == 'import':
            p.add_argument('--apply', action='store_true')
            p.add_argument('--node-edit-scope', choices=['component'], help='Promote consistent mapped main/instance edits to shared component tokens; unmapped fields are reported, per-instance variants are unsupported')
    discovery_parser = sub.add_parser('discover')
    discovery_parser.add_argument('--file-key', required=True)
    discovery_parser.add_argument('--page-id', required=True)
    discovery_parser.add_argument('--include-page-id', action='append', default=[])
    discovery_parser.add_argument('--plugin-id')
    discovery_parser.add_argument('--out', required=True)
    recovery_parser = sub.add_parser('recover')
    recovery_parser.add_argument('--recovery', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'discover':
            print(json.dumps(discovery_bundle(args.file_key, args.page_id, args.include_page_id, args.out, args.plugin_id)))
            return 0
        if args.command == 'recover':
            print(json.dumps(recover_projection(args.recovery)))
            return 0
        graph = load_graph(args.graph)
        pairing = read(args.pairing) if getattr(args, 'pairing', None) else None
        if args.command == 'export':
            if not args.native_readback and not pairing:
                raise ValueError('provide --native-readback or --pairing')
            result = export_bundle(args.graph, args.out, args.web_module,
                read(args.native_readback) if args.native_readback else None, pairing, args.plugin_id, args.adopt, read(args.import_report) if args.import_report else None)
        elif args.command == 'pair':
            data = read(args.readback)
            if data.get('schema') != 'figma-flow-graph-token-readback-v1':
                raise ValueError('pair requires actual focused native getter readback')
            # Recover exact plan topology from full native baseline or prior export alongside readback.
            plan_path = Path(args.plan) if args.plan else Path(args.readback).parent / 'native-plan.json'
            if not plan_path.exists():
                raise ValueError('pair requires native-plan.json beside readback')
            plan = read(plan_path)
            if plan['graph_sha256'] != graph.source_sha256:
                raise ValueError('stale graph: export again before pairing')
            marker = data.get('baseline')
            if not isinstance(marker, dict) or marker.get('graph_sha256') != graph.source_sha256 or marker.get('page_id') != plan['page_id'] or marker.get('collection_id') != plan['collection_id']:
                raise ValueError('pair requires actual applied native graph marker')
            result = receipt(graph, plan, data)
            has_web = any(component.get('web', {}).get('selector') for component in graph['design_system']['components'].values())
            if has_web and (not args.web_module or not args.web_proof):
                raise ValueError('web components require --web-module and actual --web-proof')
            if args.web_proof:
                proof = read(args.web_proof)
                verify_web_proof(graph, proof)
                result['web_proof'] = proof
            if args.web_module:
                with tempfile.TemporaryDirectory() as temporary:
                    expected = Path(temporary) / 'tokens.mjs'
                    emit_web_module(args.graph, expected)
                    if expected.read_bytes() != Path(args.web_module).read_bytes():
                        raise ValueError('generated web module differs from graph')
                result['web_module_sha256'] = hashlib.sha256(Path(args.web_module).read_bytes()).hexdigest()
            protected = {Path(args.graph).resolve(), Path(args.readback).resolve(), plan_path.resolve()}
            protected.update(Path(path).resolve() for path in (args.web_module, args.web_proof) if path)
            if Path(args.out).resolve() in protected:
                raise ValueError('pairing receipt must not overwrite graph or evidence')
            save(args.out, result)
            result = {'graph_sha256': result['graph_sha256'], 'pairing': args.out, 'web_artifact_verified': bool(args.web_module)}
        elif args.command == 'import':
            if pairing is None:
                raise ValueError('--pairing required')
            result = import_values(args.graph, pairing, read(args.readback), args.web_module, args.out, args.apply, args.node_edit_scope)
        else:
            result = {'graph_sha256': graph.source_sha256, 'paired': pairing is not None}
            if pairing:
                resolved = check_pairing(graph, pairing)
                result['graph_matches_pairing'] = graph.source_sha256 == pairing['graph_sha256']
                if args.readback:
                    observed, _ = verify_readback(pairing['plan'], normalize(read(args.readback), pairing['plan']), identities=pairing['consumer_ids'])
                    result['native_matches_graph'] = observed == resolved['tokens']
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print(f'graph_sync: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
