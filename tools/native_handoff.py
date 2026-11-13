#!/usr/bin/env python3
"""Fail-closed validation of supplied native readback; never authenticates its origin.

Contract: collection_id (or collection_name), variables [{id/name, resolved_type?}],
screens [{id/key, controls [{id/key, action, states, component_id/component_key, token_bindings:
[{property: 'fills.0.color' or 'cornerRadius', variable_id/variable}]}]}].
All IDs refer to actual native objects, never declared plugin metadata.
"""
import argparse
import hashlib
import html
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
    return [a.get('label') or a['labelMarkdown'] for a in node.get('annotations', [])
            if isinstance(a, dict) and isinstance(a.get('label') or a.get('labelMarkdown'), str)
            and (a.get('label') or a.get('labelMarkdown')).strip()]


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
        declaration = expected.get('annotation_contract') or {}
        readable = isinstance(declaration.get('specifications'), dict)
        if expected.get('annotation_presentation') == 'metadata' and not readable:
            raise ValueError('metadata presentation requires current graph specifications')

        def semantic_text(node):
            if readable and isinstance(node.get('specification'), dict):
                meaning = node['specification'].get('specification', {}).get('meaning', {})
                return '\n'.join(str(value) for value in meaning.values())
            if readable:
                return node.get('declared_metadata', {}).get('technical_annotation', '')
            return '\n'.join(annotations(node))
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
            if not item['native_annotations'] and not (readable and screen.get('specification')):
                errors.append('screen lacks native annotation: ' + sid)
            if readable:
                item['specification'] = screen.get('specification')
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
                text = semantic_text(node).casefold()
                static = control.get('static') is True
                current['static'] = static
                if static:
                    current['static_annotation'] = control.get('static_annotation')
                if not notes and not (readable and (node.get('specification') or node.get('declared_metadata', {}).get('technical_annotation'))):
                    errors.append('control lacks native annotation: ' + cid)
                if readable:
                    current['specification'] = node.get('specification')
                    current['technical_annotation'] = node.get('declared_metadata', {}).get('technical_annotation')
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
                    current['main_component']['observed'] = {k: component[k] for k in OBSERVED_FIELDS if k in component}
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
                if valid_component and (notes or readable and semantic_text(node)) and current['bindings']:
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
                    text = semantic_text(nodes[control['id']])
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
                    source_text = (target.get('specification') or {}).get('specification', {})
                    expected_text = source_text.get('title', '') + '\n' + source_text.get('display_text', '') if readable else None
                    if (not target_id or not within(target_id, page_id) or within(target_id, board_id) or
                        not isinstance(label, str) or len(label.strip()) < 6 or
                        (label != expected_text if readable else label not in '\n'.join(annotations(target))) or
                        not note_id or note_id in note_ids or note.get('type') != 'TEXT' or note.get('visible') is not True or
                        parents.get(note_id) != board_id or note.get('fontSize', 0) < 14 or note.get('textAutoResize') != 'HEIGHT' or
                        (note.get('characters') != label if readable else label not in note.get('characters', '')) or not isinstance(link, dict) or link.get('type') != 'NODE' or link.get('value') != target_id):
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
                    for required_id in [screen['id']] + [control['id'] for control in screen['controls'] if not readable or not control['static']]:
                        if required_id not in target_ids:
                            board_errors.append('Design-mode note index misses native target: ' + required_id)
                if readable:
                    frame = board.get('absoluteBoundingBox', {})
                    for screen in screens:
                        art = nodes[screen['id']].get('absoluteBoundingBox', {})
                        if not all(type(rect.get(field)) in (int, float) and math.isfinite(rect[field])
                                   for rect in (frame, art) for field in ('x', 'y', 'width', 'height')):
                            board_errors.append('specification/artwork bounds unavailable')
                            continue
                        if frame['x'] < art['x'] + art['width'] and art['x'] < frame['x'] + frame['width'] and frame['y'] < art['y'] + art['height'] and art['y'] < frame['y'] + frame['height']:
                            board_errors.append('specification board overlaps artwork: ' + screen['id'])
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
        spec = (control.get('specification') or {}).get('specification')
        title = spec['title'] if spec else observed.get('name') or control['id']
        result = ['', '### ' + link(title, control.get('url')), '']
        if spec:
            result += [spec['display_text'], '', '<details><summary>기술 추적 정보</summary>', '',
                       '그래프 원본: `' + text(spec['source_graph_sha256']) + '`',
                       '의미 버전: `' + text(spec['meaning_sha256']) + '`']
        result += ['네이티브 노드: `' + text(control['id']) + '` · 유형: ' + text(observed.get('type', '미관측'))]
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
        if spec:
            result += ['', '</details>']
        return result

    status = '통과' if report['passed'] else '차단'
    lines = ['# 네이티브 화면 명세', '', '검증 상태: ' + status, '',
             '제공된 네이티브 읽기 자료를 기대 계약과 대조했습니다. 이 검증은 자료의 출처 자체를 인증하지 않습니다.',
             '레이아웃·반응·주석 원문·변수 모드와 별칭의 세부 값은 screen-spec.json과 report.json에 보존됩니다.', '']
    lines += ['- 차단 사유: ' + text(error) for error in report['errors']]
    for screen in report['screens']:
        observed = screen['observed']
        spec = (screen.get('specification') or {}).get('specification')
        lines += ['', '## ' + link(spec['title'] if spec else observed.get('name') or screen['id'], screen.get('url')), '']
        if spec:
            lines += [spec['display_text'], '', '<details><summary>기술 추적 정보</summary>', '',
                      '그래프 원본: `' + text(spec['source_graph_sha256']) + '`',
                      '의미 버전: `' + text(spec['meaning_sha256']) + '`']
        lines += ['화면 ID: `' + text(screen['id']) + '`',
                  '크기: ' + text(observed.get('width', '미관측')) + ' × ' + text(observed.get('height', '미관측')) + ' px',
                  '', '화면 설명:']
        lines += notes(screen['native_annotations'])
        if spec:
            lines += ['', '</details>']
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


