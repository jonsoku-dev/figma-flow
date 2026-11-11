"""Pure audit of supplied exploratory native roles, palette and concrete uses.

`audit_draft_foundations(readback, candidate)` consumes the same candidate row as
figma_draft's packet (id, graph, fonts and optional state_layouts). It performs no
I/O or admission. Every declared role must match its typed native contract on intended fields;
auxiliary or partial projections never replace missing canonical bindings. Raster references are never native
component, typography, interaction, generated-asset or production evidence.
"""
import math
import re

NUMERIC_FIELDS = ('fontSize', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
                  'itemSpacing', 'cornerRadius', 'topLeftRadius', 'topRightRadius',
                  'bottomLeftRadius', 'bottomRightRadius')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _alias(value):
    return value.get('id') if isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS' else None


def _color(value):
    if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?', value):
        return {key: int(value[index:index + 2], 16) / 255 for key, index in zip('rgba', (1, 3, 5, 7)) if len(value) >= index + 2} | {'a': int(value[7:9], 16) / 255 if len(value) == 9 else 1}
    return value


def _equal(kind, left, right):
    if kind == 'STRING':
        return isinstance(left, str) and isinstance(right, str) and bool(left) and left == right
    if kind == 'FLOAT':
        return _number(left) and _number(right) and math.isclose(left, right, abs_tol=1e-5)
    if kind == 'COLOR':
        left, right = _color(left), _color(right)
        return isinstance(left, dict) and isinstance(right, dict) and all(
            _number(left.get(key, 1 if key == 'a' else None)) and _number(right.get(key, 1 if key == 'a' else None)) and
            math.isclose(left.get(key, 1), right.get(key, 1), abs_tol=1e-5) for key in 'rgba')
    return False


