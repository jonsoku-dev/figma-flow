#!/usr/bin/env python3
"""Fail-closed validation of supplied native readback; never authenticates its origin.

Contract: collection_id (or collection_name), variables [{id/name, resolved_type?}],
screens [{id/key, controls [{id/key, action, states, component_id/component_key, token_bindings:
[{property: 'fills.0.color' or 'cornerRadius', variable_id/variable}]}]}].
All IDs refer to actual native objects, never declared plugin metadata.
"""
import argparse
import json
import math
from pathlib import Path
import re


OBSERVED_FIELDS = ('type', 'name', 'characters', 'visible', 'x', 'y', 'width', 'height',
                   'layoutMode', 'primaryAxisSizingMode', 'counterAxisSizingMode', 'layoutSizingHorizontal',
                   'layoutSizingVertical', 'layoutWrap', 'textAutoResize', 'absoluteBoundingBox', 'minWidth',
                   'maxWidth', 'minHeight', 'maxHeight', 'itemSpacing', 'paddingTop', 'paddingRight',
                   'paddingBottom', 'paddingLeft', 'constraints', 'clipsContent', 'hyperlink', 'reactions',
                   'componentProperties', 'variantProperties', 'fills', 'strokes',
                   'boundVariables', 'cornerRadius', 'opacity', 'fontSize')


def normalize(readback):
    if not isinstance(readback, dict):
        raise ValueError('readback must be an object')
    nodes, parents = {}, {}

    def visit(node, parent=None):
        if not isinstance(node, dict) or not isinstance(node.get('id'), str):
            raise ValueError('every current node requires a native string id')
        identity = node['id']
        if identity in nodes:
            raise ValueError('duplicate native node id: ' + identity)
        nodes[identity] = node
        parents[identity] = node.get('parentId', parent)
        for child in node.get('children', []):
            if isinstance(child, dict):
                visit(child, identity)
    roots = readback.get('pages', readback.get('nodes'))
    if not isinstance(roots, list) or not roots:
        raise ValueError('missing current pages or nodes')
    for root in roots:
        visit(root)
    return nodes, parents


def annotations(node):
    if node.get('annotations_status') == 'unavailable':
        return []
    return [a['label'] for a in node.get('annotations', [])
            if isinstance(a, dict) and isinstance(a.get('label'), str) and a['label'].strip()]


def mentions(text, literal):
    return isinstance(literal, str) and bool(literal.strip()) and bool(
        re.search(r'(?<!\w)' + re.escape(literal) + r'(?!\w)', text, re.IGNORECASE))


def binding_at(node, path):
    parts = path.split('.')
    try:
        if len(parts) == 1:
            return node.get('boundVariables', {}).get(path)
        if parts[0] in ('fills', 'strokes') and len(parts) == 3:
            return node[parts[0]][int(parts[1])].get('boundVariables', {}).get(parts[2])
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    return None


def scalar(value, kind):
    if kind == 'BOOLEAN':
        return isinstance(value, bool)
    if kind == 'STRING':
        return isinstance(value, str) and bool(value.strip())
    if kind == 'FLOAT':
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if kind == 'COLOR':
        return isinstance(value, dict) and all(isinstance(value.get(k), (int, float))
            and not isinstance(value[k], bool) and math.isfinite(value[k]) and 0 <= value[k] <= 1
            for k in ('r', 'g', 'b')) and ('a' not in value or
            isinstance(value['a'], (int, float)) and not isinstance(value['a'], bool)
            and math.isfinite(value['a']) and 0 <= value['a'] <= 1)
    return False


