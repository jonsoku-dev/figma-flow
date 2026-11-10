#!/usr/bin/env python3
"""Validate proposed foundations separately from native Plugin API readback.

Contract v1: roles [{name, kind, token, value, alias?, collection?, bindings:
[{nodeId, field, paintIndex?}], styleId?}], palette {libraryId?, samples:
[{label, component, variant, action, state, useCases, instanceId?,
mainComponentId?, componentSetId?, labelNodeId?, documentationNodeId?}]}. IDs are required only for native evidence.
Readback supports readNativeSemantics flat nodes and bridge nested pages.
"""
import argparse
import copy
import json
import math
import re
from pathlib import Path

KINDS = {'color', 'typography', 'spacing', 'radius'}
FIELDS = {'color': {'fills', 'strokes'}, 'typography': {'fontSize', 'fontFamily'},
          'spacing': {'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'itemSpacing'},
          'radius': {'cornerRadius', 'topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'}}



def _opaque_rgb(value):
    """Typed COLOR native value: finite r/g/b in [0, 1], alpha absent or exactly 1."""
    return (isinstance(value, dict) and set(value) <= set('rgba') and set('rgb') <= set(value) and
            all(isinstance(value[c], (int, float)) and not isinstance(value[c], bool) and math.isfinite(value[c]) and 0 <= value[c] <= 1 for c in 'rgb')
            and value.get('a', 1) == 1)

def derive_foundations(graph):
    """Return canonical proposals, or a small editable plan from graph components.

    Defaults describe planned roles, never observed native token values or IDs.
    """
    if 'design_foundations' in graph:
        return graph['design_foundations']
    components = [node for node in graph.get('nodes', []) if node.get('type') == 'component']
    return {'version': 1, 'roles': [
        {'name': 'Surface', 'kind': 'color', 'token': 'color/surface', 'alias': 'palette/surface', 'value': 'Canvas surface color'},
        {'name': 'Body', 'kind': 'typography', 'token': 'type/body', 'alias': 'size/body', 'value': '16px body text'},
        {'name': 'Content padding', 'kind': 'spacing', 'token': 'space/content', 'alias': 'space/4', 'value': '16px content padding'},
        {'name': 'Related item gap', 'kind': 'spacing', 'token': 'space/related', 'alias': 'space/2', 'value': '8px related-item gap'},
        {'name': 'Control corners', 'kind': 'radius', 'token': 'radius/control', 'alias': 'radius/2', 'value': '8px control radius'}],
        'palette': {'samples': [
            {'label': node.get('title') or node['id'], 'component': node['id'], 'variant': 'Default',
             'action': node.get('description') or node.get('title') or node['id'], 'state': 'Default',
             'useCases': [node.get('title') or node['id']]} for node in components]}}


def _nodes(native):
    rows = []
    def visit(node, parent=None):
        row = dict(node)
        row['parentId'] = row.get('parentId', parent)
        rows.append(row)
        for child in node.get('children', []):
            visit(child, row.get('id'))
    for node in native.get('nodes', native.get('pages', [])):
        visit(node)
    return rows


def _alias(value):
    return value.get('id') if isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS' else None


def validate_foundations_review(contract, html):
    """Source check for visible review meaning; not browser or native evidence."""
    from annotation_contract import _HTML
    parsed = _HTML(html)
    visible = ' '.join(' '.join(parsed.visible).split())
    failures = []
    if not re.search(r'planned|계획|예정', visible, re.I) or not re.search(r'not native|네이티브.*아님|Figma.*아님', visible, re.I):
        failures.append({'code': 'missing-visible-plan-limitation', 'subject': 'planned / not native'})
    expected = []
    for role in contract.get('roles', []):
        expected.extend(str(role[key]) for key in ('name', 'kind', 'token', 'value') if role.get(key))
    for sample in contract.get('palette', {}).get('samples', []):
        expected.extend(str(sample[key]) for key in ('label', 'component', 'variant', 'action', 'state') if sample.get(key))
        expected.extend(sample.get('useCases', []))
    for value in expected:
        if ' '.join(value.split()) not in visible:
            failures.append({'code': 'missing-visible-foundation-review', 'subject': value})
    return {'ok': not failures, 'failures': failures, 'evidence_kind': 'html-source-only-not-browser-or-native'}


def validate_foundations(native, contract=None, *, stage='native'):
    """Return a composable fail-closed report; input metadata never grants approval."""
    if stage not in ('plan', 'native'):
        raise ValueError('stage must be plan or native')
    failures, coverage = [], {'roles': [], 'samples': [], 'styles': [], 'unbound_uses': []}
    def fail(code, subject):
        failures.append({'code': code, 'subject': str(subject)})
    def result():
        return {'ok': not failures, 'stage': stage, 'native_verified': stage == 'native' and not failures,
                'evidence_kind': 'proposed-only' if stage == 'plan' else 'native-readback-validation',
                'failures': failures, 'coverage': coverage}
    contract = copy.deepcopy(contract) if isinstance(contract, dict) else {}
    roles = contract.get('roles', [])
    samples = contract.get('palette', {}).get('samples', []) if isinstance(contract.get('palette'), dict) else []
    if contract.get('version') != 1 or not isinstance(roles, list) or not roles:
        fail('missing-foundations-contract', 'version 1 roles required')
        roles = []
    if not isinstance(samples, list) or not samples:
        fail('missing-palette-proposal', 'document reusable samples')
        samples = []
    names, tokens, labels = set(), set(), set()
    for role in roles:
        if not isinstance(role, dict):
            fail('invalid-role', role)
            continue
        name, token, kind = role.get('name'), role.get('token'), role.get('kind')
        if not isinstance(name, str) or not name.strip() or not isinstance(token, str) or not token.strip() or not isinstance(kind, str):
            fail('invalid-role', str(name))
            continue
        if name in names or token in tokens or kind not in KINDS:
            fail('invalid-role', name)
        names.add(name)
        tokens.add(token)
        native_role = role.get('native')
        if native_role is not None:
            native_type, value = (native_role.get('type'), native_role.get('value')) if isinstance(native_role, dict) else (None, None)
            valid = (native_type == 'STRING' and kind == 'typography' and isinstance(value, str) and bool(value.strip()) or
                     native_type == 'FLOAT' and kind != 'color' and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (value > 0 if kind == 'typography' else value >= 0) or
                     native_type == 'COLOR' and kind == 'color' and _opaque_rgb(value))
            if not valid:
                fail('invalid-native-role-value', name)
            if not role.get('bindings') and isinstance(native_role, dict):
                role['bindings'] = copy.deepcopy(native_role.get('bindings', []))
        if stage == 'plan' and native_role is None and ('value' not in role or role['value'] is None or role['value'] == ''):
            fail('missing-proposed-value', name)
    present = {role.get('kind') for role in roles if isinstance(role, dict) and isinstance(role.get('kind'), str)}
    for kind in sorted({'color', 'typography', 'spacing'} - present):
        fail('missing-role-kind', kind)
    for sample in samples:
        if not isinstance(sample, dict):
            fail('invalid-palette-sample', sample)
            continue
        label = sample.get('label')
        if not isinstance(label, str) or len(label.strip()) < 3 or label.casefold().strip() in labels:
            fail('missing-or-duplicate-sample-label', label)
        labels.add(str(label).casefold().strip())
        if any(not isinstance(sample.get(key), str) or not sample[key].strip()
               for key in ('component', 'variant', 'action', 'state')) or not isinstance(sample.get('useCases'), list) or not sample['useCases'] or any(not isinstance(v, str) or not v.strip() for v in sample['useCases']):
            fail('missing-sample-documentation', label)
    if stage == 'plan' or failures:
        return result()
    if not isinstance(native, dict):
        fail('missing-native-readback', 'native Plugin API evidence required')
        return result()
    rows = _nodes(native)
    nodes = {row.get('id'): row for row in rows if row.get('id')}
    if len(nodes) != len(rows):
        fail('ambiguous-native-node-ids', 'duplicate or missing node IDs')
    variables = {v['id']: v for v in native.get('variables', []) if v.get('id')}
    collections = {v['id']: v for v in native.get('collections', []) if v.get('id')}
    styles = {v['id']: v for v in native.get('styles', []) if v.get('id')}
    def resolve_key(key):
        matches = [node['id'] for node in rows if key and key in (node.get('semanticKey'), node.get('key'), node.get('semantic_id'))]
        if len(matches) != 1:
            fail('missing-or-ambiguous-native-key', key)
            return None
        return matches[0]
    for role in roles:
        for binding in role.get('bindings', []):
            if isinstance(binding, dict) and not binding.get('nodeId') and binding.get('key'):
                binding['nodeId'] = resolve_key(binding['key'])
        if role.get('styleName') and not role.get('styleId'):
            matches = [style['id'] for style in styles.values() if style.get('name') == role['styleName']]
            if len(matches) == 1:
                role['styleId'] = matches[0]
            else:
                fail('missing-or-ambiguous-native-style', role['styleName'])
    palette = contract['palette']
    if not palette.get('libraryId') and palette.get('libraryKey'):
        palette['libraryId'] = resolve_key(palette['libraryKey'])
    for sample in samples:
        for field, key in [('instanceId', 'instanceKey'), ('mainComponentId', 'mainComponentKey'), ('componentSetId', 'componentSetKey'), ('labelNodeId', 'labelKey'), ('documentationNodeId', 'documentationKey')]:
            if not sample.get(field) and sample.get(key):
                sample[field] = resolve_key(sample[key])
    def visible(node):
        seen = set()
        while node:
            if node.get('id') in seen or node.get('visible') is False or node.get('opacity') == 0:
                return False
            seen.add(node.get('id'))
            node = nodes.get(node.get('parentId'))
        return True
    def resolve(variable_id, seen=None):
        seen = set() if seen is None else seen
        if variable_id in seen or variable_id not in variables:
            return False
        seen = seen | {variable_id}
        variable = variables[variable_id]
        collection = collections.get(variable.get('variableCollectionId'))
        if not collection or not collection.get('modes'):
            return False
        values = variable.get('valuesByMode', {})
        for mode in collection['modes']:
            value = values.get(mode.get('modeId'))
            target = _alias(value)
            if target:
                if variables.get(target, {}).get('resolvedType') != variable.get('resolvedType') or not resolve(target, seen):
                    return False
            elif variable.get('resolvedType') == 'FLOAT':
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    return False
            elif variable.get('resolvedType') == 'COLOR':
                if not isinstance(value, dict) or any(not isinstance(value.get(c), (int, float)) or not 0 <= value[c] <= 1 for c in ('r', 'g', 'b')):
                    return False
            elif variable.get('resolvedType') == 'STRING':
                if not isinstance(value, str) or not value.strip():
                    return False
            else:
                return False
        return True
    def bound_ids(node, field, index=0):
        if field in ('fills', 'strokes'):
            paints = node.get(field, [])
            value = paints[index].get('boundVariables', {}).get('color') if isinstance(paints, list) and 0 <= index < len(paints) else None
            if value is None:
                style = styles.get(node.get('fillStyleId' if field == 'fills' else 'strokeStyleId'), {})
                style_paints = style.get('paints', [])
                if style.get('type') == 'PAINT' and isinstance(style_paints, list) and 0 <= index < len(style_paints) and isinstance(paints, list) and index < len(paints) and paints[index].get('color') == style_paints[index].get('color'):
                    value = style_paints[index].get('boundVariables', {}).get('color')
        else:
            value = node.get('fontFamilyBinding') if field == 'fontFamily' else None
            value = value if value is not None else node.get('boundVariables', {}).get(field)
            if field == 'fontSize' and value is None:
                style = styles.get(node.get('textStyleId'), {})
                if style.get('type') == 'TEXT' and style.get('fontSize') == node.get('fontSize'):
                    value = style.get('boundVariables', {}).get(field)
            if field == 'cornerRadius' and value is None:
                value = [node.get('boundVariables', {}).get(corner) for corner in FIELDS['radius'] - {'cornerRadius'}]
        return [_alias(v) for v in value] if isinstance(value, list) else [_alias(value)]
    for role in roles:
        if not isinstance(role, dict):
            continue
        kind, token = role.get('kind'), role.get('token')
        matches = [v for v in variables.values() if v.get('name') == token and
                   (not role.get('collection') or collections.get(v.get('variableCollectionId'), {}).get('name') == role['collection'])]
        variable = matches[0] if len(matches) == 1 else None
        expected_type = (role.get('native') or {}).get('type', role.get('native_type', 'COLOR' if kind == 'color' else 'FLOAT'))
        if not variable or variable.get('resolvedType') != expected_type or not resolve(variable['id']):
            fail('missing-or-invalid-native-token', token)
        elif role.get('alias'):
            for value in variable['valuesByMode'].values():
                target = variables.get(_alias(value), {})
                if target.get('name') != role['alias']:
                    fail('missing-semantic-alias', token)
        if variable and isinstance(role.get('native'), dict):
            for mode in collections.get(variable.get('variableCollectionId'), {}).get('modes', []):
                current, seen = variable, set()
                value = current.get('valuesByMode', {}).get(mode['modeId'])
                while _alias(value) and _alias(value) not in seen:
                    seen.add(_alias(value)); current = variables.get(_alias(value), {})
                    value = current.get('valuesByMode', {}).get(mode['modeId'])
                expected = role['native']['value']
                same = (_opaque_rgb(expected) and isinstance(value, dict) and value.get('a', 1) == 1 and
                        all(isinstance(value.get(c), (int, float)) and abs(value[c] - expected[c]) <= 1e-6 for c in 'rgb')
                        if role['native'].get('type') == 'COLOR' else value == expected)
                if not same:
                    fail('native-token-value-mismatch', token)
        bindings = role.get('bindings', [])
        if not isinstance(bindings, list) or not bindings:
            fail('missing-rendered-role-binding', token)
            continue
        for binding in bindings:
            if not isinstance(binding, dict):
                fail('invalid-role-binding', str(binding))
                continue
            if not isinstance(binding.get('nodeId'), str) or not isinstance(binding.get('field'), str) or not isinstance(binding.get('paintIndex', 0), int) or binding.get('paintIndex', 0) < 0:
                fail('invalid-role-binding', str(binding))
                continue
            node = nodes.get(binding.get('nodeId'))
            field = binding.get('field')
            if not node or not visible(node) or field not in FIELDS.get(kind, set()) or (field not in node and not (field == 'fontFamily' and isinstance(node.get('fontName'), dict))):
                fail('missing-rendered-property', binding)
                continue
            if field == 'fontFamily' and expected_type != 'STRING' or field == 'fontSize' and expected_type != 'FLOAT':
                fail('native-field-type-mismatch', token)
            if field == 'fontFamily' and role.get('native') and node.get('fontName', {}).get('family') != role['native']['value']:
                fail('native-rendered-value-mismatch', token)
            if expected_type == 'FLOAT' and role.get('native') and node.get(field) != role['native']['value']:
                fail('native-rendered-value-mismatch', token)
            ids = bound_ids(node, field, binding.get('paintIndex', 0))
            if not variable or not ids or any(identifier != variable['id'] for identifier in ids):
                fail('native-binding-mismatch', f"{node['id']}.{field}")
            else:
                coverage['roles'].append({'role': role.get('name'), 'nodeId': node['id'], 'field': field, 'variableId': variable['id']})
            if role.get('styleId'):
                style_field = 'textStyleId' if kind == 'typography' else 'fillStyleId' if field == 'fills' else 'strokeStyleId' if field == 'strokes' else None
                if role['styleId'] not in styles or not style_field or node.get(style_field) != role['styleId']:
                    fail('native-style-mismatch', role['styleId'])
                else:
                    coverage['styles'].append({'styleId': role['styleId'], 'nodeId': node['id']})
    # Check actual used native properties too: declarations cannot hide color-only work.
    for node in rows:
        if not visible(node):
            continue
        if node.get('type') == 'TEXT' and node.get('unavailable_fields', {}).get('fontSize'):
            fail('unavailable-rendered-property', f"{node['id']}.fontSize")
        for kind, fields in FIELDS.items():
            for field in fields:
                if field in ('fills', 'strokes'):
                    paints = node.get(field, [])
                    uses = [i for i, p in enumerate(paints) if p.get('type') == 'SOLID' and p.get('visible', True) and p.get('opacity', 1) > 0] if isinstance(paints, list) else []
                else:
                    value = node.get(field)
                    if field == 'fontFamily':
                        uses = [0] if node.get('type') == 'TEXT' and (node.get('boundVariables', {}).get(field) or node.get('fontFamilyBinding') or any((role.get('native') or {}).get('type') == 'STRING' for role in roles)) else []
                    else:
                        uses = [0] if isinstance(value, (int, float)) and value > 0 and (kind != 'spacing' or node.get('layoutMode') in ('VERTICAL', 'HORIZONTAL')) else []
                for index in uses:
                    ids = bound_ids(node, field, index)
                    if not ids or any(not identifier or not resolve(identifier) or variables.get(identifier, {}).get('resolvedType') != ('COLOR' if kind == 'color' else 'STRING' if field == 'fontFamily' else 'FLOAT') for identifier in ids):
                        use = {'nodeId': node['id'], 'field': field, 'kind': kind}
                        coverage['unbound_uses'].append(use)
                        fail('unbound-rendered-use', f"{node['id']}.{field}")
                    if kind == 'radius' and 'radius' not in present:
                        fail('missing-role-kind', 'radius used in native nodes')
    library_id = contract.get('palette', {}).get('libraryId')
    library = nodes.get(library_id)
    if not library or not visible(library):
        fail('missing-visible-palette-library', library_id)
    def descendant(node, ancestor_id):
        seen = set()
        while node and node.get('id') not in seen:
            seen.add(node.get('id'))
            if node.get('parentId') == ancestor_id:
                return True
            node = nodes.get(node.get('parentId'))
        return False
    def rect(node):
        box = node.get('absoluteBoundingBox')
        if isinstance(box, dict):
            return box
        x, y = node.get('x'), node.get('y')
        parent, seen = nodes.get(node.get('parentId')), set()
        while parent and parent.get('id') not in seen:
            seen.add(parent.get('id'))
            x = x + parent.get('x', 0) if isinstance(x, (int, float)) else None
            y = y + parent.get('y', 0) if isinstance(y, (int, float)) else None
            parent = nodes.get(parent.get('parentId'))
        return {'x': x, 'y': y, 'width': node.get('width'), 'height': node.get('height')}
    def overlaps(group):
        boxes = []
        for node in group:
            box = rect(node)
            if any(not isinstance(box.get(k), (int, float)) or not math.isfinite(box[k]) for k in ('x', 'y', 'width', 'height')) or box['width'] <= 0 or box['height'] <= 0:
                fail('missing-visible-palette-bounds', node['id'])
                continue
            for other, b in boxes:
                if box['x'] < b['x'] + b['width'] and b['x'] < box['x'] + box['width'] and box['y'] < b['y'] + b['height'] and b['y'] < box['y'] + box['height']:
                    fail('overlapping-palette-items', f"{other['id']} / {node['id']}")
            boxes.append((node, box))
    rendered_samples = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        instance = nodes.get(sample.get('instanceId'))
        main = nodes.get(sample.get('mainComponentId'))
        component_set = nodes.get(sample.get('componentSetId'))
        valid = (library and instance and instance.get('type') == 'INSTANCE' and visible(instance) and
                 descendant(instance, library_id) and instance.get('name') == sample.get('label') and
                 main and main.get('type') == 'COMPONENT' and component_set and component_set.get('type') == 'COMPONENT_SET' and
                 main.get('parentId', main.get('componentSetId')) == component_set['id'] and
                 instance.get('mainComponentId', instance.get('main_component_id')) == main['id'] and
                 sample.get('variant') in main.get('variantProperties', {}).values())
        label_node = nodes.get(sample.get('labelNodeId'))
        documentation = nodes.get(sample.get('documentationNodeId'))
        if not label_node or label_node.get('type') != 'TEXT' or not visible(label_node) or not descendant(label_node, library_id) or label_node.get('characters') != sample.get('label'):
            fail('missing-visible-sample-label', sample.get('label'))
        if not documentation or documentation.get('type') != 'TEXT' or not visible(documentation) or not descendant(documentation, library_id) or any(text not in documentation.get('characters', '') for text in [sample['action'], sample['state'], *sample['useCases']]):
            fail('missing-visible-sample-documentation', sample.get('label'))
        if not valid:
            fail('invalid-palette-native-relationship', sample.get('label'))
        else:
            rendered_samples.append(instance)
            coverage['samples'].append({'instanceId': instance['id'], 'mainComponentId': main['id'], 'componentSetId': component_set['id']})
    referenced_sets = {sample.get('componentSetId') for sample in samples if isinstance(sample, dict)}
    sets = [n for n in rows if n.get('type') == 'COMPONENT_SET' and visible(n) and (n['id'] in referenced_sets or library_id and descendant(n, library_id))]
    overlaps(rendered_samples + sets)
    for component_set in sets:
        overlaps([n for n in rows if n.get('parentId') == component_set['id'] and visible(n)])
    return result()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native', nargs='?', type=Path)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--stage', choices=('plan', 'native'), default='native')
    args = parser.parse_args()
    report = validate_foundations(json.loads(args.native.read_text()) if args.native else None,
                                  json.loads(args.contract.read_text()), stage=args.stage)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