def component_markdown(report):
    scope = report['component_scope']
    lines = ['# 오프라인 CTA 구성요소 인계', '', '검증 상태: 그래프·네이티브 getter·웹 증명 일치', '',
        '범위: 기존 페이지의 재사용 CTA 구성요소. 앱 전체 화면이나 서버 동작을 검증하지 않습니다.', '',
        f"- Graph key: `{scope['component_id']}`",
        f"- Native frame: [{scope['frame']['name']}]({scope['frame']['url']}) · `{scope['frame']['id']}`",
        f"- Local main: [{scope['main']['key']}]({scope['main']['url']}) · `{scope['main']['id']}`"]
    for instance in scope['instances']:
        lines.append(f"- Instance: [{instance['key']}]({instance['url']}) · `{instance['id']}` · `{instance['label'].get('characters', '미관측')}`")
    proof = scope.get('web_proof') or {}
    lines += ['', '## 연결된 웹 증명', '',
        f"- 관측 시각: `{proof.get('observed_at', '미관측')}`",
        f"- URL: `{proof.get('url', '미관측')}`",
        f"- CSS module SHA-256: `{proof.get('web_module_sha256', 'pairing 참조')}`",
        '- 화면 동작과 서버 수용 조건은 이 구성요소 인계 범위에 포함하지 않습니다.', '']
    planning = scope.get('planning_context')
    if planning:
        lines += ['## G2 정책 영향 기록', '',
            f"- 정책: `{planning['policy_id']}` · 기록 freshness: **{planning['freshness']}**",
            f"- G2 Graph SHA-256: `{planning['source_graph_sha256']}`",
            f"- Decision: `{planning.get('review_decision') or 'pending'}`",
            '- Acceptance: ' + ', '.join(f"`{row['id']}` ({row['status']})" for row in planning['acceptance']),
            '- Tests: ' + ', '.join(f"`{row['id']}` ({row['status']})" for row in planning['tests']), '']
    lines += ['## 동기화된 디자인 필드', ''] + [
        f"- `{row['field']}` → `{row['token_key']}`: **{row['status']}**" for row in scope.get('sync_fields', [])]
    copy = scope.get('text_comparison')
    if copy:
        lines += ['', '## 문구 비교', '',
            f"- 상태: **{copy['status']}**. Figma 문구는 native getter이고 웹 문구는 `{copy.get('source', '미관측')}` 템플릿 원문입니다.",
            '- Browser proof는 computed background color만 검사하며 웹 문구와 native 문구의 일치를 주장하지 않습니다.',
            '- Figma: ' + ', '.join(f"{key}=`{value}`" for key, value in copy['native_actual_labels'].items()),
            '- 템플릿: ' + ', '.join(f"{key}=`{value}`" for key, value in copy['template_branch_labels'].items()), '']
    return '\n'.join(lines)