def evaluate(readback, expected=None, page_id=None):
    """Return report and observed screen specification; malformed/missing evidence fails."""
    errors, screens, token_records = [], [], []
    report = {'schema': 'figma-flow-native-handoff-v1', 'status': 'blocked', 'passed': False,
              'errors': errors, 'screens': screens, 'variables': token_records,
              'source_verification': 'Validates supplied evidence only; cannot cryptographically authenticate frontend origin.'}
    try:
        nodes, parents = normalize(readback)
        if not isinstance(expected, dict):
            raise ValueError('explicit expected contract required; no evidence-only success')
        page_id = page_id or readback.get('pageId')
        pages = [n['id'] for n in nodes.values() if n.get('type') == 'PAGE']
        if not page_id and len(pages) == 1:
            page_id = pages[0]
        if not page_id or (page_id not in pages and page_id != readback.get('pageId')):
            raise ValueError('selected native page is absent from readback')
        report['page_id'] = page_id
        file_key = readback.get('fileKey') or readback.get('file_key') or expected.get('file_key') or expected.get('fileKey')
        if not isinstance(file_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file_key):
            errors.append('native file key required for native screen links')
            file_key = None

        def within(identity, ancestor):
            seen = set()
            while identity and identity not in seen:
                if identity == ancestor:
                    return True
                seen.add(identity)
                identity = parents.get(identity)
            return False

        def native_url(identity):
            return f'https://www.figma.com/design/{file_key}?node-id={identity.replace(":", "-")}' if file_key else None

        def select(wanted, prefix=''):
            identity = wanted.get(prefix + 'id')
            if identity:
                return identity if identity in nodes else None
            key = wanted.get(prefix + 'key')
            matches = [n['id'] for n in nodes.values() if key and
                       (n.get('semanticKey') == key or n.get('key') == key or n.get('semantic_id') == key)]
            return matches[0] if len(matches) == 1 else None

        collections = readback.get('collections', readback.get('variableCollections', []))
        page_collection = nodes.get(page_id, {}).get('declared_metadata', {}).get('collection_id')
        matches = [c for c in collections if isinstance(c, dict) and
                   (c.get('id') == expected.get('collection_id') if expected.get('collection_id')
                    else ((c.get('semantic_id') or c.get('declared_metadata', {}).get('semantic_id')) == expected['collection_key']
                          if expected.get('collection_key') else c.get('name') == expected.get('collection_name')))
                   and (not page_collection or c.get('id') == page_collection)]
        if len(matches) != 1 or not matches[0].get('id'):
            raise ValueError('exactly one selected native variable collection required')
        collection = matches[0]
        report['collection'] = collection
        variables = readback.get('variables', [])
        if not isinstance(variables, list) or any(not isinstance(v, dict) or not v.get('id') for v in variables):
            raise ValueError('native variables require IDs')
        by_var = {v['id']: v for v in variables}
        if len(by_var) != len(variables):
            raise ValueError('duplicate native variable IDs')
        modes = [m['modeId'] for m in collection.get('modes', []) if isinstance(m, dict) and m.get('modeId')]
        if not modes or len(modes) != len(set(modes)):
            raise ValueError('selected collection requires unique native modes')

        def resolve(identity, mode, trail=()):
            if identity in trail or identity not in by_var:
                raise ValueError('missing/cyclic native variable alias: ' + str(identity))
            var = by_var[identity]
            if var.get('variableCollectionId') != collection['id']:
                raise ValueError('variable outside selected collection: ' + identity)
            value = var.get('valuesByMode', {}).get(mode)
            if isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS':
                result = resolve(value.get('id'), mode, trail + (identity,))
                if by_var[value['id']].get('resolvedType') != var.get('resolvedType'):
                    raise ValueError('alias type mismatch: ' + identity)
                return result
            if not scalar(value, var.get('resolvedType')):
                raise ValueError('missing/invalid scalar value: ' + identity + ' mode ' + mode)
            return {'value': value, 'alias_chain': list(trail) + [identity]}

        declared_vars = expected.get('variables')
        if not isinstance(declared_vars, list) or not declared_vars:
            raise ValueError('expected semantic variables required')
        selected_ids = set()
        for wanted in declared_vars:
            found = [v for v in variables if v.get('variableCollectionId') == collection['id'] and
                     (v['id'] == wanted['id'] if wanted.get('id') else v.get('name') == wanted.get('name'))]
            if len(found) != 1:
                errors.append('expected native variable missing/ambiguous: ' + str(wanted))
                continue
            var = found[0]
            selected_ids.add(var['id'])
            record = {k: var.get(k) for k in ('id', 'name', 'resolvedType', 'valuesByMode')}
            record['resolved_modes'] = {}
            token_records.append(record)
            if wanted.get('resolved_type') and var.get('resolvedType') != wanted['resolved_type']:
                errors.append('variable type mismatch: ' + var['id'])
            for mode in modes:
                try:
                    record['resolved_modes'][mode] = resolve(var['id'], mode)
                except ValueError as exc:
                    errors.append(str(exc))
        wanted_screens = expected.get('screens')
        if not isinstance(wanted_screens, list) or not wanted_screens:
            raise ValueError('expected screens and important controls required')
        seen_screens = set()
        verified_instances = 0
        for wanted in wanted_screens:
            sid = select(wanted)
            if sid is None:
                errors.append('missing/ambiguous expected screen: ' + str(wanted.get('id', wanted.get('key'))))
                continue
            screen = nodes.get(sid, {})
            if sid in seen_screens or screen.get('type') not in ('FRAME', 'COMPONENT') or not within(sid, page_id):
                errors.append('missing/duplicate screen on selected page: ' + sid)
                continue
            seen_screens.add(sid)
            item = {'id': sid, 'url': native_url(sid),
                    'observed': {k: screen[k] for k in OBSERVED_FIELDS if k in screen},
                    'native_annotations': annotations(screen), 'controls': [], 'additional_annotations': []}
            screens.append(item)
            if not item['native_annotations']:
                errors.append('screen lacks native annotation: ' + sid)
            if wanted.get('static') is True and any(n.get('reactions') and within(n['id'], sid) for n in nodes.values()):
                errors.append('static screen contains native interactions: ' + sid)
            controls = wanted.get('controls')
            if not isinstance(controls, list) or (not controls and wanted.get('static') is not True):
                errors.append('expected important controls required: ' + sid)
                continue
            seen_controls = set()
            for control in controls:
                cid = select(control)
                if cid is None:
                    errors.append('missing/ambiguous important control: ' + str(control.get('id', control.get('key'))))
                    continue
                node = nodes.get(cid, {})
                if cid in seen_controls or cid == sid or not within(cid, sid):
                    errors.append('missing/duplicate important control: ' + cid)
                    continue
                seen_controls.add(cid)
                notes = annotations(node)
                current = {'id': cid, 'url': native_url(cid), 'observed': {k: node[k] for k in OBSERVED_FIELDS if k in node},
                           'native_annotations': notes, 'bindings': [], 'covered_action': None, 'covered_states': []}
                item['controls'].append(current)
                action, states = control.get('action'), control.get('states')
                text = '\n'.join(notes).casefold()
                static = control.get('static') is True
                current['static'] = static
                if static:
                    current['static_annotation'] = control.get('static_annotation')
                if not notes:
                    errors.append('control lacks native annotation: ' + cid)
                if static and (action or states or any(control.get(field) for field in ('action_id', 'target', 'target_screen', 'target_ids')) or any(n.get('reactions') and within(n['id'], cid) for n in nodes.values())):
                    errors.append('static control declares interaction: ' + cid)
                if not static and not mentions(text, action):
                    errors.append('control native annotation lacks expected action: ' + cid)
                elif not static:
                    current['covered_action'] = action
                if not static and (not isinstance(states, list) or not states or any(not mentions(text, s) for s in states)):
                    errors.append('control native annotation lacks expected states: ' + cid)
                elif not static:
                    current['covered_states'] = states
                component_id = node.get('mainComponentId', node.get('main_component_id'))
                component = nodes.get(component_id, {})
                component_set = nodes.get(parents.get(component_id), {})
                valid_component = not (node.get('type') != 'INSTANCE' or not (control.get('component_id') or control.get('component_key')) or
                    component_id != select(control, 'component_') or component.get('type') != 'COMPONENT' or
                    (not static and (component_set.get('type') != 'COMPONENT_SET' or not component.get('variantProperties'))) or not within(component_id, page_id))
                if not valid_component:
                    errors.append('control lacks real local component-set instance: ' + cid)
                else:
                    current['main_component'] = {k: component[k] for k in ('id', 'name', 'variantProperties') if k in component}
                    current['main_component']['url'] = native_url(component_id)
                    if component_set.get('type') == 'COMPONENT_SET':
                        current['component_set_id'] = component_set['id']
                        current['component_set_url'] = native_url(component_set['id'])
                    if 'native_state_property' in control or 'state_variants' in control:
                        prop = control.get('native_state_property', 'State')
                        required = control.get('state_variants', states)
                        if isinstance(required, dict):
                            required = ([required[state] for state in states]
                                        if isinstance(states, list) and all(state in required for state in states) else None)
                        if (not isinstance(prop, str) or not prop.strip() or not isinstance(required, list) or not required or
                            any(not isinstance(value, str) or not value.strip() for value in required)):
                            errors.append('invalid native state variant contract: ' + cid)
                        else:
                            variants = [candidate for candidate in nodes.values()
                                        if candidate.get('type') == 'COMPONENT' and parents.get(candidate['id']) == component_set['id']]
                            current['native_state_property'] = prop
                            current['native_state_variants'] = [dict(
                                {k: variant[k] for k in ('id', 'name', 'variantProperties') if k in variant},
                                url=native_url(variant['id'])) for variant in variants]
                            observed_states = {variant.get('variantProperties', {}).get(prop) for variant in variants}
                            missing = [value for value in required if value not in observed_states]
                            if missing:
                                errors.append('missing native component state variants: ' + cid + ' ' + ', '.join(missing))
                            else:
                                current['covered_native_states'] = required
                bindings = control.get('token_bindings')
                if not isinstance(bindings, list) or not bindings:
                    errors.append('expected important token bindings required: ' + cid)
                    continue
                for binding in bindings:
                    prop, vid = binding.get('property'), binding.get('variable_id')
                    if not vid and binding.get('variable'):
                        candidates = [v['id'] for v in variables if v.get('name') == binding['variable']
                                      and v.get('variableCollectionId') == collection['id']]
                        vid = candidates[0] if len(candidates) == 1 else None
                    binding_id = select(binding, 'node_') if binding.get('node_id') or binding.get('node_key') else cid
                    if not binding_id or not within(binding_id, cid):
                        errors.append('binding node is not within control: ' + cid)
                        continue
                    actual = binding_at(nodes[binding_id], prop) if isinstance(prop, str) else None
                    if isinstance(actual, list) and len(actual) == 1:
                        actual = actual[0]
                    if not isinstance(actual, dict) or actual.get('type') != 'VARIABLE_ALIAS' or actual.get('id') != vid or vid not in selected_ids:
                        errors.append('missing/wrong native variable binding: ' + cid + ' ' + str(prop))
                        continue
                    current['bindings'].append({'property': prop, 'variable_id': vid, 'node_id': binding_id,
                        'variable': next((v for v in token_records if v['id'] == vid), None)})
                if valid_component and notes and current['bindings']:
                    verified_instances += 1
            for identity, node in nodes.items():
                notes = annotations(node)
                if identity == sid or identity in seen_controls or not notes or not within(identity, sid):
                    continue
                extra = {'id': identity, 'url': native_url(identity),
                         'observed': {k: node[k] for k in OBSERVED_FIELDS if k in node},
                         'native_annotations': notes, 'annotation_details': node.get('annotations', []),
                         'bindings': []}
                for prop, alias in node.get('boundVariables', {}).items():
                    values = alias if isinstance(alias, list) else [alias]
                    for value in values:
                        if isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS':
                            extra['bindings'].append({'property': prop, 'variable_id': value.get('id'),
                                                      'variable': by_var.get(value.get('id'))})
                for field in ('fills', 'strokes'):
                    paints = node.get(field, [])
                    for index, paint in enumerate(paints if isinstance(paints, list) else []):
                        for prop, alias in paint.get('boundVariables', {}).items():
                            if isinstance(alias, dict) and alias.get('type') == 'VARIABLE_ALIAS':
                                extra['bindings'].append({'property': f'{field}.{index}.{prop}',
                                    'variable_id': alias.get('id'), 'variable': by_var.get(alias.get('id'))})
                component_id = node.get('mainComponentId', node.get('main_component_id'))
                if component_id:
                    component = nodes.get(component_id, {})
                    extra['main_component'] = {k: component[k] for k in ('id', 'name', 'variantProperties') if k in component}
                    extra['main_component'].update(id=component_id, url=native_url(component_id))
                    if nodes.get(parents.get(component_id), {}).get('type') == 'COMPONENT_SET':
                        extra['component_set_id'] = parents[component_id]
                        extra['component_set_url'] = native_url(parents[component_id])
                item['additional_annotations'].append(extra)
        if not verified_instances:
            errors.append('at least one annotated native reusable instance with verified token bindings required')
        declaration = expected.get('annotation_contract')
        strict_creation = expected.get('mode') == 'strict-creation' or (
            isinstance(declaration, dict) and declaration.get('mode') == 'strict-creation')
        if strict_creation:
            from annotation_contract import validate_native_annotations
            annotation_result = validate_native_annotations(readback, declaration, page_id)
            report['annotation_contract'] = annotation_result
            errors.extend('annotation contract: ' + error for error in annotation_result['errors'])
            graph_nodes = declaration.get('product_graph', {}).get('nodes', []) if isinstance(declaration, dict) else []
            graph_by_id = {node['id']: node for node in graph_nodes}
            graph_screen_ids = {node['id'] for node in graph_nodes if node.get('type') == 'screen'}
            prototype_checks = []
            report['prototype_checks'] = prototype_checks
            for screen in expected.get('screens', []):
                for control in screen.get('controls', []):
                    action = graph_by_id.get(control.get('action'), {})
                    graph_targets = [target for target in action.get('target_ids', []) if target in graph_screen_ids]
                    target_key = control.get('target_screen')
                    if not target_key and len(graph_targets) == 1:
                        target_key = graph_targets[0]
                    if not target_key and not graph_targets:
                        continue
                    source_id = select(control)
                    destination_id = next((node['id'] for node in annotation_result['nodes'] if node['semantic_id'] == target_key and target_key in graph_screen_ids), None)
                    destination_id = destination_id or (select({'key': target_key}) if target_key else None)
                    if not destination_id and target_key in nodes and nodes[target_key].get('type') in ('FRAME', 'COMPONENT'):
                        destination_id = target_key
                    if (not source_id or not destination_id or not within(destination_id, page_id) or
                        graph_targets and target_key not in graph_targets):
                        errors.append('resolved native navigation destination required: ' + str(control.get('key', control.get('id'))))
                        continue
                    observed = [reaction_action.get('destinationId') for reaction in nodes[source_id].get('reactions', [])
                                if reaction.get('trigger', {}).get('type') == 'ON_CLICK'
                                for reaction_action in reaction.get('actions', [])
                                if reaction_action.get('type') == 'NODE' and reaction_action.get('navigation') == 'NAVIGATE']
                    passed = observed == [destination_id]
                    prototype_checks.append({'source_id': source_id, 'destination_id': destination_id, 'observed_destination_ids': observed, 'passed': passed})
                    if not passed:
                        errors.append('declared native navigation reaction missing/wrong: ' + source_id)
            covered = {node['id'] for node in annotation_result['nodes']}
            canonical_nodes = {node['id']: node for node in declaration.get('product_graph', {}).get('nodes', [])} if isinstance(declaration, dict) else {}
            for screen in screens:
                if screen['id'] not in covered:
                    errors.append('annotation contract misses required native node: ' + screen['id'])
                source = next((node for node in annotation_result['nodes'] if node['id'] == screen['id']), {})
                screen_meaning = canonical_nodes.get(source.get('semantic_id'), {}).get('annotation', {})
                for control in screen['controls']:
                    if not control['static']:
                        if control['id'] not in covered:
                            errors.append('annotation contract misses required native node: ' + control['id'])
                        continue
                    text = '\n'.join(control['native_annotations'])
                    expected_note = control.get('static_annotation')
                    if (not isinstance(expected_note, str) or len(expected_note.strip()) < 6 or expected_note not in text or
                        screen['id'] not in covered or not all(isinstance(screen_meaning.get(field), str) and
                            screen_meaning[field] in expected_note for field in ('purpose', 'journey'))):
                        errors.append('static instance lacks canonical screen/sample native annotation: ' + control['id'])
        board_contract = expected.get('design_note_board')
        if strict_creation or board_contract is not None:
            board_report = {'passed': False, 'entries': [], 'errors': []}
            report['design_note_board'] = board_report
            board_errors = board_report['errors']
            if not isinstance(board_contract, dict) or board_contract.get('required') is not True or not isinstance(board_contract.get('entries'), list) or not board_contract['entries']:
                board_errors.append('required Design-mode note board declaration missing')
            else:
                board_id = select({'key': board_contract.get('key')})
                board = nodes.get(board_id, {})
                if (board.get('type') != 'FRAME' or not within(board_id, page_id) or board.get('visible') is not True or
                    board.get('layoutMode') != 'VERTICAL' or board.get('itemSpacing', 0) <= 0 or board.get('clipsContent') is not False):
                    board_errors.append('visible ordinary Design-mode note frame required')
                target_ids, note_ids, rendered_bounds = set(), set(), []
                for entry in board_contract['entries']:
                    target_id = select({'key': entry.get('target_key')})
                    note_id = select({'key': str(board_contract.get('key')) + ':' + str(entry.get('key'))})
                    target, note = nodes.get(target_id, {}), nodes.get(note_id, {})
                    label = entry.get('label')
                    link = note.get('hyperlink')
                    if (not target_id or not within(target_id, page_id) or within(target_id, board_id) or
                        not isinstance(label, str) or len(label.strip()) < 6 or label not in '\n'.join(annotations(target)) or
                        not note_id or note_id in note_ids or note.get('type') != 'TEXT' or note.get('visible') is not True or
                        parents.get(note_id) != board_id or note.get('fontSize', 0) < 14 or note.get('textAutoResize') != 'HEIGHT' or
                        label not in note.get('characters', '') or not isinstance(link, dict) or link.get('type') != 'NODE' or link.get('value') != target_id):
                        board_errors.append('missing readable Design-mode native target link: ' + str(entry.get('key')))
                    bounds, frame_bounds = note.get('absoluteBoundingBox', {}), board.get('absoluteBoundingBox', {})
                    if not (all(isinstance(bounds.get(field), (int, float)) and math.isfinite(bounds[field]) for field in ('x', 'y', 'width', 'height')) and
                            all(isinstance(frame_bounds.get(field), (int, float)) and math.isfinite(frame_bounds[field]) for field in ('x', 'y', 'width', 'height')) and
                            bounds.get('width', 0) > 0 and bounds.get('height', 0) > 0 and frame_bounds.get('width', 0) > 0 and frame_bounds.get('height', 0) > 0 and
                            bounds['x'] >= frame_bounds['x'] and bounds['y'] >= frame_bounds['y'] and
                            bounds['x'] + bounds['width'] <= frame_bounds['x'] + frame_bounds['width'] + 0.1 and
                            bounds['y'] + bounds['height'] <= frame_bounds['y'] + frame_bounds['height'] + 0.1):
                        board_errors.append('Design-mode note bounds unavailable/outside board: ' + str(entry.get('key')))
                    else:
                        for previous in rendered_bounds:
                            if (bounds['x'] < previous['x'] + previous['width'] and previous['x'] < bounds['x'] + bounds['width'] and
                                bounds['y'] < previous['y'] + previous['height'] and previous['y'] < bounds['y'] + bounds['height']):
                                board_errors.append('Design-mode note text overlaps: ' + str(entry.get('key')))
                        rendered_bounds.append(bounds)
                    target_ids.add(target_id)
                    note_ids.add(note_id)
                    board_report['entries'].append({'text_node_id': note_id, 'target_id': target_id})
                for screen in screens:
                    for required_id in [screen['id']] + [control['id'] for control in screen['controls']]:
                        if required_id not in target_ids:
                            board_errors.append('Design-mode note index misses native target: ' + required_id)
            board_report['passed'] = not board_errors
            errors.extend('Design-mode note board: ' + error for error in board_errors)
        report['passed'] = not errors
        report['status'] = 'passed' if report['passed'] else 'blocked'
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append('invalid or incomplete evidence/contract: ' + str(exc))
    return report