def audit_draft_foundations(readback, candidate, *, production_packet=None):
    """Recompute actual visible use counts; never trust receipt counters or names alone."""
    failures, observations, uncovered, auxiliary = [], [], [], []
    report = {'passed': False, 'ok': False, 'scope': 'exploratory-only', 'production_admitted': False,
              'evidence': 'supplied-native-readback-not-origin-authentication', 'failures': failures,
              'errors': [], 'roles': observations, 'unobserved_roles': uncovered, 'uses': [],
              'auxiliary_uses': auxiliary, 'role_projections': [], 'palette': {}, 'counts': {}, 'limits': [
                  'Only supplied visible native nodes and their native variable/style records are checked.',
                  'Every declared semantic role and intended native use is required; auxiliary uses do not satisfy them.',
                  'Raster artwork/references are not editable foundations, generated-asset receipts or interaction evidence.',
                  'Font availability, visual composition and rendering require separate runtime review.']}
    def fail(code, subject):
        failures.append({'code': code, 'subject': str(subject)})
    try:
        if not isinstance(readback, dict) or not isinstance(candidate, dict):
            raise ValueError('native readback and packet candidate objects required')
        identity, graph = candidate.get('id'), candidate.get('graph')
        if not isinstance(identity, str) or not identity or not isinstance(graph, dict):
            raise ValueError('candidate id and exact per-candidate graph required')
        if production_packet is None:
            if readback.get('scope') != 'exploratory-only' or readback.get('production_admitted') is True:
                fail('invalid-draft-scope', identity)
        else:
            # figma_draft imports this module, so production schema names are read at call time.
            from figma_draft import PRODUCTION_READBACK, PRODUCTION_SCHEMA
            if (production_packet.get('schema') != PRODUCTION_SCHEMA
                    or production_packet.get('scope') != 'selected-production'
                    or production_packet.get('production_admitted') is not True
                    or readback.get('schema') != PRODUCTION_READBACK
                    or readback.get('scope') != 'selected-production'
                    or readback.get('production_admitted') is not True
                    or any(not production_packet.get(key) or readback.get(key) != production_packet[key]
                           for key in ('sourceSelection', 'production_graph', 'change_request'))):
                fail('invalid-selected-production-scope', identity)
            else:
                report.update(scope='selected-production', production_admitted=True)
        plan = graph.get('design_foundations', {})
        if candidate.get('foundations', plan) != plan:
            fail('candidate-foundations-differ-from-graph', identity)
        roles = plan.get('roles', [])
        if not isinstance(roles, list) or not roles:
            raise ValueError('per-candidate planned foundation roles required')
        from draft_token_plan import native_name
        declarations = []
        for planned in roles:
            native = planned.get('native')
            if native is not None:
                if not isinstance(native, dict):
                    raise ValueError('role.native must be a typed object: ' + planned['token'])
                declarations.append({'token': planned['token'], 'alias': planned.get('alias'), **native})
        if len({native_name(identity, role.get('token')) for role in roles}) != len(roles):
            fail('duplicate-canonical-role-token', identity)
        legacy = any(role['kind'] != 'color' and role.get('native') is None for role in roles)
        if legacy:
            from draft_token_plan import foundation_bindings
            try:
                declarations = foundation_bindings(candidate, graph)
            except (ValueError, KeyError, TypeError) as exc:
                fail('unresolvable-canonical-native-plan', str(exc))
        resolved_specs = {row['token']: row for row in declarations}
        if candidate.get('foundationBindings', []) != declarations:
            fail('compiled-foundation-plan-differs-from-graph', identity)
        scalar_names = {native_name(identity, row['token']) for row in declarations if row.get('type') == 'FLOAT'}
        intended_slots = {(binding.get('key'), binding.get('field')) for row in declarations for binding in row.get('bindings', []) if isinstance(binding, dict)}
        def index(field):
            rows = readback.get(field, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in rows):
                raise ValueError('invalid native ' + field)
            result = {row['id']: row for row in rows}
            if len(result) != len(rows):
                raise ValueError('duplicate native ' + field + ' ids')
            return result
        nodes, variables, collections = index('nodes'), index('variables'), index('collections')
        styles = {}
        for row in readback.get('styles', []) + readback.get('textStyles', []):
            if isinstance(row, dict) and row.get('id'):
                styles[row['id']] = dict(styles.get(row['id'], {}), **row)
        page_id = readback.get('pageId')
        if nodes.get(page_id, {}).get('type') != 'PAGE':
            raise ValueError('actual owning page required')
        palette = readback.get('palettes', {}).get(identity, {})
        library_id = palette.get('libraryId')
        def within(node_id, owner):
            seen = set()
            while node_id in nodes and node_id not in seen:
                if node_id == owner:
                    return True
                seen.add(node_id)
                node_id = nodes[node_id].get('parentId')
            return False
        def visible(node):
            seen = set()
            while node:
                if node['id'] in seen or node.get('visible') is False or node.get('opacity', 1) == 0:
                    return False
                seen.add(node['id'])
                node = nodes.get(node.get('parentId'))
            return True
        def key(node):
            return node.get('semanticKey') or node.get('key') or ''
        def belongs(node):
            current, seen = node, set()
            while current and current['id'] not in seen:
                if key(current).startswith(identity + '.') or current['id'] == library_id:
                    return within(node['id'], page_id)
                seen.add(current['id'])
                current = nodes.get(current.get('parentId'))
            return False
        def owner(node):
            if node.get('type') == 'FRAME':
                return node['id']
            current = nodes.get(node.get('parentId'))
            while current:
                if current.get('type') in ('FRAME', 'COMPONENT_SET'):
                    return current['id']
                current = nodes.get(current.get('parentId'))
            return None
        def resolve(variable_id, node=None, seen=None):
            seen = set() if seen is None else seen
            if variable_id not in variables or variable_id in seen:
                raise ValueError('missing/cyclic native variable ' + str(variable_id))
            variable = variables[variable_id]
            collection = collections.get(variable.get('variableCollectionId'))
            if not collection:
                raise ValueError('variable owning collection unavailable: ' + variable_id)
            mode = (node or {}).get('resolvedVariableModes', {}).get(collection['id'], collection.get('defaultModeId'))
            if not mode or mode not in variable.get('valuesByMode', {}):
                raise ValueError('actual variable mode unavailable: ' + variable_id)
            value = variable['valuesByMode'][mode]
            target = _alias(value)
            if target:
                kind, value = resolve(target, node, seen | {variable_id})
                if kind != variable.get('resolvedType'):
                    raise ValueError('native alias type mismatch: ' + variable_id)
                return kind, value
            kind = variable.get('resolvedType')
            if not _equal(kind, value, value):
                raise ValueError('invalid COLOR/FLOAT/STRING native value: ' + variable_id)
            if kind == 'COLOR' and any(not 0 <= _color(value).get(channel, 1) <= 1 for channel in 'rgba'):
                raise ValueError('native color outside channel range: ' + variable_id)
            return kind, value
        expected_sizes, expected_owners, product_buttons = {}, {}, []
        for viewport, layouts in candidate.get('state_layouts', {}).items():
            for state_id, layout in layouts.items():
                for layer in layout.get('layers', []):
                    expected_owners[f"{identity}.{viewport}.{state_id}.{layer['id']}"] = (f"{identity}.{viewport}.{state_id}", 'FRAME')
                    if layer.get('kind') == 'text':
                        expected_sizes[f"{identity}.{viewport}.{state_id}.{layer['id']}"] = layer
                for button_id, button in layout.get('product_buttons', {}).items():
                    frame_key = f'{identity}.{viewport}.{state_id}'
                    control_key = frame_key + '.' + button_id
                    main_key = f"{identity}.{viewport}.component.{button['variant']}"
                    style = candidate['control_styles'][viewport][button['variant']]
                    expected_owners[control_key] = (frame_key, 'FRAME')
                    expected_owners[control_key + '.label'] = (control_key, 'INSTANCE')
                    expected_sizes[control_key + '.label'] = {'font': style.get('font', 'body'), 'size': style['fontSize']}
                    product_buttons.append((control_key, main_key, frame_key, button))
        for viewport, control_styles in candidate.get('control_styles', {}).items():
            for visual in control_styles:
                main_key = f'{identity}.{viewport}.component.{visual}'
                expected_owners[main_key] = (f'{identity}.{viewport}.component-set', 'COMPONENT_SET')
                expected_owners[main_key + '.label'] = (main_key, 'COMPONENT')
                style = control_styles[visual]
                expected_sizes[main_key + '.label'] = {'font': style.get('font', 'body'), 'size': style['fontSize']}
        actions = {node['id']: node.get('annotation', {}).get('visual_variant') for node in graph.get('nodes', []) if node.get('type') == 'action'}
        for edge in graph.get('draft_prototype', {}).get('bindings', []):
            frame_key = f"{identity}.{edge['viewport']}.{edge['source_state']}"
            control_key = frame_key + '.' + edge['control_id']
            expected_owners[control_key] = (frame_key, 'FRAME')
            expected_owners[control_key + '.label'] = (control_key, 'INSTANCE')
            style = candidate.get('control_styles', {}).get(edge['viewport'], {}).get(actions.get(edge.get('action')))
            if style:
                expected_sizes[control_key + '.label'] = {'font': style.get('font', 'body'), 'size': style['fontSize']}
        for control_key, main_key, frame_key, button in product_buttons:
            def exact(target):
                matches = [node for node in nodes.values() if key(node) == target]
                return matches[0] if len(matches) == 1 else {}
            instance, main, label, frame = (exact(target) for target in (control_key, main_key, control_key + '.label', frame_key))
            component_set = exact(main_key.rsplit('.component.', 1)[0] + '.component-set')
            if (instance.get('type') != 'INSTANCE' or main.get('type') != 'COMPONENT' or
                component_set.get('type') != 'COMPONENT_SET' or main.get('parentId') != component_set.get('id') or
                instance.get('mainComponentId') != main.get('id') or not visible(main) or not belongs(main) or not visible(instance) or
                not belongs(instance) or instance.get('parentId') != frame.get('id') or
                not isinstance(instance.get('reactions'), list) or instance['reactions']):
                fail('invalid-real-product-button', control_key)
            if (label.get('type') != 'TEXT' or label.get('characters') != button['label'] or
                label.get('parentId') != instance.get('id') or not visible(label)):
                fail('missing-real-product-button-label', control_key)
        uses = report['uses']
        for node in nodes.values():
            if not belongs(node) or not visible(node):
                continue
            fields = []
            if node.get('type') == 'TEXT' and node.get('characters') and (not _number(node.get('fontSize')) or node['fontSize'] <= 0):
                fail('missing-observed-font-size', node['id'])
            for field in ('fills', 'strokes'):
                for i, paint in enumerate(node.get(field, []) if isinstance(node.get(field), list) else []):
                    if paint.get('type') == 'SOLID' and paint.get('visible', True) and paint.get('opacity', 1) > 0:
                        fields.append((field, i, paint.get('boundVariables', {}).get('color'), paint.get('color')))
            for field in NUMERIC_FIELDS:
                if 'Radius' in field or field == 'cornerRadius':
                    if node.get('type') == 'COMPONENT_SET' and not any(paint.get('visible', True) and paint.get('opacity', 1) > 0 for paint in node.get('fills', []) + node.get('strokes', [])):
                        continue  # Figma's unpainted set-outline radius is editor chrome, not a rendered role.
                value = node.get(field)
                if _number(value) and value > 0:
                    alias = node.get('boundVariables', {}).get(field)
                    if field == 'fontSize' and (alias is None or alias == []):
                        style = styles.get(node.get('textStyleId'), {})
                        if style.get('fontSize') == value and style.get('fontName') == node.get('fontName'):
                            alias = style.get('boundVariables', {}).get('fontSize')
                    if field == 'cornerRadius' and not alias:
                        corners = ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius')
                        if (key(node), field) not in intended_slots and not all(_number(node.get(corner)) and _alias(node.get('boundVariables', {}).get(corner)) for corner in corners):
                            fail('missing-actual-variable-binding', f"{node['id']}.{field}")
                        continue  # Uniform native radius is verified through four real corners below.
                    fields.append((field, None, alias, value))
            for field, paint_index, aliases, actual in fields:
                aliases = aliases if isinstance(aliases, list) else [aliases]
                ids = [_alias(alias) for alias in aliases]
                if len(ids) != 1 or not ids[0]:
                    if (key(node), field) in intended_slots or (field in ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius') and (key(node), 'cornerRadius') in intended_slots):
                        continue  # Exact semantic declaration checks effective/inherited binding below.
                    fail('missing-actual-variable-binding', f"{node['id']}.{field}")
                    continue
                variable_id = ids[0]
                try:
                    kind, value = resolve(variable_id, node)
                    if kind != ('COLOR' if field in ('fills', 'strokes') else 'FLOAT') or not _equal(kind, value, actual):
                        fail('observed-field-value-mismatch', f"{node['id']}.{field}")
                    variable = variables[variable_id]
                    name = variable.get('name', '')
                    if not name.startswith(identity + '/') and not name.startswith('review/'):
                        fail('wrong-candidate-variable', name)
                    if kind == 'COLOR' and name not in {native_name(identity, role['token']) for role in roles if role['kind'] == 'color'}:
                        fail('unknown-canonical-color-token', name)
                    if kind == 'FLOAT':
                        mode = node.get('resolvedVariableModes', {}).get(variable['variableCollectionId'], collections[variable['variableCollectionId']].get('defaultModeId'))
                        target_id = _alias(variable['valuesByMode'].get(mode))
                        if not target_id and name not in scalar_names:
                            fail('missing-real-scalar-alias', name)
                        elif name not in scalar_names and (name.startswith('review/') or '/type/' in name):
                            target_name = variables.get(target_id, {}).get('name', '')
                            target_number = re.fullmatch(r'review/primitive/(\d+(?:[._]\d+)?)', target_name)
                            if not target_number or not _equal('FLOAT', float(target_number[1].replace('_', '.')), value):
                                fail('scalar-alias-name-value-mismatch', name)
                        suffix = re.search(r'/(\d+(?:[._]\d+)?)$', name)
                        if name not in scalar_names and suffix and not _equal('FLOAT', float(suffix[1].replace('_', '.')), value):
                            fail('numeric-token-name-value-mismatch', name)
                        if field == 'fontSize':
                            layer = expected_sizes.get(key(node))
                            if layer and not _equal('FLOAT', layer['size'], actual):
                                fail('projected-font-size-mismatch', key(node))
                            concrete_role = re.search(r'/type/(display|body|serif)/', name)
                            role = layer.get('font', 'body') if layer else concrete_role[1] if concrete_role else 'body'
                            if name not in scalar_names and not name.startswith(identity + '/type/' + role + '/') and name != 'review/type/palette':
                                fail('unsupported-native-type-token-name', name)
                            expected_font = candidate.get('fonts', {}).get(role) if layer or concrete_role or name == 'review/type/palette' else None
                            if expected_font and (not isinstance(node.get('fontName'), dict) or any(node['fontName'].get(k) != v for k, v in expected_font.items())):
                                fail('projected-font-family-mismatch', node['id'])
                            style = styles.get(node.get('textStyleId'))
                            if not style and name == 'review/type/palette':
                                limitation = 'Auxiliary palette labels have real size bindings but no shared text style; no canonical typography-style claim.'
                                if limitation not in report['limits']:
                                    report['limits'].append(limitation)
                            elif not style or not _equal('FLOAT', style.get('fontSize'), actual) or style.get('fontName') != node.get('fontName'):
                                fail('missing-real-typography-style', node['id'])
                    use = {'nodeId': node['id'], 'ownerFrameId': owner(node), 'field': field,
                           'variableId': variable_id, 'token': name, 'type': kind, 'value': value}
                    if paint_index is not None:
                        use['paintIndex'] = paint_index
                    if not use['ownerFrameId'] or not visible(nodes[use['ownerFrameId']]):
                        fail('missing-visible-owning-frame', node['id'])
                    uses.append(use)
                    if name.startswith('review/'):
                        auxiliary.append(use)
                except (ValueError, KeyError, TypeError) as exc:
                    fail('invalid-native-variable', str(exc))
        # Canonical contracts are graph authority; observed JSON counters/aliases are not.
        covered_bindings = []
        report['canonical_bindings'] = covered_bindings
        required_bindings = 0
        children = {}
        for node in nodes.values():
            children.setdefault(node.get('parentId'), []).append(node)
        corners = ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius')
        allowed = {'color': {'fills', 'strokes'}, 'typography': {'fontFamily', 'fontSize'},
                   'spacing': {'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'itemSpacing'},
                   'radius': set(corners) | {'cornerRadius'}}
        def actual_value(node, field, paint_index=0):
            if field in ('fills', 'strokes'):
                paints = node.get(field, [])
                paint = paints[paint_index] if isinstance(paints, list) and 0 <= paint_index < len(paints) else {}
                return paint.get('color') if paint.get('type') == 'SOLID' else None
            if field == 'fontFamily':
                family = node.get('fontName', {}).get('family') if isinstance(node.get('fontName'), dict) else None
                if family is not None:
                    return family
                segments = node.get('fontSegments', node.get('textSegments', []))
                families = {segment.get('fontName', {}).get('family') for segment in segments}
                return next(iter(families)) if len(families) == 1 else None
            if field == 'cornerRadius' and not _number(node.get(field)):
                values = [node.get(corner) for corner in corners]
                return values[0] if all(_number(value) and value == values[0] for value in values) else None
            return node.get(field)
        def getter_aliases(node, field, paint_index=0):
            if field in ('fills', 'strokes'):
                paints = node.get(field, [])
                value = paints[paint_index].get('boundVariables', {}).get('color') if isinstance(paints, list) and 0 <= paint_index < len(paints) else None
            else:
                value = node.get('fontFamilyBinding') if field == 'fontFamily' and 'fontFamilyBinding' in node else node.get('boundVariables', {}).get(field)
                if value == []:
                    value = None
                if value is None and field == 'cornerRadius':
                    value = [node.get('boundVariables', {}).get(corner) for corner in corners]
                    if not any(value):
                        value = None
                if value is None and field in ('fontFamily', 'fontSize'):
                    segments = node.get('fontSegments', node.get('textSegments', [])) if field == 'fontFamily' else node.get('textSegments', [])
                    end, ranged = 0, []
                    for segment in segments:
                        if segment.get('start') != end or not isinstance(segment.get('end'), int) or segment['end'] <= end:
                            return [], 'invalid-segments'
                        end = segment['end']
                        segment_value = segment.get('fontName', {}).get('family') if field == 'fontFamily' else segment.get(field)
                        if segment_value != actual_value(node, field):
                            return [], 'invalid-segments'
                        ranged.append(segment.get('boundVariables', {}).get(field))
                    if segments:
                        if end != len(node.get('characters', '').encode('utf-16-le')) // 2:
                            return [], 'invalid-segments'
                        segment_ids = [_alias(value) for value in ranged]
                        if any(segment_ids):
                            return segment_ids, 'segments'
                    style = styles.get(node.get('textStyleId'), {})
                    if field == 'fontFamily':
                        style_value = style.get('fontName', {}).get('family')
                    else:
                        style_value = style.get(field)
                    if (style_value == actual_value(node, field) and
                        style.get('fontSize') == node.get('fontSize') and style.get('fontName') == node.get('fontName')):
                        value = style.get('boundVariables', {}).get(field)
                        if value:
                            return [_alias(value)], 'style'
            return ([_alias(item) for item in value] if isinstance(value, list) else [_alias(value)] if value is not None else []), 'node'
        def inherited(node, field, paint_index):
            current, path, seen = node, [], set()
            while current and current['id'] not in seen and current.get('type') != 'INSTANCE':
                seen.add(current['id'])
                parent = nodes.get(current.get('parentId'))
                if not parent:
                    return None
                path.append(children[parent['id']].index(current))
                current = parent
            if not current or current.get('type') != 'INSTANCE' or not isinstance(current.get('overrides'), list):
                return None
            overridden = {field, 'boundVariables'} | ({'fontName', 'textStyleId', 'fontFamily', 'fontSize'} if field in ('fontFamily', 'fontSize') else set()) | (set(corners) if field == 'cornerRadius' else set())
            if any(change.get('id') == node['id'] and overridden.intersection(change.get('overriddenFields', [])) for change in current['overrides']):
                return None
            main = nodes.get(current.get('mainComponentId'))
            if not main or main.get('type') != 'COMPONENT' or not belongs(main) or not visible(main):
                return None
            source = main
            for index in reversed(path):
                rows = children.get(source['id'], [])
                if index >= len(rows):
                    return None
                source = rows[index]
            same_type = source.get('type') == node.get('type') or (not path and source.get('type') == 'COMPONENT' and node.get('type') == 'INSTANCE')
            if not same_type or actual_value(source, field, paint_index) != actual_value(node, field, paint_index):
                return None
            return source
        def canonical_alias(variable, node, expected_alias, expected_type, expected_value):
            collection = collections[variable['variableCollectionId']]
            mode = (node or {}).get('resolvedVariableModes', {}).get(collection['id'], collection.get('defaultModeId'))
            raw = variable.get('valuesByMode', {}).get(mode)
            target = variables.get(_alias(raw), {})
            if expected_alias:
                if target.get('name') != native_name(identity, expected_alias) or target.get('resolvedType') != expected_type or target.get('variableCollectionId') != collection['id']:
                    return False
                primitive_mode = (node or {}).get('resolvedVariableModes', {}).get(collection['id'], collection.get('defaultModeId'))
                return not _alias(target.get('valuesByMode', {}).get(primitive_mode)) and _equal(expected_type, target.get('valuesByMode', {}).get(primitive_mode), expected_value)
            return not _alias(raw) and _equal(expected_type, raw, expected_value)
        for role in roles:
            token = native_name(identity, role['token'])
            start_failures, start_covered = len(failures), len(covered_bindings)
            spec = role.get('native')
            if spec is None and role['kind'] == 'color':
                spec = {'type': 'COLOR', 'value': _color(role['value']), 'bindings': []}
            elif spec is None:
                spec = resolved_specs.get(role['token'])
            if not isinstance(spec, dict) or spec.get('type') not in ('COLOR', 'FLOAT', 'STRING') or not _equal(spec.get('type'), spec.get('value'), spec.get('value')):
                fail('missing-exact-native-role-declaration', role['token'])
                uncovered.append({'token': role['token'], 'kind': role['kind'], 'reason': 'Explicit typed native value and intended bindings required.'})
                continue
            matches = [variable for variable in variables.values() if variable.get('name') == token]
            if len(matches) != 1:
                fail('missing-or-ambiguous-canonical-role-variable', token)
                uncovered.append({'token': role['token'], 'kind': role['kind'], 'reason': 'Canonical native variable unavailable or ambiguous.'})
                continue
            variable = matches[0]
            expected_type, expected_value = spec['type'], spec['value']
            try:
                kind, value = resolve(variable['id'])
                if kind != expected_type or not _equal(expected_type, expected_value, value):
                    fail('canonical-role-value-mismatch', token)
                if not canonical_alias(variable, None, role.get('alias'), expected_type, expected_value):
                    fail('canonical-role-alias-mismatch', token)
                bindings = spec.get('bindings', [])
                if not isinstance(bindings, list):
                    raise ValueError('native bindings must be a list: ' + token)
                if not bindings and role['kind'] == 'color' and role.get('native') is None:
                    bindings = [{'key': key(nodes[use['nodeId']]), 'nodeId': use['nodeId'], 'field': use['field'], 'paintIndex': use.get('paintIndex', 0)} for use in uses if use['variableId'] == variable['id']]
                if not bindings:
                    fail('missing-intended-native-role-bindings', token)
                seen_bindings = set()
                for binding in bindings:
                    required_bindings += 1
                    locator, field = binding.get('key'), binding.get('field')
                    index = binding.get('paintIndex', 0)
                    slot = binding.get('nodeId') or locator, field, index
                    if slot in seen_bindings:
                        fail('duplicate-intended-native-binding', slot)
                        continue
                    seen_bindings.add(slot)
                    expected_field_type = 'COLOR' if field in ('fills', 'strokes') else 'STRING' if field == 'fontFamily' else 'FLOAT'
                    if field not in allowed.get(role['kind'], set()) or expected_field_type != expected_type or not isinstance(index, int) or index < 0:
                        fail('unsupported-intended-role-field', slot)
                        continue
                    targets = [nodes[binding['nodeId']]] if binding.get('nodeId') in nodes else [node for node in nodes.values() if locator and locator == key(node)]
                    if len(targets) != 1 or not belongs(targets[0]) or not visible(targets[0]):
                        fail('missing-or-ambiguous-intended-node', locator)
                        continue
                    node = targets[0]
                    if locator in expected_owners:
                        owner_key, owner_type = expected_owners[locator]
                        owners = [item for item in nodes.values() if key(item) == owner_key and item.get('type') == owner_type]
                        if len(owners) != 1 or not within(node['id'], owners[0]['id']):
                            fail('intended-target-outside-authored-owner', locator)
                            continue
                    if role['kind'] == 'spacing' and node.get('layoutMode') not in ('VERTICAL', 'HORIZONTAL'):
                        fail('intended-spacing-not-used-by-layout', node['id'])
                        continue
                    if field in ('fontFamily', 'fontSize') and (node.get('type') != 'TEXT' or not node.get('characters')):
                        fail('missing-rendered-typography-target', node['id'])
                        continue
                    if not _equal(expected_type, actual_value(node, field, index), expected_value):
                        fail('intended-field-value-mismatch', f"{node['id']}.{field}")
                        continue
                    actual_type, actual_resolved = resolve(variable['id'], node)
                    if actual_type != expected_type or not _equal(expected_type, actual_resolved, expected_value) or not canonical_alias(variable, node, role.get('alias'), expected_type, expected_value):
                        fail('intended-mode-value-or-alias-mismatch', f"{node['id']}.{field}")
                        continue
                    aliases, proof = getter_aliases(node, field, index)
                    inherited_from = None
                    if not aliases and proof != 'invalid-segments':
                        inherited_from = inherited(node, field, index)
                        if inherited_from:
                            aliases, proof = getter_aliases(inherited_from, field, index)
                            proof = 'proven-main-inheritance/' + proof
                    if not aliases or any(identifier != variable['id'] for identifier in aliases):
                        fail('intended-canonical-binding-mismatch', f"{node['id']}.{field}")
                        continue
                    covered_bindings.append({'token': role['token'], 'declared': role['token'] in resolved_specs, 'nodeId': node['id'], 'field': field, 'variableId': variable['id'], 'proof': proof, **({'mainNodeId': inherited_from['id']} if inherited_from else {})})
                if len(failures) == start_failures and len(covered_bindings) > start_covered:
                    observations.append({'token': role['token'], 'kind': role['kind'], 'variableId': variable['id'], 'uses': len(covered_bindings) - start_covered})
                else:
                    uncovered.append({'token': role['token'], 'kind': role['kind'], 'reason': 'At least one exact alias/value/intended-field proof is missing.'})
            except (ValueError, KeyError, TypeError) as exc:
                fail('invalid-native-role', str(exc))
                uncovered.append({'token': role['token'], 'kind': role['kind'], 'reason': str(exc)})
        def box(node):
            rect = node.get('absoluteBoundingBox')
            if not isinstance(rect, dict) or any(not _number(rect.get(k)) for k in ('x', 'y', 'width', 'height')) or rect['width'] <= 0 or rect['height'] <= 0:
                fail('missing-real-visible-bounds', node['id'])
                return None
            return rect
        def separate(items, code):
            unique = {node['id']: node for node in items}
            bounded = [(node, box(node)) for node in unique.values() if visible(node)]
            for i, (node, a) in enumerate(bounded):
                for other, b in bounded[i + 1:]:
                    if a and b and a['x'] < b['x'] + b['width'] and b['x'] < a['x'] + a['width'] and a['y'] < b['y'] + b['height'] and b['y'] < a['y'] + a['height']:
                        fail(code, node['id'] + ' / ' + other['id'])
        library = nodes.get(library_id)
        if not library or library.get('type') != 'FRAME' or not visible(library) or not within(library_id, page_id):
            fail('missing-real-palette-owner', identity)
        expected_samples = plan.get('palette', {}).get('samples', [])
        samples = palette.get('samples', [])
        if len(samples) != len(expected_samples) or not samples:
            fail('palette-sample-coverage-mismatch', identity)
        sample_nodes, set_ids, labels = [], set(), set()
        for sample, expected in zip(samples, expected_samples):
            for field in ('label', 'component', 'variant', 'action', 'state', 'useCases'):
                if sample.get(field) != expected.get(field):
                    fail('palette-meaning-differs-from-graph', field)
            instance, main, component_set = (nodes.get(sample.get(field), {}) for field in ('instanceId', 'mainComponentId', 'componentSetId'))
            label, documentation = (nodes.get(sample.get(field), {}) for field in ('labelNodeId', 'documentationNodeId'))
            if (instance.get('type') != 'INSTANCE' or not visible(instance) or not within(instance.get('id'), library_id) or
                instance.get('mainComponentId') != main.get('id') or main.get('type') != 'COMPONENT' or
                component_set.get('type') != 'COMPONENT_SET' or main.get('parentId') != component_set.get('id') or
                sample.get('variant') not in main.get('variantProperties', {}).values()):
                fail('invalid-real-palette-relationship', sample.get('label'))
                continue
            if sample.get('label') in labels:
                fail('duplicate-palette-label', sample.get('label'))
            labels.add(sample.get('label'))
            owner_id = instance.get('parentId')
            if label.get('type') != 'TEXT' or label.get('characters') != sample.get('label') or not visible(label) or not within(label.get('id'), owner_id):
                fail('missing-real-palette-label', sample.get('label'))
            phrases = [sample.get('action', ''), sample.get('state', ''), *sample.get('useCases', [])]
            if documentation.get('type') != 'TEXT' or not visible(documentation) or not within(documentation.get('id'), owner_id) or any(value not in documentation.get('characters', '') for value in phrases):
                fail('missing-real-palette-documentation', sample.get('label'))
            sample_nodes.append(instance)
            set_ids.add(component_set['id'])
        sets = [node for node in nodes.values() if node.get('type') == 'COMPONENT_SET' and (node['id'] in set_ids or key(node).startswith(identity + '.'))]
        separate(sample_nodes + sets, 'overlapping-palette-items')
        for component_set in sets:
            separate([node for node in nodes.values() if node.get('parentId') == component_set['id']], 'overlapping-main-variants')
        top_frames = [node for node in nodes.values() if node.get('parentId') == page_id and node.get('type') == 'FRAME' and (belongs(node) or any(within(component_set['id'], node['id']) for component_set in sets))]
        separate(top_frames, 'overlapping-owner-frames')
        if not uses or not observations:
            fail('no-visible-canonical-foundation-uses', identity)
        report['palette'] = {'libraryId': library_id, 'sampleIds': [node['id'] for node in sample_nodes], 'componentSetIds': sorted(set_ids)}
        report['counts'] = {'visible_bound_fields': len(uses), 'used_variables': len({use['variableId'] for use in uses}),
                            'owner_frames': len({use['ownerFrameId'] for use in uses if use['ownerFrameId']}),
                            'observed_canonical_roles': len({role['variableId'] for role in observations}), 'unobserved_planned_roles': len(uncovered),
                            'real_palette_instances': len({node['id'] for node in sample_nodes}), 'auxiliary_review_fields': len(auxiliary),
                            'required_semantic_bindings': required_bindings, 'covered_semantic_bindings': len(covered_bindings),
                            'declared_native_bindings': sum(len(row.get('bindings', [])) for row in declarations),
                            'covered_declared_native_bindings': sum(binding['declared'] for binding in covered_bindings)}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        fail('invalid-draft-foundation-evidence', str(exc))
    report['errors'] = [failure['code'] + ': ' + failure['subject'] for failure in failures]
    report['ok'] = report['passed'] = not failures
    report['status'] = 'blocked' if failures else 'observed-declared-scope'
    return report
