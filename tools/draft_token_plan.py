"""Compile a graph's typed semantic roles against the properties of its authored layout."""
import math
import re

FIELDS = {
    ('typography', 'STRING'): {'fontFamily'},
    ('typography', 'FLOAT'): {'fontSize'},
    ('spacing', 'FLOAT'): {'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'itemSpacing'},
    ('radius', 'FLOAT'): {'cornerRadius'},
}


def authored_fields(source, graph):
    """Index bindable properties by the same stable keys used in the Figma source."""
    fields = {}
    identity = source['id']
    fonts = source['fonts']
    prototype = graph['draft_prototype']
    action_variants = {n['id']: n.get('annotation', {}).get('visual_variant') for n in graph['nodes'] if n.get('type') == 'action'}

    def put(key, properties):
        if key in fields:
            raise ValueError('Ambiguous native target in authored layout: ' + key)
        fields[key] = properties

    def control(key, style):
        icon = style.get('icon')
        item_spacing = icon.get('gap', 0) if isinstance(icon, dict) else 0
        put(key, {'cornerRadius': style['radius'], 'paddingLeft': style['paddingX'],
                  'paddingRight': style['paddingX'], 'paddingTop': style['paddingY'],
                  'paddingBottom': style['paddingY'], 'itemSpacing': item_spacing})
        put(key + '.label', {'fontFamily': fonts[style.get('font', 'body')]['family'], 'fontSize': style['fontSize']})

    for viewport, states in source['state_layouts'].items():
        styles = source['control_styles'][viewport]
        for visual, style in styles.items():
            control(f'{identity}.{viewport}.component.{visual}', style)
        for state, layout in states.items():
            prefix = f'{identity}.{viewport}.{state}.'
            for layer in layout['layers']:
                if layer['kind'] == 'text':
                    put(prefix + layer['id'], {'fontFamily': fonts[layer.get('font', 'body')]['family'],
                                               'fontSize': layer['size']})
            for edge in prototype['bindings']:
                if edge['viewport'] == viewport and edge['source_state'] == state:
                    visual = action_variants.get(edge['action'])
                    if visual not in styles:
                        raise ValueError('No authored component style for action ' + edge['action'])
                    control(prefix + edge['control_id'], styles[visual])
            for button_id, button in layout.get('product_buttons', {}).items():
                if button.get('variant') not in styles:
                    raise ValueError('No authored component style for product button ' + button_id)
                control(prefix + button_id, styles[button['variant']])
    return fields


def name_path(name):
    if not isinstance(name, str) or any(not s or s != s.strip() or not s.isprintable() for s in name.split('/')):
        raise ValueError('Expected a valid Figma variable name: ' + str(name))
    return name


def native_name(identity, name):
    path = name_path(name)
    return path if path.startswith(identity + '/') else identity + '/' + path


def check_display_value(role, variable_type, value):
    # Numeric size annotations in a family description are not font-family variables.
    displayed = role.get('value')
    if variable_type == 'FLOAT':
        if type(displayed) in (float, int):
            values = [displayed]
        else:
            other = re.search(r'-?\d+(?:\.\d+)?\s*(rem|em|pt|%|vw|vh|ch)(?![a-z])', str(displayed), re.I)
            if other:
                raise ValueError(f"{role['token']}: displayed unit {other.group(1)!r} cannot be compared with the native px value; show px")
            values = [float(n) for n in re.findall(r'(-?\d+(?:\.\d+)?)\s*px\b', str(displayed), re.I)]
            if re.fullmatch(r'-?\d+(?:\.\d+)?', str(displayed).strip()):
                values.append(float(displayed))
        if any(n != value for n in values):
            raise ValueError(f"{role['token']}: displayed value {displayed!r} conflicts with native value {value!r}")
    elif variable_type == 'STRING':
        # The plan must show the written family itself (optionally followed by style/size notes),
        # not merely list it somewhere in source_values.
        shown = str(displayed)
        if shown != value and not shown.startswith(value + ' ') and shown.split(',')[0].strip() != value:
            raise ValueError(f"{role['token']}: font family {value!r} is absent from the displayed plan")


def _legacy_native(role, source, fields, graph):
    """Recover an unambiguous former role; never choose a consumer by a coincidental number."""
    token = role['token']
    if token == 'radius/control' and role['kind'] == 'radius':
        match = re.fullmatch(r'(\d+(?:\.\d+)?)px', str(role.get('value')))
        if match:
            value = float(match[1])
            return {'type': 'FLOAT', 'value': value,
                    'bindings': [{'key': key, 'field': 'cornerRadius'} for key, props in fields.items() if 'cornerRadius' in props]}
    font = next((key for key in source['fonts'] if token == 'type/' + key and role.get('alias') == 'font/' + key), None)
    if font and role['kind'] == 'typography':
        keys = []
        for viewport, states in source['state_layouts'].items():
            for state, layout in states.items():
                keys.extend(f"{source['id']}.{viewport}.{state}.{layer['id']}" for layer in layout['layers']
                            if layer['kind'] == 'text' and layer.get('font', 'body') == font)
        actions = {node['id']: node.get('annotation', {}).get('visual_variant') for node in graph['nodes'] if node.get('type') == 'action'}
        for viewport, states in source['state_layouts'].items():
            styles = source['control_styles'][viewport]
            for visual, style in styles.items():
                if style.get('font', 'body') == font:
                    keys.append(f"{source['id']}.{viewport}.component.{visual}.label")
            for edge in graph['draft_prototype']['bindings']:
                if edge['viewport'] == viewport and styles[actions[edge['action']]].get('font', 'body') == font:
                    keys.append(f"{source['id']}.{viewport}.{edge['source_state']}.{edge['control_id']}.label")
            for state_id, layout in states.items():
                for button_id, button in layout.get('product_buttons', {}).items():
                    if styles[button['variant']].get('font', 'body') == font:
                        keys.append(f"{source['id']}.{viewport}.{state_id}.{button_id}.label")
        return {'type': 'STRING', 'value': source['fonts'][font]['family'],
                'bindings': [{'key': key, 'field': 'fontFamily'} for key in keys]}
    raise ValueError(f'{token}: declare native.type, native.value and native.bindings for the intended properties')


def _rgb(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Authored COLOR values must be opaque six-digit hex colors: ' + str(value))
    return {channel: int(value[index:index + 2], 16) / 255 for channel, index in zip('rgb', (1, 3, 5))}


def _color_consumers(source, graph):
    """Mirror rendered source paints, excluding references and auxiliary libraries.

    Return reports and bindable screen/control paints. Main-component libraries
    are not screen consumers. Defining a variable, identical hex, gradient stop or unused style
    cannot turn a role into a visible named consumer.
    """
    identity = source['id']
    roles = [role for role in graph['design_foundations']['roles'] if role['kind'] == 'color']
    if not roles:
        return [], {}  # Preserve noncolor-only normalizer calls; whole draft admission requires colors.
    colors = source.get('colors')
    if not isinstance(colors, dict):
        raise ValueError('Authored colors must match declared COLOR role names')
    declared, uses, bindable = {}, {}, {}
    for role in roles:
        leaf = name_path(role['token']).split('/')[-1]
        if leaf in declared:
            raise ValueError('Ambiguous authored paint name: ' + leaf)
        if leaf not in colors or _rgb(colors[leaf]) != _rgb(role['value']):
            raise ValueError(f"{role['token']}: authored source.colors value differs from the graph")
        declared[leaf], uses[leaf] = role, []
    if set(colors) != set(declared):
        raise ValueError('Authored source.colors contains unknown/unbound COLOR role names')
    def named(name, key):
        if not isinstance(name, str) or name not in declared:
            raise ValueError(f'Unknown/unbound authored paint name {name!r} at {key}')
        return name
    def add(name, key, field='fills'):
        named(name, key)
        slot = key, field
        if slot in bindable:
            raise ValueError('Ambiguous authored paint target: ' + key + '.' + field)
        bindable[slot] = name
        uses[name].append({'key': key, 'field': field})
    def intersects(box, layout):
        return (all(type(box.get(k)) in (int, float) and math.isfinite(box[k]) for k in ('x', 'y', 'w', 'h')) and
                box['w'] > 0 and box['h'] > 0 and box['x'] < layout['width'] and box['y'] < layout['height'] and
                box['x'] + box['w'] > 0 and box['y'] + box['h'] > 0)
    prototype = graph['draft_prototype']
    states, edges = prototype.get('states'), prototype.get('bindings')
    if not isinstance(states, list) or not states or not isinstance(edges, list):
        raise ValueError('Rendered prototype states and bindings required for COLOR consumers')
    actions = {node['id']: node for node in graph['nodes'] if node.get('type') == 'action'}
    for viewport in ('desktop', 'mobile'):
        styles = source['control_styles'].get(viewport, {})
        # These paints are also authored as mains; validate their names, but do
        # not credit their existence as actual screen usage.
        for visual, style in styles.items():
            if 'fill' not in style or style['fill'] is not None:
                named(style.get('fill'), f'{identity}.{viewport}.component.{visual}')
            named(style.get('ink'), f'{identity}.{viewport}.component.{visual}.label')
            if 'stroke' in style:
                named(style['stroke'], f'{identity}.{viewport}.component.{visual}.stroke')
        for state in states:
            state_id = state['id']
            key = f'{identity}.{viewport}.{state_id}'
            layout = source.get('state_layouts', {}).get(viewport, {}).get(state_id)
            if not isinstance(layout, dict) or any(type(layout.get(d)) not in (int, float) or not math.isfinite(layout[d]) or layout[d] <= 0 for d in ('width', 'height')) or not isinstance(layout.get('layers'), list):
                raise ValueError('Rendered state layout required for COLOR consumers: ' + key)
            add(layout.get('bg'), key)
            for layer in layout['layers']:
                kind = layer.get('kind')
                if kind not in ('rect', 'ellipse', 'text'):
                    continue  # Raster and raw gradient stops bind other assets/stop tokens, not these roles.
                layer_key = key + '.' + str(layer.get('id', ''))
                solid = kind in ('rect', 'ellipse')
                paint = named(layer.get('fill' if solid else 'ink'), layer_key)
                stroke = named(layer['stroke'], layer_key + '.stroke') if solid and 'stroke' in layer else None
                if not intersects(layer, layout):
                    continue
                if solid or (isinstance(layer.get('value'), str) and layer['value'].strip() and
                             type(layer.get('size')) in (int, float) and math.isfinite(layer['size']) and layer['size'] > 0):
                    add(paint, layer_key)
                if stroke is not None:
                    add(stroke, layer_key, 'strokes')
            for edge in edges:
                if edge.get('viewport') != viewport or edge.get('source_state') != state_id:
                    continue
                action = actions.get(edge.get('action'), {})
                visual = action.get('annotation', {}).get('visual_variant')
                style = styles.get(visual)
                control_key = key + '.' + str(edge.get('control_id', ''))
                box = layout.get('control_boxes', {}).get(edge.get('control_id'))
                if not style or not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box) or box[2] <= 0 or box[3] <= 0:
                    raise ValueError('Actual control box/style required for COLOR consumer: ' + control_key)
                if not intersects(dict(zip(('x', 'y', 'w', 'h'), box)), layout):
                    continue
                if style['fill'] is not None:
                    add(style['fill'], control_key)
                if 'stroke' in style:
                    add(style['stroke'], control_key, 'strokes')
                if isinstance(action.get('title'), str) and action['title'].strip():
                    add(style['ink'], control_key + '.label')
            for button_id, button in layout.get('product_buttons', {}).items():
                control_key = key + '.' + button_id
                style = styles.get(button.get('variant'))
                box = button.get('box')
                if (not style or not isinstance(box, list) or len(box) != 4 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in box) or
                    box[2] <= 0 or box[3] <= 0 or not isinstance(button.get('label'), str) or not button['label'].strip()):
                    raise ValueError('Actual product button box/style/label required for COLOR consumer: ' + control_key)
                if not intersects(dict(zip(('x', 'y', 'w', 'h'), box)), layout):
                    continue
                if style['fill'] is not None:
                    add(style['fill'], control_key)
                add(style['ink'], control_key + '.label')
                if 'stroke' in style:
                    add(style['stroke'], control_key, 'strokes')
    reports = []
    unused = [role['token'] for leaf, role in declared.items() if not uses[leaf]]
    if unused:  # Report every unused role at once instead of one per run.
        raise ValueError(', '.join(unused) + ': no visible authored screen/control COLOR consumer'
                         + (f' ({len(unused)} roles)' if len(unused) > 1 else ''))
    for leaf, role in declared.items():
        reports.append({'candidate': identity, 'token': role['token'], 'consumers': uses[leaf]})
    return reports, bindable