def markdown(report):
    def text(value):
        return str(value).replace('\n', ' ').replace('|', '\\|')

    def link(label, url):
        return f'[{text(label)}]({url})' if url else text(label)

    def notes(labels):
        return ['- ' + text(re.sub(r'^\[figma-flow:[^\]]+\]\s*', '', label)) for label in labels]

    def control_lines(control, required):
        observed = control['observed']
        title = observed.get('name') or control['id']
        result = ['', '### ' + link(title, control.get('url')), '',
                  '네이티브 노드: `' + text(control['id']) + '` · 유형: ' + text(observed.get('type', '미관측'))]
        if required and control.get('static'):
            result += ['용도: 정적 재사용 컴포넌트 (동작·상태 검증 대상 아님)']
        elif required:
            result += ['동작: ' + text(control['covered_action'] or '검증되지 않음'),
                       '상태: ' + (', '.join(map(text, control['covered_states'])) or '검증되지 않음')]
        result += notes(control['native_annotations'])
        main = control.get('main_component')
        if main:
            variants = main.get('variantProperties') or observed.get('variantProperties', {})
            result += ['- 사용 컴포넌트: ' + link(main.get('name') or main.get('id'), main.get('url')) +
                       (' · 변형: ' + ', '.join(f'{text(k)}={text(v)}' for k, v in variants.items()) if variants else '')]
            if control.get('component_set_id'):
                result += ['- 컴포넌트 세트: ' + link(control['component_set_id'], control.get('component_set_url'))]
        if control.get('native_state_variants'):
            prop = control['native_state_property']
            result += ['- 실제 상태 변형 (' + text(prop) + '): ' + ', '.join(
                link(variant.get('variantProperties', {}).get(prop, '미관측'), variant.get('url'))
                for variant in control['native_state_variants'])]
        for binding in control['bindings']:
            token = binding.get('variable') or {}
            result += ['- 토큰: `' + text(token.get('name') or binding.get('variable_id')) + '` → `' + text(binding['property']) + '`']
        return result

    status = '통과' if report['passed'] else '차단'
    lines = ['# 네이티브 화면 명세', '', '검증 상태: ' + status, '',
             '제공된 네이티브 읽기 자료를 기대 계약과 대조했습니다. 이 검증은 자료의 출처 자체를 인증하지 않습니다.',
             '레이아웃·반응·주석 원문·변수 모드와 별칭의 세부 값은 screen-spec.json과 report.json에 보존됩니다.', '']
    lines += ['- 차단 사유: ' + text(error) for error in report['errors']]
    for screen in report['screens']:
        observed = screen['observed']
        lines += ['', '## ' + link(observed.get('name') or screen['id'], screen.get('url')), '',
                  '화면 ID: `' + text(screen['id']) + '`',
                  '크기: ' + text(observed.get('width', '미관측')) + ' × ' + text(observed.get('height', '미관측')) + ' px',
                  '', '화면 설명:']
        lines += notes(screen['native_annotations'])
        lines += ['', '### 필수 조작 검증', '', '아래 조작은 기대한 동작·상태·컴포넌트 인스턴스·토큰 바인딩을 검사합니다.']
        for control in screen['controls']:
            lines += control_lines(control, True)
        additional = screen.get('additional_annotations', [])
        if additional:
            lines += ['', '### 추가로 관측한 화면 주석과 조작', '',
                      '실제 화면 안의 네이티브 주석입니다. 필수 조작 검증과 별도로 기록하며, 주석에 없는 동작이나 상태를 추정하지 않습니다.']
            for control in additional:
                lines += control_lines(control, False)
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readback', required=True)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--page-id')
    parser.add_argument('--out', required=True, help='new output directory; existing evidence is never overwritten')
    args = parser.parse_args()
    try:
        readback = json.loads(Path(args.readback).read_text())
        expected = json.loads(Path(args.contract).read_text())
        report = evaluate(readback, expected, args.page_id)
    except (OSError, ValueError) as exc:
        parser.exit(2, 'native handoff blocked: ' + str(exc) + '\n')
    output = Path(args.out)
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.exit(2, 'new output directory required: ' + str(exc) + '\n')
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (output / 'screen-spec.json').write_text(json.dumps({'schema': report['schema'], 'status': report['status'], 'screens': report['screens']}, ensure_ascii=False, indent=2) + '\n')
    (output / 'screen-spec.md').write_text(markdown(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