def offline_html(pack):
    """Render the supplied handoff JSON without network or local service access."""
    payload = json.dumps(pack, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    title = html.escape('Figma Flow 오프라인 핸드오프')
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font:15px/1.55 system-ui,sans-serif;margin:0;background:#f4f2ef;color:#211f1c}}main{{max-width:1000px;margin:0 auto;padding:32px 20px}}
header,section,article{{background:white;border:1px solid #dedbd6;border-radius:12px;padding:20px;margin:16px 0}}
h1{{font-size:26px;margin:0 0 8px}}h2{{font-size:19px;margin:0 0 12px}}h3{{font-size:16px;margin:18px 0 8px}}
.meta{{color:#625e58;font-size:13px;overflow-wrap:anywhere}}.blocked{{color:#8b271b;font-weight:700}}.passed{{color:#17653b;font-weight:700}}
dl{{display:grid;grid-template-columns:minmax(130px,220px) 1fr;gap:5px 14px}}dt{{color:#625e58}}dd{{margin:0;overflow-wrap:anywhere}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f5f3;padding:12px;border-radius:8px}}a{{color:#174d8c}}
@media(max-width:600px){{main{{padding:18px 12px}}dl{{grid-template-columns:1fr}}}}
</style></head><body><main><header><h1>{title}</h1><div id="status"></div><div class="meta" id="provenance"></div></header><div id="content"></div>
<script type="application/json" id="handoff-data">{payload}</script><script>
const pack=JSON.parse(document.getElementById('handoff-data').textContent), report=pack.report;
const el=(tag,text,cls)=>{{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}};
const status=document.getElementById('status');status.append(el('strong',report.component_scope?(report.passed?'구성요소 범위 통과 · 화면 검증 제외':'구성요소 범위 차단'):(report.passed?'검증 통과':'검증 차단'),report.passed?'passed':'blocked'));
const selected=pack.provenance.selected_scope,selectedLabel=selected.kind==='component'?`${{selected.component_key}} · frame ${{selected.frame_id}} · main ${{selected.main_id}} · instances ${{selected.instance_ids.join(', ')}}`:`screens ${{(selected.screen_ids||[]).join(', ')}}`;
const meta=document.getElementById('provenance');meta.textContent=[`관측 시각: ${{pack.provenance.observed_at||'미관측'}}`,`파일: ${{pack.provenance.file_key||'미관측'}}`,`페이지: ${{pack.provenance.page_id||'미관측'}}`,`작업 revision: ${{pack.provenance.revision||'미관측'}} (${{pack.provenance.revision_status}})`,`읽기 범위: ${{pack.provenance.scope}}`,`전달 범위: ${{selectedLabel}}`,`coverage: ${{pack.provenance.coverage}}`,`Graph SHA-256: ${{pack.provenance.graph_sha256||'미제공'}} (${{pack.provenance.graph_sha256_status}})`,`Readback SHA-256: ${{pack.provenance.readback_sha256}}`,`Contract SHA-256: ${{pack.provenance.contract_sha256||'component scope'}}`,`graph sync: ${{pack.provenance.graph_sync?.status||'not paired'}}`,`오프라인 스냅샷입니다. 이후 변경은 새 pairing과 새 팩으로 확인해야 합니다.`].join(' · ');
const root=document.getElementById('content');if(report.errors.length){{const s=el('section');s.append(el('h2','확인할 항목'));for(const error of report.errors)s.append(el('p',error));root.append(s)}}
const assetSection=el('section');assetSection.append(el('h2','에셋과 제외 범위'));for(const item of pack.provenance.assets.excluded)assetSection.append(el('p',`${{item.sha256}}: ${{item.reason}}`));if(!pack.provenance.assets.excluded.length)assetSection.append(el('p','포함하거나 관측된 래스터 에셋이 없습니다.'));for(const item of pack.provenance.omissions)assetSection.append(el('p',`제외: ${{item}}`));root.append(assetSection);
if(report.component_scope){{const c=report.component_scope,s=el('section');s.append(el('h2',`구성요소 · ${{c.component_id}}`));
for(const node of [c.frame,c.main,...c.instances]){{const row=el('article'),link=el('a');link.href=node.url;link.rel='noreferrer';link.textContent=`${{node.name||node.key}} · ${{node.id}}`;row.append(link);if(node.label?.characters)row.append(el('p',`실제 문구: ${{node.label.characters}}`));const details=el('details'),summary=el('summary','실제 getter의 크기·스타일·바인딩');details.open=true;details.append(summary,el('pre',JSON.stringify(node.observed,null,2)));row.append(details);s.append(row)}}
const sync=el('article');sync.append(el('h3','Pairing이 동기화한 디자인 필드'));for(const field of c.sync_fields){{sync.append(el('p',`${{field.field}} · ${{field.token_key}} · ${{field.status}}`));sync.append(el('pre',JSON.stringify({{native:field.native_getter,web:field.browser_computed}},null,2)))}}s.append(sync);
if(c.text_comparison){{const copy=el('article');copy.append(el('h3',`문구 비교 · ${{c.text_comparison.status}}`));copy.append(el('p','Figma 값은 실제 native text getter입니다. 웹 문구는 템플릿의 조건부 branch 원문입니다. Browser proof는 문구를 검사하지 않았습니다.'));copy.append(el('pre',JSON.stringify({{native_actual_labels:c.text_comparison.native_actual_labels,template_branch_labels:c.text_comparison.template_branch_labels,source:c.text_comparison.source,source_sha256:c.text_comparison.source_sha256}},null,2)));s.append(copy)}}
const context=el('article');context.append(el('h3','그래프 문맥 · 그래프 작성 정보'));context.append(el('p',c.graph_context.status));if(c.graph_context.screen)context.append(el('p',`화면: ${{c.graph_context.screen.title}} · ${{c.graph_context.screen.status}} · ${{c.graph_context.screen.id}}`));if(c.graph_context.action)context.append(el('p',`행동: ${{c.graph_context.action.title}} · ${{c.graph_context.action.status}} · ${{c.graph_context.action.web_method}} ${{c.graph_context.action.web_href}}`));context.append(el('p',c.coverage.application_screen));context.append(el('p',`인수 조건: ${{c.coverage.acceptance_conditions}}`));s.append(context);
if(c.web_proof){{const proof=el('article');proof.append(el('h3','브라우저 computed-style 증명'));proof.append(el('p',`관측: ${{c.web_proof.observed_at}} · ${{c.web_proof.url}}`));proof.append(el('p',`web module SHA-256: ${{c.web_proof.web_module_sha256}}`));proof.append(el('pre',JSON.stringify(c.web_proof.components,null,2)));s.append(proof)}}root.append(s)}}
if(report.component_scope?.planning_context){{const p=report.component_scope.planning_context,section=el('section');section.append(el('h2',`G2 정책 영향 기록 · ${{p.policy_id}} · ${{p.freshness}}`));section.append(el('p',`G2 source graph SHA-256: ${{p.source_graph_sha256}}`));section.append(el('p',`Review decision: ${{p.review_decision||'pending'}}`));section.append(el('p',`Direct screens: ${{p.direct_screens.map(row=>row.id+' · '+row.title).join(', ')}}`));section.append(el('p',`Acceptance: ${{p.acceptance.map(row=>row.id+' · '+row.status).join(', ')}}`));section.append(el('p',`Tests: ${{p.tests.map(row=>row.id+' · '+row.status).join(', ')}}`));section.append(el('p',`G2 report SHA-256: ${{p.report_sha256}}`));root.append(section)}}
if(!report.component_scope)for(const screen of report.screens){{const s=el('section'), title=el('h2',screen.observed.name||screen.id);let screenTitle=title;if(screen.url){{screenTitle=el('a',title.textContent);screenTitle.href=screen.url;screenTitle.rel='noreferrer'}}s.append(screenTitle);
const facts=el('dl');for(const [label,value] of [['노드 ID',screen.id],['크기',`${{screen.observed.width??'미관측'}} × ${{screen.observed.height??'미관측'}} px`],['Figma 링크',screen.url||'미제공']]){{facts.append(el('dt',label),el('dd',value))}}s.append(facts);
const layoutFields=['absoluteBoundingBox','constraints','layoutMode','primaryAxisSizingMode','counterAxisSizingMode','layoutSizingHorizontal','layoutSizingVertical','paddingTop','paddingRight','paddingBottom','paddingLeft','itemSpacing','clipsContent','fills','strokes','boundVariables'];
for(const control of screen.controls){{const a=el('article'), heading=el('h3',control.specification?.specification?.title||control.observed.name||control.id);let controlTitle=heading;if(control.url){{controlTitle=el('a',heading.textContent);controlTitle.href=control.url;controlTitle.rel='noreferrer'}}a.append(controlTitle);const rows=[['노드 ID',control.id],['유형',control.observed.type||'미관측'],['인스턴스 main',control.main_component?.id||'해당 없음'],['크기',`${{control.observed.width??'미관측'}} × ${{control.observed.height??'미관측'}} px`]];for(const [label,value] of rows)a.append(el('p',`${{label}}: ${{value}}`));for(const binding of control.bindings||[])a.append(el('p',`토큰 ${{binding.variable?.name||binding.variable_id||'미관측'}} → ${{binding.property}}`));for(const note of control.native_annotations||[])a.append(el('p',note));const observed=Object.fromEntries(layoutFields.filter(key=>key in control.observed).map(key=>[key,control.observed[key]]));if(Object.keys(observed).length){{const details=el('details'), summary=el('summary','실제 getter의 레이아웃·스타일 제약');details.append(summary,el('pre',JSON.stringify(observed,null,2)));a.append(details)}}s.append(a)}}root.append(s)}}
if(!report.component_scope&&!report.screens.length)root.append(el('p','읽을 수 있는 화면 근거가 없습니다.'));
</script></main></body></html>\n'''


def component_scope_report(readback, graph_path, pairing_path, component_key, planning_report_path=None):
    """Build a component-only report from actual native nodes and the current graph pairing."""
    import graph_sync

    graph = graph_sync.load_graph(graph_path)
    pairing = json.loads(Path(pairing_path).read_bytes())
    graph_sync.check_pairing(graph, pairing)
    paired_tokens = _pairing_tokens(pairing)
    if readback.get('schema') != 'figma-flow-graph-native-discovery-v1' or readback.get('allowed_page_ids') != [readback.get('pageId')]:
        raise ValueError('CTA handoff requires a full selected-page native discovery')
    if readback.get('fileKey') != pairing.get('plan', {}).get('file_key') or readback.get('pageId') != pairing.get('plan', {}).get('page_id'):
        raise ValueError('CTA discovery differs from the current graph pairing file/page')
    declaration = graph.get('design_system', {}).get('components', {}).get(component_key)
    if not declaration:
        raise ValueError('Selected component key is absent from the current graph')
    planned = [row for row in pairing['plan']['components'] if row.get('id') == component_key]
    if len(planned) != 1 or set(declaration['properties']) != {'backgroundColor'}:
        raise ValueError('CTA component requires exactly one current paired backgroundColor property')
    component = planned[0]
    if len(component['main_keys']) != 1 or len(component['instance_keys']) != 2:
        raise ValueError('Starter CTA handoff requires one actual local main and two observed instances')
    nodes, parents = normalize(readback)
    main_id = component['main_keys'][0]
    main = nodes.get(main_id)
    if not main or main.get('type') != 'COMPONENT' or main.get('semanticKey') != declaration['native']['mainKeys'][0]:
        raise ValueError('Paired CTA local main getter is missing or changed')
    frame_id = parents.get(main_id)
    frame = nodes.get(frame_id, {})
    if frame.get('type') != 'FRAME' or frame.get('visible') is False:
        raise ValueError('Selected CTA main must sit inside an observed visible workbench frame')
    instances = []
    for key, identity in zip(declaration['native']['instanceKeys'], component['instance_keys']):
        node = nodes.get(identity)
        if (not node or node.get('type') != 'INSTANCE' or parents.get(identity) != frame_id or
                node.get('semanticKey') != key or node.get('mainComponentId', node.get('main_component_id')) != main_id):
            raise ValueError('Paired CTA instance is missing, misplaced, or detached from the local main: ' + key)
        text_rows = [candidate for candidate in nodes.values() if parents.get(candidate['id']) == identity and candidate.get('type') == 'TEXT']
        if len(text_rows) != 1:
            raise ValueError('CTA instance requires one observed visible text layer: ' + key)
        instances.append({'id': identity, 'key': key, 'main_component_id': main_id,
            'url': _figma_node_url(readback['fileKey'], identity),
            'observed': {field: node[field] for field in OBSERVED_FIELDS if field in node},
            'label': {field: text_rows[0].get(field) for field in ('id', 'characters', 'fontName', 'nativeFontFamily', 'fontSize') if field in text_rows[0]}})
    main_texts = [node for node in nodes.values() if parents.get(node['id']) == main_id and node.get('type') == 'TEXT']
    if len(main_texts) != 1:
        raise ValueError('CTA main requires one observed text layer')
    main_scope = {'id': main_id, 'key': declaration['native']['mainKeys'][0], 'type': 'COMPONENT',
        'url': _figma_node_url(readback['fileKey'], main_id),
        'observed': {field: main[field] for field in OBSERVED_FIELDS if field in main},
        'label': {field: main_texts[0].get(field) for field in ('id', 'characters', 'fontName', 'nativeFontFamily', 'fontSize') if field in main_texts[0]}}
    collection = next((value for value in readback.get('collections', []) if value.get('id') == pairing['plan']['collection_id']), None)
    if not collection:
        raise ValueError('Paired native color collection is missing from full discovery')
    variable_by_id = {row['id']: row for row in readback.get('variables', [])}
    def resolve_variable(identity, mode_id, seen=()):
        if identity in seen or identity not in variable_by_id:
            raise ValueError('Missing or cyclic actual graph variable alias')
        variable = variable_by_id[identity]
        value = variable.get('valuesByMode', {}).get(mode_id)
        if isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS':
            resolved, chain = resolve_variable(value.get('id'), mode_id, seen + (identity,))
            return resolved, [identity] + chain
        if not scalar(value, variable.get('resolvedType')):
            raise ValueError('Missing or invalid actual native variable value: ' + identity)
        return value, [identity]
    modes = [mode.get('modeId') for mode in collection.get('modes', []) if mode.get('modeId')]
    if len(modes) != 1:
        raise ValueError('Paired CTA collection must have one actual mode')
    mode = modes[0]
    values = []
    for token in paired_tokens:
        variable = variable_by_id.get(token.get('variable_id'))
        if not variable or variable.get('variableCollectionId') != collection['id']:
            raise ValueError('Paired CTA variable is missing from its actual collection')
        value, chain = resolve_variable(variable['id'], mode)
        values.append({**token, 'resolved_modes': {mode: {'value': value, 'alias_chain': chain}},
            'name': variable['name'], 'resolvedType': variable['resolvedType'], 'id': variable['id']})
    token = next((value for value in values if value['key'] == declaration['properties']['backgroundColor']), None)
    if not token:
        raise ValueError('Paired CTA semantic background token is not in the current receipt')
    main_binding = binding_at(main, 'fills.0.color')
    if not isinstance(main_binding, dict) or main_binding.get('id') != token['variable_id']:
        raise ValueError('Observed CTA main fill is not bound to its paired semantic graph token')
    graph_nodes = {node['id']: node for node in graph.get('nodes', []) if isinstance(node, dict) and isinstance(node.get('id'), str)}
    action_key = declaration['native']['instanceKeys'][0]
    action = next((node for node in graph_nodes.values() if node.get('web_action') == action_key), None)
    screen = graph_nodes.get(action.get('source_screen')) if action else None
    action_annotation = action.get('annotation', {}) if action else {}
    web_proof = pairing.get('web_proof')
    browser_component = next((row for row in (web_proof or {}).get('components', []) if row.get('id') == component_key), {})
    native_color = main.get('fills', [{}])[0].get('color')
    browser_color = browser_component.get('properties', {}).get('backgroundColor')
    sync_fields = [{'field': 'backgroundColor', 'token_key': declaration['properties']['backgroundColor'],
        'native_getter': native_color, 'browser_computed': browser_color,
        'status': 'matched' if native_color and browser_color and graph_sync.same_value(native_color, browser_color) else 'mismatch'}]
    text_comparison = _little_hands_template_copy(action, instances) if component_key == 'button.bookingCTA' else None
    planning_context = None
    if planning_report_path:
        planning_bytes = Path(planning_report_path).read_bytes()
        planning = json.loads(planning_bytes)
        if (planning.get('schema') != 1 or not isinstance(planning.get('policyId'), str) or
                not isinstance(planning.get('currentGraphSha256'), str) or
                not isinstance(planning.get('acceptance'), list) or not isinstance(planning.get('tests'), list)):
            raise ValueError('Expected the evidence-backed G2 policy impact report')
        planning_context = {'schema': planning['schema'], 'policy_id': planning['policyId'],
            'source_graph_sha256': planning['currentGraphSha256'],
            'freshness': 'current' if planning['currentGraphSha256'] == graph.source_sha256 else 'stale',
            'report_sha256': hashlib.sha256(planning_bytes).hexdigest(),
            'review_decision': planning.get('reviewDecision'),
            'direct_screens': [{'id': row.get('id'), 'title': row.get('title'), 'relation': row.get('relation')}
                for row in planning.get('directScreens', [])],
            'acceptance': [{'id': row.get('id'), 'title': row.get('title'), 'status': row.get('status')}
                for row in planning['acceptance']],
            'tests': [{'id': row.get('id'), 'title': row.get('title'), 'status': row.get('status')}
                for row in planning['tests']]}
    return {'schema': 'figma-flow-cta-component-handoff-v1', 'status': 'passed', 'passed': True,
        'errors': [], 'collection': collection, 'variables': values, 'screens': [],
        'component_scope': {'component_id': component_key, 'graph_properties': declaration['properties'],
            'graph_native_mapping': declaration['native'], 'frame': {'id': frame_id,
                'semantic_key': frame.get('semanticKey'), 'name': frame.get('name'),
                'url': _figma_node_url(readback['fileKey'], frame_id),
                'observed': {field: frame[field] for field in OBSERVED_FIELDS if field in frame}},
            'main': main_scope, 'instances': instances, 'sync_fields': sync_fields,
            'text_comparison': text_comparison,
            'graph_context': {'source': 'canonical graph nodes', 'status': 'graph-authored; not native screen evidence',
                'screen': {'id': screen.get('id'), 'title': screen.get('title'), 'status': screen.get('status')} if screen else None,
                'action': {'id': action.get('id'), 'title': action.get('title'), 'status': action.get('status'),
                    'web_action': action.get('web_action'), 'web_method': action.get('web_method') or action_annotation.get('web_method'),
                    'web_href': action.get('web_href') or action_annotation.get('web_href'),
                    'source_selector': action_annotation.get('source_selector')} if action else None},
            'web_proof': {**web_proof, 'web_module_sha256': pairing.get('web_module_sha256')} if isinstance(web_proof, dict) else None,
            'planning_context': planning_context,
            'coverage': {'native': 'selected reusable CTA component on one fully read page',
                'application_screen': 'not included', 'acceptance_conditions': 'not included'}}}


def little_hands_source_labels(action, keys):
    if not isinstance(action, dict) or not isinstance(action.get('source'), str):
        return {'status': 'unavailable', 'reason': 'Approved graph action has no source path'}
    repository = Path(__file__).resolve().parents[1]
    source_path = (repository / 'apps/little-hands/design' / action['source']).resolve()
    allowed_root = (repository / 'apps/little-hands/templates').resolve()
    try:
        source_path.relative_to(allowed_root)
    except ValueError:
        return {'status': 'unavailable', 'reason': 'Graph source path is outside the approved Little Hands template tree'}
    if not source_path.is_file():
        return {'status': 'unavailable', 'reason': 'Graph source template is unavailable'}
    raw = source_path.read_bytes()
    template = raw.decode('utf-8')
    def branch_copy(key):
        match = re.search(r'<(?P<tag>button|a)\b(?=[^>]*\bdata-native-key="' + re.escape(key) + r'")[^>]*>(?P<body>.*?)</(?P=tag)>', template, re.S)
        if not match:
            return None
        return html.unescape(re.sub(r'<[^>]+>', '', match['body'])).strip()
    return {'source': str(source_path.relative_to(repository)), 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'template_branch_labels': {key: branch_copy(key) for key in keys}}


def _little_hands_template_copy(action, instances):
    actual = {row['key']: row['label'].get('characters') for row in instances}
    source = little_hands_source_labels(action, actual)
    if 'template_branch_labels' not in source:
        return source
    source_copy = source['template_branch_labels']
    compared = [key for key in actual if source_copy.get(key) is not None]
    differs = any(source_copy[key] != actual[key] for key in compared)
    return {**source,
        'status': 'differs' if differs else 'matched' if compared and len(compared) == len(actual) else 'unavailable',
        'native_actual_labels': actual, 'template_branch_labels': source_copy,
        'runtime_proof': 'Template source only; browser evidence confirms computed backgroundColor, not rendered copy.'}


def _figma_node_url(file_key, node_id):
    return f"https://www.figma.com/design/{file_key}?node-id={str(node_id).replace(':', '-')}"


def _pairing_tokens(pairing):
    raw = pairing.get('tokens', [])
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [{**row, 'resolved': raw.get(row.get('key'))} for row in pairing.get('plan', {}).get('tokens', [])]
    raise ValueError('Graph pairing token evidence has an unsupported shape')


def verify_graph_sync_handoff(readback, report, graph_path, pairing_path, web_module_path):
    """Pin the pack to a current graph_sync pairing and its exact web module."""
    import tempfile
    import graph_sync
    from graph_design_system import emit_web_module

    graph_file, pairing_file, web_file = map(Path, (graph_path, pairing_path, web_module_path))
    graph = graph_sync.load_graph(graph_file)
    pairing_bytes = pairing_file.read_bytes()
    pairing = json.loads(pairing_bytes)
    paired_tokens = _pairing_tokens(pairing)
    resolved = graph_sync.check_pairing(graph, pairing)
    if pairing.get('graph_sha256') != resolved.get('graphSha256'):
        raise ValueError('Graph changed after the native/web pairing; obtain a fresh pairing')
    if any(component.get('web', {}).get('selector') for component in graph.get('design_system', {}).get('components', {}).values()):
        if not pairing.get('web_proof') or not graph_sync.verify_web_proof(graph, pairing['web_proof']):
            raise ValueError('Current browser computed-style proof is missing or stale')
    if readback.get('fileKey') != pairing.get('plan', {}).get('file_key') or readback.get('pageId') != pairing.get('plan', {}).get('page_id'):
        raise ValueError('Native handoff readback is outside the paired file or page')
    full_discovery = (readback.get('schema') == 'figma-flow-graph-native-discovery-v1' and
                      readback.get('allowed_page_ids') == [readback.get('pageId')])
    full_export = (readback.get('format') == 'figma-flow-readback-v1' and len(readback.get('pages', [])) == 1 and
                   readback['pages'][0].get('id') == readback.get('pageId'))
    if not (full_discovery or full_export):
        raise ValueError('Offline handoff requires an explicit full-page native readback')
    current_web = web_file.read_bytes()
    current_web_sha = hashlib.sha256(current_web).hexdigest()
    if current_web_sha != pairing.get('web_module_sha256'):
        raise ValueError('Web module changed after pairing; regenerate proof and pairing')
    with tempfile.TemporaryDirectory() as temporary:
        generated = Path(temporary) / 'tokens.mjs'
        emit_web_module(graph_file, generated, expected_sha256=resolved['graphSha256'])
        if generated.read_bytes() != current_web:
            raise ValueError('Current web module differs from the paired graph projection')
    if report.get('collection', {}).get('id') != pairing.get('plan', {}).get('collection_id'):
        raise ValueError('Native handoff evidence uses a different variable collection than the pairing')
    variables = {row.get('id'): row for row in report.get('variables', [])}
    modes = [row.get('modeId') for row in report.get('collection', {}).get('modes', []) if row.get('modeId')]
    if len(modes) != 1:
        raise ValueError('Offline handoff requires the paired single-mode token collection')
    mode = modes[0]
    for token in paired_tokens:
        observed = variables.get(token.get('variable_id'))
        if (not observed or observed.get('name') != token.get('variable_name') or
                observed.get('resolvedType') != token.get('type') or
                observed.get('resolved_modes', {}).get(mode, {}).get('value') != token.get('resolved')):
            raise ValueError('Native handoff getter differs from the paired token value: ' + str(token.get('key')))
    expected_mains = {node for component in pairing.get('plan', {}).get('components', []) for node in component.get('main_keys', [])}
    expected_instances = {node for component in pairing.get('plan', {}).get('components', []) for node in component.get('instance_keys', [])}
    component_scope = report.get('component_scope')
    if component_scope:
        actual_mains = {component_scope.get('main', {}).get('id')}
        actual_instances = {instance.get('id') for instance in component_scope.get('instances', [])}
    else:
        actual_mains = {control.get('main_component', {}).get('id') for screen in report.get('screens', []) for control in screen.get('controls', [])}
        actual_instances = {control.get('id') for screen in report.get('screens', []) for control in screen.get('controls', [])}
    if actual_mains != expected_mains or actual_instances != expected_instances:
        raise ValueError('Offline handoff screen scope differs from the paired main/instance set')
    paired_tokens_by_key = {token.get('key'): token for token in paired_tokens}
    for component in pairing.get('plan', {}).get('components', []):
        properties = component.get('properties', {})
        if set(properties) != {'backgroundColor'}:
            raise ValueError('Offline Starter handoff currently admits only the paired booking CTA background field')
        token = paired_tokens_by_key.get(properties['backgroundColor'])
        if not token:
            raise ValueError('Paired CTA graph token is missing')
        token_value = token['resolved']
        if component_scope:
            consumers = [(component_scope['main']['id'], component_scope['main']['observed'])]
            consumers.extend((instance['id'], instance['observed']) for instance in component_scope['instances'])
        else:
            controls = {control.get('id'): control for screen in report.get('screens', []) for control in screen.get('controls', [])}
            main_control = next((row for row in controls.values() if row.get('main_component', {}).get('id') in component.get('main_keys', [])), None)
            if not main_control:
                raise ValueError('Paired CTA main getter is absent from the handoff')
            consumers = [(component['main_keys'][0], main_control.get('main_component', {}).get('observed', {}))]
            consumers.extend((identity, controls[identity]['observed']) for identity in component.get('instance_keys', []) if identity in controls)
        if len(consumers) != 1 + len(component.get('instance_keys', [])):
            raise ValueError('Paired CTA instance getter is absent from the handoff')
        for identity, observed in consumers:
            binding = binding_at(observed, 'fills.0.color')
            paints = observed.get('fills')
            if (not isinstance(paints, list) or len(paints) != 1 or paints[0].get('type') != 'SOLID' or
                    not isinstance(binding, dict) or binding.get('type') != 'VARIABLE_ALIAS' or binding.get('id') != token['variable_id'] or
                    not graph_sync.same_value({**paints[0]['color'], 'a': 1}, {**token_value, 'a': 1})):
                raise ValueError('Paired CTA main/instance getter differs from its graph token: ' + identity)
    return {'status': 'paired-current-at-export', 'graph_sha256': resolved['graphSha256'],
            'pairing_sha256': hashlib.sha256(pairing_bytes).hexdigest(), 'web_module_sha256': current_web_sha,
            'file_key': pairing['plan']['file_key'], 'page_id': pairing['plan']['page_id'],
            'token_count': len(paired_tokens), 'main_ids': sorted(expected_mains),
            'instance_ids': sorted(expected_instances)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readback', required=True)
    parser.add_argument('--contract', help='native screen contract for screen-level handoff')
    parser.add_argument('--component-key', help='export the graph-paired component-only scope, with no screen claims')
    parser.add_argument('--planning-report', help='optional G2 policy-impact report; stale graph versions stay labeled stale')
    parser.add_argument('--page-id')
    parser.add_argument('--graph-sha256', help='optional canonical graph SHA-256 recorded by the caller')
    parser.add_argument('--revision', help='optional prepared-work revision recorded by the caller')
    parser.add_argument('--offline-pack', action='store_true', help='write handoff.html and handoff.json for offline recipients')
    parser.add_argument('--confirm-included-text', action='store_true', help='confirm selected text and native annotations may be included')
    parser.add_argument('--graph-sync-graph', help='canonical graph paired with the native and web evidence')
    parser.add_argument('--graph-sync-pairing', help='current graph_sync pairing receipt')
    parser.add_argument('--web-module', help='exact generated web module named by the pairing receipt')
    parser.add_argument('--out', required=True, help='new output directory; existing evidence is never overwritten')
    args = parser.parse_args()
    if args.confirm_included_text and not args.offline_pack:
        parser.error('--confirm-included-text requires --offline-pack')
    if args.offline_pack and not args.confirm_included_text:
        parser.error('--offline-pack requires explicit --confirm-included-text')
    paired_args = (args.graph_sync_graph, args.graph_sync_pairing, args.web_module)
    if args.offline_pack and not all(paired_args):
        parser.error('--offline-pack requires --graph-sync-graph, --graph-sync-pairing, and --web-module')
    if not args.offline_pack and any(paired_args):
        parser.error('graph_sync pairing inputs require --offline-pack')
    if args.component_key and not args.offline_pack:
        parser.error('--component-key requires --offline-pack')
    if args.component_key and args.contract:
        parser.error('choose either --component-key or a screen --contract')
    if not args.component_key and not args.contract:
        parser.error('a screen --contract or --component-key is required')
    if args.offline_pack and not args.component_key and not args.contract:
        parser.error('--offline-pack requires a screen contract or --component-key')
    try:
        readback = json.loads(Path(args.readback).read_text())
        expected = json.loads(Path(args.contract).read_text()) if args.contract else None
        report = component_scope_report(readback, args.graph_sync_graph, args.graph_sync_pairing, args.component_key, args.planning_report) if args.component_key else evaluate(readback, expected, args.page_id)
    except (OSError, ValueError) as exc:
        parser.exit(2, 'native handoff blocked: ' + str(exc) + '\n')
    graph_sync_proof = None
    if args.offline_pack:
        if not report['passed']:
            parser.exit(2, 'offline handoff blocked: native evidence does not pass its explicit contract\n')
        try:
            graph_sync_proof = verify_graph_sync_handoff(readback, report, args.graph_sync_graph, args.graph_sync_pairing, args.web_module)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.exit(2, 'offline handoff blocked: ' + str(exc) + '\n')
        readback_bytes = Path(args.readback).read_bytes()
        contract_bytes = Path(args.contract).read_bytes() if args.contract else None
        graph_ssot = readback.get('graphSSOT')
        observed_graph_hash = readback.get('graph_sha256')
        if observed_graph_hash is None and isinstance(graph_ssot, dict):
            observed_graph_hash = graph_ssot.get('graph_sha256')
        for graph_hash in (args.graph_sha256, observed_graph_hash):
            if graph_hash is not None and (not isinstance(graph_hash, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', graph_hash)):
                parser.error('Graph SHA values must be 64 hexadecimal characters')
        if graph_sync_proof and observed_graph_hash and graph_sync_proof['graph_sha256'] != observed_graph_hash:
            parser.error('Graph sync pairing differs from the graph SHA observed in native readback')
        if args.graph_sha256 and observed_graph_hash and args.graph_sha256 != observed_graph_hash:
            parser.error('Supplied graph SHA differs from the graph SHA observed in native readback')
        observed_revision = readback.get('revision') or readback.get('work_revision')
        if args.revision and observed_revision and args.revision != observed_revision:
            parser.error('Supplied revision differs from the revision observed in native readback')
        if graph_sync_proof:
            if args.graph_sha256 and args.graph_sha256 != graph_sync_proof['graph_sha256']:
                parser.error('Supplied graph SHA differs from the current graph_sync pairing')
            graph_status = graph_sync_proof['status']
            observed_graph_hash = graph_sync_proof['graph_sha256']
        elif args.graph_sha256 is not None and not observed_graph_hash:
            graph_status = 'claimed-unverified'
        else:
            graph_status = 'observed' if observed_graph_hash else 'unavailable'
        if args.revision is not None and not observed_revision:
            revision_status = 'claimed-unverified'
        else:
            revision_status = 'observed' if observed_revision else 'unavailable'
        page_id = args.page_id or readback.get('pageId')
        if readback.get('schema') == 'figma-flow-graph-native-discovery-v1' and readback.get('allowed_page_ids') == [page_id]:
            evidence_scope, evidence_coverage = 'full selected page', 'all native nodes on the admitted page'
        elif readback.get('format') == 'figma-flow-readback-v1' and len(readback.get('pages', [])) == 1:
            evidence_scope, evidence_coverage = 'single exported page', 'all nodes in the exported page snapshot'
        else:
            evidence_scope = readback.get('scope') or readback.get('evidence_scope') or 'scope not declared'
            evidence_coverage = readback.get('coverage') or readback.get('readback_coverage') or 'coverage not declared'
        provenance = {
            'observed_at': readback.get('exported_at') or readback.get('observed_at'),
            'file_key': readback.get('fileKey') or readback.get('file_key'),
            'page_id': page_id,
            'revision': observed_revision,
            'revision_claim': args.revision,
            'revision_status': revision_status,
            'graph_sha256': observed_graph_hash,
            'graph_sha256_claim': args.graph_sha256,
            'graph_sha256_status': graph_status,
            'readback_sha256': hashlib.sha256(readback_bytes).hexdigest(),
            'contract_sha256': hashlib.sha256(contract_bytes).hexdigest() if contract_bytes else None,
            'contract_source': 'graph-sync component scope' if args.component_key else 'explicit native screen contract',
            'scope': evidence_scope,
            'coverage': evidence_coverage,
            'selected_scope': ({'kind': 'component', 'component_key': report['component_scope']['component_id'],
                'frame_id': report['component_scope']['frame']['id'], 'main_id': report['component_scope']['main']['id'],
                'instance_ids': [item['id'] for item in report['component_scope']['instances']]}
                if report.get('component_scope') else {'kind': 'screens', 'screen_ids': [screen['id'] for screen in report.get('screens', [])]}),
            'graph_sync': graph_sync_proof,
            'assets': {'included': [], 'excluded': [
                {'sha256': image_hash, 'reason': 'Image bytes are not embedded in this offline pack'}
                for image_hash in sorted(set(readback.get('rasterImages', {})) |
                    {node.get('rasterImageRef') or (paint.get('imageHash') if isinstance(paint, dict) else None)
                     for node in readback.get('nodes', []) for paint in node.get('fills', [])}) if image_hash
            ]},
            'omissions': ['Private plugin data', 'Unsupported or unavailable native fields', 'Raster image bytes'],
        }
    output = Path(args.out)
    try:
        output.mkdir(parents=True, exist_ok=False, mode=0o700 if args.offline_pack else 0o755)
    except OSError as exc:
        parser.exit(2, 'new output directory required: ' + str(exc) + '\n')
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    screen_spec = {'schema': report['schema'], 'status': report['status'], 'screens': report.get('screens', [])}
    if report.get('component_scope'):
        screen_spec['component_scope'] = report['component_scope']
    (output / 'screen-spec.json').write_text(json.dumps(screen_spec, ensure_ascii=False, indent=2) + '\n')
    (output / 'screen-spec.md').write_text(component_markdown(report) if report.get('component_scope') else markdown(report))
    if args.offline_pack:
        pack = {'format_version': 'figma-flow-offline-handoff-v1', 'provenance': provenance, 'report': report}
        (output / 'handoff.json').write_text(json.dumps(pack, ensure_ascii=False, indent=2) + '\n')
        (output / 'handoff.html').write_text(offline_html(pack), encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