def authored_color_consumers(source, graph):
    """Public, pure named-use report; no declaration or preview-only credit."""
    return _color_consumers(source, graph)[0]


def foundation_bindings(source, graph):
    if not graph.get('draft_prototype') or not isinstance(graph.get('design_foundations'), dict):
        raise ValueError('Native review requires a declared prototype and design foundation roles')
    fields = authored_fields(source, graph)
    roles = graph['design_foundations'].get('roles')
    if not isinstance(roles, list) or not roles:
        raise ValueError('Define the semantic roles consumed by this Figma layout')
    _, color_targets = _color_consumers(source, graph)
    semantic_names = {native_name(source['id'], r['token']) for r in roles}
    if len(semantic_names) != len(roles):
        raise ValueError('Duplicate semantic variable name in the graph')
    identity = re.escape(source['id'])
    font_roles = '|'.join(re.escape(name) for name in (source.get('fonts') or {})) or '(?!)'
    reserved = re.compile(rf'{identity}/(?:type/(?:{font_roles})/\d+(?:\.\d+)?|radius/observed/\d+(?:\.\d+)?)')
    for role in roles:
        for name in filter(None, (role['token'], role.get('alias'))):
            if reserved.fullmatch(native_name(source['id'], name)):
                raise ValueError(f'{name}: name is reserved for importer fallback variables; choose another token name')
    primitives = {}
    assignments = {}
    result = []
    color_keys = set()
    for role in roles:
        token, alias, kind = role['token'], role.get('alias'), role['kind']
        if alias is not None:
            primitive_name = native_name(source['id'], alias)
            if primitive_name in semantic_names:
                raise ValueError(f'{token}: primitive alias collides with a semantic variable')
        if kind == 'color':
            leaf = token.split('/')[-1]
            if leaf in color_keys:
                raise ValueError('Ambiguous authored paint name: ' + leaf)
            color_keys.add(leaf)
            variable_type, value = 'COLOR', role['value']
            native = role.get('native')
            if native is not None:
                if not isinstance(native, dict) or native.get('type') != 'COLOR':
                    raise ValueError(f'{token}: explicit native COLOR declaration required')
                rgba = native.get('value')
                if (not isinstance(rgba, dict) or not set('rgb') <= set(rgba) or set(rgba) - set('rgba') or
                    any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in rgba.values()) or
                    rgba.get('a', 1) != 1 or any(not math.isclose(rgba[c], _rgb(role['value'])[c], abs_tol=1e-7) for c in 'rgb')):
                    raise ValueError(f'{token}: native RGB(A) differs from authored opaque color')
                bindings = native.get('bindings')
                if not isinstance(bindings, list) or not bindings:
                    raise ValueError(f'{token}: no declared native COLOR consumer')
                checked = []
                for binding in bindings:
                    if not isinstance(binding, dict):
                        raise ValueError(f'{token}: invalid native COLOR binding')
                    key, field = binding.get('key'), binding.get('field')
                    if field not in ('fills', 'strokes') or type(binding.get('paintIndex', 0)) is not int or binding.get('paintIndex', 0) != 0 or color_targets.get((key, field)) != leaf:
                        raise ValueError(f'{token}: native target is not its authored named paint {key}.{field}')
                    if (key, field) in assignments:
                        raise ValueError(f'{token}: {key}.{field} already declared for {assignments[key, field]}')
                    assignments[key, field] = token
                    checked.append({'key': key, 'field': field, **({'paintIndex': 0} if 'paintIndex' in binding else {})})
                result.append({'token': token, 'alias': alias, 'type': 'COLOR', 'value': rgba, 'bindings': checked})
        else:
            native = role.get('native')
            if native is None:
                native = _legacy_native(role, source, fields, graph)
            if not isinstance(native, dict):
                raise ValueError(f'{token}: invalid native role declaration')
            variable_type, value = native.get('type'), native.get('value')
            allowed = FIELDS.get((kind, variable_type), set())
            if not allowed:
                raise ValueError(f'{token}: unsupported native type {variable_type} for {kind}')
            if variable_type == 'STRING':
                valid = isinstance(value, str) and bool(value.strip())
            else:
                valid = type(value) in (int, float) and math.isfinite(value) and (value > 0 if kind == 'typography' else value >= 0)
            if not valid:
                raise ValueError(f'{token}: invalid native value {value!r}')
            check_display_value(role, variable_type, value)
            bindings = native.get('bindings')
            if not isinstance(bindings, list) or not bindings:
                raise ValueError(f'{token}: no declared consumer')
            checked = []
            for binding in bindings:
                if not isinstance(binding, dict):
                    raise ValueError(f'{token}: invalid binding')
                key, field = binding.get('key'), binding.get('field')
                if field not in allowed or field not in fields.get(key, {}):
                    raise ValueError(f'{token}: missing or incompatible authored property {key}.{field}')
                actual = fields[key][field]
                if value != actual:
                    raise ValueError(f'{token}: expected {value!r} but {key}.{field} is authored as {actual!r}')
                if (key, field) in assignments:
                    raise ValueError(f'{token}: {key}.{field} already declared for {assignments[key, field]}')
                assignments[key, field] = token
                checked.append({'key': key, 'field': field})
            result.append({'token': token, 'alias': alias, 'type': variable_type, 'value': value, 'bindings': checked})
        if alias is not None:
            definition = (variable_type, tuple(_rgb(role['value'])[c] for c in 'rgb')) if kind == 'color' else (variable_type, value)
            if primitive_name in primitives and primitives[primitive_name] != definition:
                raise ValueError(f'{token}: conflicting type or value for shared primitive {alias}')
            primitives[primitive_name] = definition
    # A screen control is an instance of its main component: a FLOAT/STRING role on the instance must also be
    # declared on that main, or Figma rejects the instance binding after the page already exists.
    actions = {node['id']: node for node in graph.get('nodes', []) if node.get('type') == 'action'}
    controls = []
    for edge in graph['draft_prototype'].get('bindings', []):
        visual = actions.get(edge.get('action'), {}).get('annotation', {}).get('visual_variant')
        instance = f"{source['id']}.{edge.get('viewport')}.{edge.get('source_state')}.{edge.get('control_id')}"
        main = f"{source['id']}.{edge.get('viewport')}.component.{visual}"
        controls.append((instance, main))
    for viewport, states in source['state_layouts'].items():
        for state_id, layout in states.items():
            for button_id, button in layout.get('product_buttons', {}).items():
                controls.append((f"{source['id']}.{viewport}.{state_id}.{button_id}",
                                 f"{source['id']}.{viewport}.component.{button['variant']}"))
    for instance, main in controls:
        for suffix in ('', '.label'):
            for (key, field), token in assignments.items():
                if key == instance + suffix and field not in ('fills', 'strokes') and assignments.get((main + suffix, field)) != token:
                    raise ValueError(f'{token}: control {key}.{field} needs the same role on its main component {main + suffix}.{field}')
    return result
