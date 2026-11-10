#!/usr/bin/env python3
"""Compile a pinned, reviewed design-system payload into a local Figma plugin."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Input must be a regular JSON file of at most 2 MB')
    raw = path.read_bytes()
    return raw, json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))


def variable_value(token):
    kind, value = token.get('type'), token.get('value')
    if kind == 'color' and isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?', value):
        return 'COLOR', dict(zip(('r', 'g', 'b', 'a'), [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)] + [int(value[7:9], 16) / 255 if len(value) == 9 else 1]))
    if kind == 'dimension' and isinstance(value, str) and re.fullmatch(r'(?:0|[0-9]+(?:\.[0-9]+)?)(?:px|rem)', value):
        return 'FLOAT', float(value[:-3]) * 16 if value.endswith('rem') else float(value[:-2])
    if kind == 'boolean' and isinstance(value, bool):
        return 'BOOLEAN', value
    if kind == 'number' and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return 'FLOAT', value
    if kind in ('fontFamily', 'string') and isinstance(value, str) and value:
        return 'STRING', value
    raise ValueError(f'Unsupported token value/type: {kind!r}')


def validate(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Expected resolved design-system version 1')
    tokens, components, screens = (data.get(key) for key in ('tokens', 'components', 'screens'))
    if not isinstance(tokens, dict) or not tokens or len(tokens) > 500:
        raise ValueError('Expected 1..500 resolved tokens')
    if not isinstance(components, dict) or not components or len(components) > 100:
        raise ValueError('Expected 1..100 component definitions')
    if not isinstance(screens, list) or not 1 <= len(screens) <= 100:
        raise ValueError('Expected 1..100 screens')
    values = {}
    for name, token in tokens.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', name) or not isinstance(token, dict):
            raise ValueError('Token paths must be dot-separated identifiers')
        values[name] = variable_value(token)
    for name, token in tokens.items():
        alias = token.get('alias')
        seen = {name}
        while alias:
            if alias not in tokens or alias in seen or values[alias][0] != values[name][0]:
                raise ValueError(f'Invalid or cyclic variable alias for {name}')
            if values[alias][1] != values[name][1]:
                raise ValueError(f'Alias value differs from resolved value for {name}')
            seen.add(alias)
            alias = tokens[alias].get('alias')
    variants_count = 0
    for name, component in components.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name) or not isinstance(component, dict) or not isinstance(component.get('variants'), dict) or not component['variants']:
            raise ValueError('Components require named variants')
        for variant, props in component['variants'].items():
            variants_count += 1
            if not isinstance(variant, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', variant) or not isinstance(props, dict) or any(not isinstance(path, str) or path not in tokens for path in props.values()):
                raise ValueError('Every component variant property must reference a resolved token')
    if variants_count > 200:
        raise ValueError('At most 200 component variants are supported')
    ids = set()
    for screen in screens:
        if not isinstance(screen, dict) or not isinstance(screen.get('id'), str) or not screen['id'] or screen['id'] in ids:
            raise ValueError('Screens require unique semantic IDs')
        ids.add(screen['id'])
    all_ids = set(ids)
    count = 0
    for screen in screens:
        if not isinstance(screen.get('title'), str) or not isinstance(screen.get('elements'), list):
            raise ValueError('Screens require title and elements')
        if 'annotation' in screen and not isinstance(screen['annotation'], str):
            raise ValueError('Annotations must be plain text')
        for index, element in enumerate(screen['elements']):
            count += 1
            if not isinstance(element, dict) or element.get('kind') not in ('heading', 'text', 'component') or not isinstance(element.get('text'), str):
                raise ValueError('Elements require kind heading/text/component and plain text')
            identity = element.get('id', f"{screen['id']}/element:{index}")
            if not isinstance(identity, str) or not identity or identity in all_ids:
                raise ValueError('Element semantic IDs must be globally unique')
            all_ids.add(identity)
            if 'target_screen' in element and element['target_screen'] not in ids:
                raise ValueError('Prototype target_screen must reference an existing screen')
            if 'annotation' in element and not isinstance(element['annotation'], str):
                raise ValueError('Annotations must be plain text')
            if 'action_id' in element and not isinstance(element['action_id'], str):
                raise ValueError('Action IDs must be strings')
            if element['kind'] == 'component':
                component = components.get(element.get('component'), {})
                if element.get('variant') not in component.get('variants', {}):
                    raise ValueError('Component elements must reference an existing component variant')
    if count > 1000:
        raise ValueError('At most 1000 screen elements are supported')
    return values



def handoff_contract(data):
    """Derive required native notes from the reviewed model, never plugin stamps."""
    notes = {}
    for screen in data['screens']:
        trace = ', '.join(map(str, screen.get('trace', []))) or 'none declared'
        notes[screen['id']] = (f"Screen {screen['id']}: {screen['title']}. Trace: {trace}. " + screen.get('annotation', '')).strip()
        for index, element in enumerate(screen['elements']):
            if element['kind'] != 'component' and not element.get('action_id') and not element.get('target_screen'):
                continue
            identity = element.get('id', f"{screen['id']}/element:{index}")
            props = data['components'][element['component']]['variants'][element['variant']] if element['kind'] == 'component' else {}
            notes[identity] = (f"Control {identity}: {element['text']}. Trace: {trace}. "
                               f"Action: {element.get('action_id') or 'none declared'}. Target: {element.get('target_screen') or 'none declared'}. "
                               f"States: {json.dumps(element.get('states', element.get('state', element.get('variant', 'none declared'))), ensure_ascii=True, sort_keys=True)}. "
                               f"Component: {element.get('component', 'none')}/{element.get('variant', 'none')}. "
                               f"Tokens: {json.dumps(props, sort_keys=True)}. " + element.get('annotation', '')).strip()
    return {'version': 1, 'required_annotations': notes, 'requires_component_usage': True,
            'requires_variable_bindings': True, 'status': 'pending_native_handoff'}

def expected_handoff(data):
    """Compile the reviewed semantic model to the shared native evidence contract."""
    screens = []
    numeric = {'radius': ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'],
               'cornerRadius': ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'],
               'border-radius': ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'],
               'padding': ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft'],
               'padding-inline': ['paddingLeft', 'paddingRight'], 'padding-block': ['paddingTop', 'paddingBottom'], 'gap': ['itemSpacing']}
    for screen in data['screens']:
        controls = []
        for index, element in enumerate(screen['elements']):
            if element['kind'] != 'component' and not element.get('action_id') and not element.get('target_screen'):
                continue
            identity = element.get('id', f"{screen['id']}/element:{index}")
            action = element.get('action_id') or element.get('target_screen')
            control = {'key': identity, 'static': not bool(action), 'token_bindings': []}
            if element.get('target_screen'):
                control['target_screen'] = element['target_screen']
            if element.get('static_annotation'):
                control['static_annotation'] = element['static_annotation']
            if action:
                states = element.get('states', element.get('state', element.get('variant')))
                control.update(action=action, states=states if isinstance(states, list) else [states] if states else [])
            if element['kind'] == 'component':
                control['component_key'] = f"component:{element['component']}/{element['variant']}"
                final_bindings = {}
                for prop, path in data['components'][element['component']]['variants'][element['variant']].items():
                    fields, label = [], False
                    kind, value = variable_value(data['tokens'][path])
                    if prop in ('background', 'color', 'borderColor', 'border-color') and kind == 'COLOR':
                        fields = ['strokes.0.color' if prop in ('borderColor', 'border-color') else 'fills.0.color']
                        label = prop == 'color'
                    elif prop in numeric and kind == 'FLOAT' and value >= 0:
                        fields = numeric[prop]
                    elif prop in ('fontSize', 'font-size') and kind == 'FLOAT' and value > 0:
                        fields, label = ['fontSize'], True
                    elif prop == 'font-family' and data['tokens'][path]['type'] == 'fontFamily':
                        fields, label = ['fontFamily'], True
                    if not fields:
                        raise ValueError(f'Native component property {prop} needs a compatible token type, not {kind} {path}')
                    for field in fields:
                        binding = {'property': field, 'variable': path.replace('.', '/')}
                        if label:
                            binding['node_key'] = identity + '/label'
                        final_bindings[(binding.get('node_key', identity), field)] = binding
                control['token_bindings'] = list(final_bindings.values())
            controls.append(control)
        screens.append({'key': screen['id'], 'static': not any(not control['static'] for control in controls), 'controls': controls})
    return {'schema': 'figma-flow-native-handoff-v1', 'collection_key': 'token-collection',
            'variables': [{'name': path.replace('.', '/'), 'resolved_type': variable_value(token)[0]} for path, token in data['tokens'].items()],
            'screens': screens}


def production_contract(data, graph):
    """Project selected graph meaning onto actual compiler-supported semantic targets."""
    from annotation_contract import derive_notes
    from design_foundations import derive_foundations, validate_foundations
    notes = derive_notes(graph)
    supported_props = {'background', 'color', 'borderColor', 'border-color', 'radius', 'cornerRadius', 'border-radius', 'padding', 'padding-inline', 'padding-block', 'gap', 'fontSize', 'font-size', 'font-family'}
    for definition in data['components'].values():
        for props in definition['variants'].values():
            if set(props) - supported_props:
                raise ValueError('Unsupported reviewed native component properties: ' + ', '.join(sorted(set(props) - supported_props)))
            for spellings in (('fontSize', 'font-size'), ('borderColor', 'border-color')):
                if all(name in props for name in spellings):
                    raise ValueError('Set only one spelling of a native component property: ' + ' / '.join(spellings))
    plan = copy.deepcopy(derive_foundations(graph))
    report = validate_foundations(None, plan, stage='plan')
    if not report['ok']:
        raise ValueError('Selected graph foundations invalid: ' + json.dumps(report['failures']))
    graph_screens = {n['id'] for n in graph['nodes'] if n.get('type') == 'screen'}
    if {s['id'] for s in data['screens']} != graph_screens:
        raise ValueError('Resolved screens differ from selected canonical graph')
    note_map = {n['target_id']: n for n in notes}
    for screen in data['screens']:
        for index, element in enumerate(screen['elements']):
            if not element.get('action_id') and not element.get('target_screen'):
                continue
            identity = element.get('id', f"{screen['id']}/element:{index}")
            note = note_map.get(identity)
            if not note or element.get('action_id') and note.get('action') != element['action_id']:
                raise ValueError('Resolved control/action differs from selected canonical graph: ' + identity)
            element['action_id'] = note['action']
            supplied = element.get('states', [])
            if supplied and supplied != note['functional_states']:
                raise ValueError('Resolved functional states differ from selected canonical graph: ' + identity)
            element['states'] = note['functional_states']
    token_paths = {path.replace('.', '/'): path for path in data['tokens']}
    for role in plan['roles']:
        token = role['token'].replace('.', '/')
        if token not in token_paths:
            raise ValueError('Selected native role token missing from resolved design: ' + token)
        kind, value = variable_value(data['tokens'][token_paths[token]])
        expected_type = (role.get('native') or {}).get('type', 'COLOR' if role['kind'] == 'color' else 'FLOAT')
        if kind != expected_type or kind == 'FLOAT' and (value <= 0 if role['kind'] == 'typography' else value < 0) or kind == 'STRING' and (role['kind'] != 'typography' or not value.strip()):
            raise ValueError('Selected role has unsupported native value/type: ' + token)
        planned = (role.get('native') or {}).get('value', role.get('native_value', role.get('value')))
        if isinstance(planned, str) and kind != 'STRING':
            planned_kind = 'dimension' if re.fullmatch(r'(?:0|[0-9]+(?:\.[0-9]+)?)(?:px|rem)', planned) else data['tokens'][token_paths[token]]['type']
            try:
                _, planned = variable_value({'type': planned_kind, 'value': planned})
            except ValueError as exc:
                raise ValueError('Selected role requires an exact supported native value: ' + token) from exc
        if not same_variable_value(kind, value, planned):
            raise ValueError('Resolved token differs from selected canonical role value: ' + token)
        alias = data['tokens'][token_paths[token]].get('alias')
        if role.get('alias') and role['alias'].replace('.', '/') != (alias or '').replace('.', '/'):
            raise ValueError('Selected semantic alias differs from resolved design: ' + token)
        role.update(token=token, native_value=value, native_type=kind)
        if role.get('alias'):
            role['alias'] = role['alias'].replace('.', '/')
        if role['kind'] == 'typography' and kind == 'FLOAT':
            role['styleName'] = token
    base_type = next((role for role in plan['roles'] if role['kind'] == 'typography' and role['native_type'] == 'FLOAT'), None)
    base_space = next((role for role in plan['roles'] if role['kind'] == 'spacing' and role['native_value'] > 0), None)
    used_properties = [props for screen in data['screens'] for element in screen['elements'] if element['kind'] == 'component'
                       for props in [data['components'][element['component']]['variants'][element['variant']]]]
    def auxiliary(properties, purpose):
        for props in used_properties:
            for prop, path in props.items():
                if prop in properties:
                    scalar_type, scalar = variable_value(data['tokens'][path])
                    if scalar_type == 'FLOAT' and scalar > 0:
                        return {'token': path.replace('.', '/'), 'native_value': scalar}
        raise ValueError('Actual used positive numeric source ' + purpose + ' token required for native documentation')
    auxiliary_type = base_type or auxiliary({'fontSize', 'font-size'}, 'font-size')
    auxiliary_space = base_space or auxiliary({'padding', 'padding-inline', 'padding-block', 'gap'}, 'spacing')
    base_ink = next((role for role in plan['roles'] if role['kind'] == 'color' and re.search(r'text|ink|foreground', role['name'] + role['token'], re.I)), next(role for role in plan['roles'] if role['kind'] == 'color'))
    for role in plan['roles']:
        consumers = []
        def add(key, field):
            item = {'key': key, 'field': field}
            if item not in consumers:
                consumers.append(item)
        for screen in data['screens']:
            if role is base_space:
                add(screen['id'], 'paddingTop')
            for index, element in enumerate(screen['elements']):
                identity = element.get('id', f"{screen['id']}/element:{index}")
                props = data['components'][element['component']]['variants'][element['variant']] if element['kind'] == 'component' else {}
                label = identity + '/label' if element['kind'] == 'component' else identity
                if role is base_type and not any(p in props for p in ('fontSize', 'font-size')):
                    add(label, 'fontSize')
                if role is base_ink and 'color' not in props:
                    add(label, 'fills')
                final_padding = {}
                for prop, path in props.items():
                    for field in {'padding':['paddingTop','paddingRight','paddingBottom','paddingLeft'], 'padding-inline':['paddingLeft','paddingRight'], 'padding-block':['paddingTop','paddingBottom'], 'gap':['itemSpacing']}.get(prop, []):
                        final_padding[field] = path
                if role is base_space and element['kind'] == 'component' and 'paddingTop' not in final_padding:
                    add(identity, 'paddingTop')
                for prop, path in props.items():
                    if path.replace('.', '/') != role['token']:
                        continue
                    if prop in ('padding', 'padding-inline', 'padding-block', 'gap'):
                        if role['kind'] == 'spacing':
                            for field, final_path in final_padding.items():
                                if final_path == path:
                                    add(identity, field)
                        continue
                    field = {'background':'fills','color':'fills','borderColor':'strokes','border-color':'strokes',
                             'fontSize':'fontSize','font-size':'fontSize','font-family':'fontFamily','padding':'paddingTop','gap':'itemSpacing',
                             'radius':'cornerRadius','cornerRadius':'cornerRadius','border-radius':'cornerRadius'}.get(prop)
                    supported = {'color': {'fills', 'strokes'}, 'typography': {'fontFamily'} if role['native_type'] == 'STRING' else {'fontSize'}, 'spacing': {'paddingTop', 'itemSpacing'}, 'radius': {'cornerRadius'}}
                    if field in supported[role['kind']]:
                        add(label if prop in ('color','fontSize','font-size','font-family') else identity, field)
        if not consumers:
            raise ValueError('Selected foundation role has no actual production-screen consumer: ' + role['token'])
        role['bindings'] = consumers
    canonical_components = {n['id'] for n in graph['nodes'] if n.get('type') == 'component'}
    for sample_index, sample in enumerate(plan['palette']['samples']):
        component, variant = sample['component'], sample['variant']
        if component not in canonical_components or variant not in data['components'].get(component, {}).get('variants', {}):
            raise ValueError('Selected palette component/variant is not authorable: ' + component + '/' + variant)
        interactive = any(e.get('component') == component and (e.get('action_id') or e.get('target_screen')) for screen in data['screens'] for e in screen['elements'])
        if interactive and (sample['action'] not in {n['id'] for n in graph['nodes'] if n.get('type') == 'action'} or sample['state'] not in {n['id'] for n in graph['nodes'] if n.get('type') == 'state'}):
            raise ValueError('Selected palette needs canonical action and functional state IDs')
        key = f'palette:{sample_index}:' + component + '/' + variant
        sample.update(instanceKey=key, mainComponentKey='component:' + component + '/' + variant,
                      componentSetKey='component-set:' + component, labelKey=key + '/label', documentationKey=key + '/documentation')
    if set(data['components']) != {sample['component'] for sample in plan['palette']['samples']}:
        raise ValueError('Every resolved component requires selected discoverable palette coverage')
    plan['palette']['libraryKey'] = 'foundation-palette'
    required = {note['target_id']: '\n'.join([str(note[key]) for key in ('purpose', 'behavior', 'precondition', 'result', 'failure', 'design_choice', 'journey', 'first_action', 'action', 'visual_variant') if note.get(key)] + note.get('functional_states', [])) for note in notes}
    for screen in data['screens']:
        for index, element in enumerate(screen['elements']):
            if element['kind'] == 'component' and not element.get('action_id') and not element.get('target_screen'):
                identity = element.get('id', f"{screen['id']}/element:{index}")
                sample = next(s for s in plan['palette']['samples'] if s['component'] == element['component'])
                required[identity] = 'Use: ' + '; '.join(sample['useCases']) + '\n' + required[screen['id']]
                element['static_annotation'] = required[identity]
    return {'roles': plan['roles'], 'auxiliary_type': auxiliary_type, 'auxiliary_space': auxiliary_space, 'samples': plan['palette']['samples'], 'expected': plan,
            'required_annotations': required, 'annotation_contract': {'mode': 'strict-creation', 'product_graph': graph, 'notes': notes}}


def compile_plugin(source, reviewed_sha256, out, plugin_id=None, *, local_sync=None, selection_path=None,
                   draft_only=False, product_graph=None, technical_existing=False, batch_path=None, asset_receipts=None):
    sys.path.insert(0, str(ROOT / 'tools'))
    from design_directions import require_selected, guard_production, pin, current
    from workflow import Event
    from embedded_assets import embedded_asset_warnings
    selected, graph, admission = None, None, None
    if technical_existing:
        if not local_sync or not plugin_id or not isinstance(local_sync.get('file_key'), str) or not local_sync['file_key'] or not re.fullmatch(r'[0-9]+:[0-9]+', str(local_sync.get('page_id', ''))):
            raise ValueError('Existing technical sync requires assigned plugin and exact native file/page pins')
    elif not draft_only:
        selected = require_selected(selection_path)
        if not product_graph or pin(product_graph)['sha256'] != selected['product_graph']['sha256']:
            raise ValueError('Production graph must match exact human-selected canonical product graph')
        admission = guard_production(selection_path, event=Event.HANDOFF_NATIVE, product_graph=product_graph,
                                     batch_path=batch_path, asset_receipts=asset_receipts)
        graph = read_json(current(selected['product_graph']))[1]
    raw, data = read_json(source)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != reviewed_sha256:
        raise ValueError('Reviewed SHA256 does not match the exact input bytes; review this payload first')
    values = validate(data)
    if plugin_id is not None and not re.fullmatch(r'\d+', plugin_id):
        raise ValueError('plugin-id must be the numeric ID assigned by Figma')
    if draft_only:
        if local_sync or technical_existing:
            raise ValueError('Draft output cannot pair or write a live Figma document')
        out = Path(out)
        out.mkdir()
        (out / 'draft-preview.json').write_text(json.dumps({'design': data, 'native_verified': False, 'limitations': 'Planned only; no installable plugin, native authoring or live sync.'}, ensure_ascii=True, indent=2) + '\n')
        return {'output': str(out.resolve()), 'status': 'draft-only-no-native-authoring', 'figma_import_verified': False}
    foundation = production_contract(data, graph) if graph else None
    native = handoff_contract(data)
    expected = expected_handoff(data)
    if foundation:
        native['required_annotations'] = foundation.pop('required_annotations')
        expected.update(mode='strict-creation', annotation_contract=foundation.pop('annotation_contract'), design_foundations=foundation['expected'],
                        required_annotations=native['required_annotations'])
        for screen in expected['screens']:
            for control in screen['controls']:
                if control.get('component_key') and not control['token_bindings']:
                    role = foundation['auxiliary_type']
                    control['token_bindings'].append({'node_key':control['key'] + '/label', 'property':'fontSize', 'variable':role['token']})
    if foundation:
        expected['design_note_board'] = {'required': True, 'key': 'design-note-board', 'entries': [
            {'key': key, 'target_key': key, 'label': label} for key, label in native['required_annotations'].items()]}
    payload = dict(data, source_sha256=digest, variable_values=values, native_handoff=native,
                   expected_native_handoff=expected, foundations=foundation,
                   technical_existing_only=technical_existing, selected_direction=selected, native_admission=admission)
    manifest = {'name': 'Figma Flow — Reviewed local design', 'api': '1.0.0', 'editorType': ['figma'],
                'main': 'code.js', 'ui': 'ui.html', 'documentAccess': 'dynamic-page',
                'networkAccess': {'allowedDomains': ['none']}, 'enablePrivatePluginApi': True}
    if plugin_id:
        manifest['id'] = plugin_id
    prefix = ''
    if local_sync is not None:
        if not plugin_id or not re.fullmatch(r'http://localhost:[0-9]+/sync', local_sync['url']) or not re.fullmatch(r'http://localhost:[0-9]+/', local_sync['preview_url']):
            raise ValueError('Paired development plugin requires fixed loopback endpoints and an assigned plugin ID.')
        manifest['name'] = 'Figma Flow · 앱에 반영 0.9'
        manifest['enablePrivatePluginApi'] = True
        manifest['networkAccess']['devAllowedDomains'] = [local_sync['url'].removesuffix('/sync'), local_sync['preview_url'].rstrip('/')]
        prefix = 'const LOCAL_SYNC = ' + json.dumps(local_sync, ensure_ascii=True) + ';\n'
    payload_json = json.dumps(payload, ensure_ascii=True, allow_nan=False)
    files = {'manifest.json': json.dumps(manifest, indent=2) + '\n',
             'reviewed-payload.json': json.dumps(payload, ensure_ascii=True, indent=2) + '\n',
             'expected-native-handoff.json': json.dumps(payload['expected_native_handoff'], ensure_ascii=True, indent=2) + '\n',
             'code.js': prefix + '\n'.join((ROOT / 'figma-bridge' / name).read_text() for name in ('semantic_tokens.js', 'foundation_palette.js', 'native_semantic_read.js', 'design_note_board.js')) + '\nconst PAYLOAD = ' + payload_json + ';\n' + (ROOT / 'figma-bridge/code.js').read_text(),
             'ui.html': (ROOT / 'figma-bridge/ui.html').read_text(),
             'README.md': (ROOT / 'figma-bridge/README.md').read_text()}
    out = Path(out)
    out.mkdir()  # A new directory is the output ownership boundary; never overwrite an existing build.
    for name, content in files.items():
        (out / name).write_text(content, encoding='utf-8')
    return {'output': str(out.resolve()), 'source_sha256': digest, 'screens': len(data['screens']),
            'variables': len(values), 'figma_import_verified': False, 'status': 'technical-existing-sync-only' if technical_existing else 'pending_native_handoff',
            'native_handoff_contract': str((out / 'expected-native-handoff.json').resolve()),
            'native_admission': admission, 'warnings': embedded_asset_warnings(payload_json),
            'manifest_identity': 'figma-assigned-id-supplied' if plugin_id else 'obtain-figma-id-before-import'}


def comparison_status(statuses):
    return next((status for status in ('changed', 'missing', 'unsupported') if status in statuses), 'match')


def observed_token(variable, mode, variables, collection_id, seen=()):
    if variable['id'] in seen:
        return 'unsupported', None
    if variable.get('variableCollectionId') != collection_id:
        return 'unsupported', None
    values = variable.get('valuesByMode')
    if not isinstance(values, dict) or mode not in values:
        return 'missing', None
    value = values[mode]
    if isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS':
        target = variables.get(value.get('id'))
        return observed_token(target, mode, variables, collection_id, (*seen, variable['id'])) if target else ('unsupported', None)
    return 'match', value


def same_variable_value(kind, expected, actual):
    if kind == 'FLOAT':
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isclose(expected, actual, rel_tol=1e-7, abs_tol=1e-7)
    if kind == 'COLOR':
        return isinstance(actual, dict) and all(isinstance(actual.get(key, 1 if key == 'a' else None), (int, float)) and
            math.isclose(value, actual.get(key, 1 if key == 'a' else None), rel_tol=1e-7, abs_tol=1e-7) for key, value in expected.items())
    return type(actual) is type(expected) and actual == expected


def compare_import(page, expected, digest, variables, collections, required_annotations=None):
    """Compare only this page and its declared collection; a stamp is not current-state evidence."""
    stamped = page.get('source_sha256') or page.get('declared_metadata', {}).get('source_sha256')
    result = {'page_id': page['id'], 'current_name': page.get('name'), 'source_sha256': stamped,
              'origin_stamp_match': stamped == digest}
    if stamped != digest:
        return dict(result, status='source-mismatch', current_state='not-compared')
    semantic = {}
    def collect(node, instance_label=None):
        identity = node.get('semantic_id') or node.get('declared_metadata', {}).get('semantic_id')
        # Instances inherit the main component's metadata. Only the explicitly retagged
        # label belongs to the instance and must still be checked for text and bindings.
        if instance_label is None or identity == instance_label:
            semantic.setdefault(identity, []).append(node)
        if node.get('type') == 'INSTANCE' and instance_label is None:
            instance_label = (identity or '') + '/label'
        for child in node.get('children', []):
            collect(child, instance_label)
    collect(page)
    def find(identity):
        candidates = semantic.get(identity, [])
        return (candidates[0], 'match') if len(candidates) == 1 else (None, 'unsupported' if candidates else 'missing')
    screens, elements = [], []
    for screen in expected['screens']:
        node, state = find(screen['id'])
        check = {'semantic_id': screen['id'], 'status': state, 'current_name': node.get('name') if node else None,
                 'expected_name': f"{screen['id']} · {screen['title']}"}
        if node:
            check['node_id'] = node['id']
            check['status'] = 'match' if node.get('name') == check['expected_name'] and node.get('type') == 'FRAME' else 'changed'
        screens.append(check)
        for index, element in enumerate(screen['elements']):
            identity = element.get('id', f"{screen['id']}/element:{index}")
            source_node, source_state = find(identity)
            item = {'semantic_id': identity, 'status': source_state, 'expected_text': element['text'],
                    'current_name': source_node.get('name') if source_node else None,
                    'declared_action_id': element.get('action_id'), 'action_execution': 'not-observed',
                    'expected_target_screen': element.get('target_screen')}
            if source_node:
                item['node_id'] = source_node['id']
                label = source_node
                if element['kind'] == 'component':
                    label, label_state = find(identity + '/label')
                else:
                    label_state = 'match'
                item['current_text'] = label.get('characters') if label else None
                text_state = label_state if not label else ('unsupported' if not isinstance(label.get('characters'), str) else
                             'match' if label['characters'] == element['text'] else 'changed')
                item['text_status'] = text_state
                reactions = source_node.get('reactions')
                actual_targets = []
                if isinstance(reactions, list):
                    for reaction in reactions:
                        if (reaction.get('trigger') or {}).get('type') != 'ON_CLICK':
                            continue
                        for action in reaction.get('actions', [reaction.get('action')] if reaction.get('action') else []):
                            if action.get('type') == 'NODE' and action.get('navigation') == 'NAVIGATE':
                                actual_targets.append(action.get('destinationId'))
                target, target_state = find(element['target_screen']) if element.get('target_screen') else (None, 'match')
                expected_targets = [target['id']] if target else []
                item['expected_native_targets'] = expected_targets
                item['current_native_targets'] = actual_targets
                item['navigation_status'] = target_state if target_state != 'match' else ('unsupported' if not isinstance(reactions, list) else
                                            'match' if actual_targets == expected_targets else 'changed')
                item['status'] = comparison_status([text_state, item['navigation_status']])
            elements.append(item)
    collection_id = page.get('declared_metadata', {}).get('collection_id') or page.get('collection_id')
    collection = collections.get(collection_id)
    owned_variables = [variable for variable in variables.values() if variable.get('variableCollectionId') == collection_id]
    # Compare only bindings the bridge attempts to create, including instance overrides.
    bindings = []
    numeric = {'radius': ['cornerRadius'], 'cornerRadius': ['cornerRadius'], 'border-radius': ['cornerRadius'],
               'padding': ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft'],
               'padding-inline': ['paddingLeft', 'paddingRight'], 'padding-block': ['paddingTop', 'paddingBottom'], 'gap': ['itemSpacing']}
    def check_bindings(identity, props):
        targets = {}
        for prop, path in props.items():
            kind, value = variable_value(expected['tokens'][path])
            if prop in ('background', 'color', 'borderColor', 'border-color') and kind == 'COLOR':
                targets[(identity + '/label' if prop == 'color' else identity, 'strokes' if prop in ('borderColor', 'border-color') else 'fills', 'color')] = path
            elif prop in numeric and kind == 'FLOAT' and value >= 0:
                for field in numeric[prop]:
                    targets[(identity, 'boundVariables', field)] = path
            elif prop in ('fontSize', 'font-size') and kind == 'FLOAT' and value > 0:
                targets[(identity + '/label', 'boundVariables', 'fontSize')] = path
            elif prop == 'font-family' and expected['tokens'][path]['type'] == 'fontFamily':
                targets[(identity + '/label', 'boundVariables', 'fontFamily')] = path
        for (node_id, container, field), path in targets.items():
            node, state = find(node_id)
            candidates = [variable for variable in owned_variables if (variable.get('semantic_id') or variable.get('declared_metadata', {}).get('semantic_id')) == path]
            actual = None
            if state == 'match' and len(candidates) != 1:
                state = 'missing' if not candidates else 'unsupported'
            elif state == 'match':
                value = node.get(container)
                if container == 'boundVariables':
                    actual = value.get(field) if isinstance(value, dict) else None
                    if node.get('type') == 'TEXT' and field in ('fontSize', 'fontFamily') and isinstance(actual, list):
                        if len(actual) == 1:
                            actual = actual[0]
                        else:
                            state = 'unsupported'
                    if field == 'cornerRadius' and isinstance(value, dict):
                        corners = ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius')
                        if any(corner in value for corner in corners):
                            actual = {corner: value.get(corner) for corner in corners}
                            expected_id = candidates[0]['id']
                            state = ('missing' if any(actual[corner] is None for corner in corners) else
                                     'match' if all(isinstance(actual[corner], dict) and
                                                    actual[corner].get('type') == 'VARIABLE_ALIAS' and
                                                    actual[corner].get('id') == expected_id for corner in corners) else 'changed')
                elif isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
                    paint_bindings = value[0].get('boundVariables')
                    actual = paint_bindings.get(field) if isinstance(paint_bindings, dict) else None
                elif value and (not isinstance(value, list) or len(value) != 1):
                    state = 'unsupported'
                if state == 'match' and not (container == 'boundVariables' and field == 'cornerRadius' and
                                             isinstance(actual, dict) and 'topLeftRadius' in actual):
                    state = ('missing' if actual is None else 'match' if isinstance(actual, dict) and
                             actual.get('type') == 'VARIABLE_ALIAS' and actual.get('id') == candidates[0]['id'] else 'changed')
            bindings.append({'semantic_id': node_id, 'property': container + '.' + field, 'token': path,
                             'status': state, 'current_binding': actual})
    for name, component in expected['components'].items():
        for variant, props in component['variants'].items():
            check_bindings(f'component:{name}/{variant}', props)
    for screen in expected['screens']:
        for index, element in enumerate(screen['elements']):
            if element['kind'] == 'component':
                identity = element.get('id', f"{screen['id']}/element:{index}")
                check_bindings(identity, expected['components'][element['component']]['variants'][element['variant']])
    tokens = []
    for path, token in expected['tokens'].items():
        candidates = [variable for variable in owned_variables if variable.get('semantic_id') == path or variable.get('declared_metadata', {}).get('semantic_id') == path]
        kind, expected_value = variable_value(token)
        check = {'token': path, 'expected_value': expected_value, 'expected_alias': token.get('alias'),
                 'status': 'missing' if not candidates or not collection else 'unsupported' if len(candidates) != 1 else 'match'}
        if check['status'] != 'match':
            tokens.append(check)
            continue
        variable = candidates[0]
        check.update(variable_id=variable['id'], current_name=variable.get('name'), current_type=variable.get('resolvedType'),
                     current_values_by_mode=variable.get('valuesByMode'), modes={})
        states = ['match' if variable.get('resolvedType') == kind and variable.get('name') == path.replace('.', '/') else 'changed']
        mode_ids = {mode.get('modeId') for mode in collection.get('modes', []) if isinstance(mode, dict)}
        mode_ids.update(variable.get('valuesByMode', {}))
        mode_ids.add(collection.get('defaultModeId'))
        if None in mode_ids:
            mode_ids.remove(None)
            states.append('unsupported')
        if not mode_ids:
            states.append('missing')
        alias = token.get('alias')
        alias_targets = [candidate for candidate in owned_variables if candidate.get('semantic_id') == alias or
                         candidate.get('declared_metadata', {}).get('semantic_id') == alias] if alias else []
        for mode in sorted(mode_ids):
            raw = variable.get('valuesByMode', {}).get(mode)
            raw_alias = raw.get('id') if isinstance(raw, dict) and raw.get('type') == 'VARIABLE_ALIAS' else None
            alias_state = ('missing' if len(alias_targets) != 1 else 'match' if raw_alias == alias_targets[0]['id'] else 'changed') if alias else ('changed' if raw_alias else 'match')
            value_state, observed = observed_token(variable, mode, variables, collection_id)
            if value_state == 'match' and not same_variable_value(kind, expected_value, observed):
                value_state = 'changed'
            state = comparison_status([alias_state, value_state])
            check['modes'][mode] = {'status': state, 'alias_status': alias_state, 'value_status': value_state,
                                    'current_alias_id': raw_alias, 'current_resolved_value': observed}
            states.append(state)
        check['status'] = comparison_status(states)
        tokens.append(check)
    annotations, component_usage = [], []
    required = handoff_contract(expected)['required_annotations']
    if required_annotations is not None:
        if (not isinstance(required_annotations, dict) or not required.keys() <= required_annotations.keys() or
                not all(isinstance(note, str) and note.strip() for note in required_annotations.values())):
            raise ValueError('Strict creation contract must supply text for every required annotation')
        required = required_annotations
    for identity, note in required.items():
        node, state = find(identity)
        labels = [item.get('label') for item in node.get('annotations', []) if isinstance(item, dict)] if node else []
        annotations.append({'semantic_id': identity, 'status': state if state != 'match' else
                            'match' if note in labels else 'missing'})
    for screen in expected['screens']:
        for index, element in enumerate(screen['elements']):
            if element['kind'] != 'component':
                continue
            identity = element.get('id', f"{screen['id']}/element:{index}")
            node, state = find(identity)
            main, main_state = find(f"component:{element['component']}/{element['variant']}")
            component_usage.append({'semantic_id': identity, 'status': comparison_status([state, main_state])
                if state != 'match' or main_state != 'match' else 'match' if node.get('type') == 'INSTANCE' and
                main.get('type') == 'COMPONENT' and node.get('main_component_id') == main['id'] else 'changed'})
    native_coverage = 'complete' if component_usage and all(any(
        check['semantic_id'] in (item['semantic_id'], item['semantic_id'] + '/label') for check in bindings)
        for item in component_usage) else 'partial'
    status = comparison_status([check['status'] for check in [*screens, *elements, *tokens, *bindings, *annotations, *component_usage]] +
                               (['unsupported'] if native_coverage != 'complete' else []))
    return dict(result, status=status, current_state=status, collection_id=collection_id,
                screen_checks=screens, element_checks=elements, token_checks=tokens, binding_checks=bindings,
                annotation_checks=annotations, component_usage_checks=component_usage,
                native_handoff_coverage='complete' if native_coverage == 'complete' and all(
                    check['status'] == 'match' for check in [*annotations, *component_usage, *bindings]) else 'partial',
                missing_screens=[check['semantic_id'] for check in screens if check['status'] == 'missing'])


def inspect_readback(path, source=None, expected_contract=None):
    _, data = read_json(path)
    if not isinstance(data, dict) or data.get('format') != 'figma-flow-readback-v1' or not isinstance(data.get('pages'), list) or not isinstance(data.get('variables'), list):
        raise ValueError('Expected a Figma Flow readback JSON export')
    nodes, identities = [], []
    def visit(node):
        if not isinstance(node, dict):
            raise ValueError('Invalid readback node')
        nodes.append(node)
        if node.get('semantic_id'):
            identities.append(node['semantic_id'])
        for child in node.get('children', []):
            visit(child)
    for page in data['pages']:
        visit(page)
    native_ids = [node.get('id') for node in nodes]
    if any(not isinstance(identity, str) or not identity for identity in native_ids) or len(native_ids) != len(set(native_ids)):
        raise ValueError('Readback requires unique current native node IDs')
    node_ids = set(native_ids)
    if any(not isinstance(variable, dict) for variable in data['variables']):
        raise ValueError('Invalid readback variable')
    for node in nodes:
        reactions = node.get('reactions', [])
        if not isinstance(reactions, list) or any(not isinstance(reaction, dict) for reaction in reactions):
            raise ValueError('Invalid readback reaction')
        for reaction in reactions:
            actions = reaction.get('actions', [reaction.get('action')] if reaction.get('action') else [])
            if not isinstance(actions, list) or any(not isinstance(action, dict) for action in actions):
                raise ValueError('Invalid readback reaction')
    variable_ids = {variable.get('id') for variable in data['variables']}
    if None in variable_ids or len(variable_ids) != len(data['variables']):
        raise ValueError('Readback requires unique variable IDs')
    collections = data.get('collections', [])
    if not isinstance(collections, list) or any(not isinstance(collection, dict) or not isinstance(collection.get('id'), str) for collection in collections):
        raise ValueError('Readback collections require native IDs')
    if len({collection['id'] for collection in collections}) != len(collections):
        raise ValueError('Readback collection IDs must be unique')
    external_targets = []
    missing_variable_references = set()
    def variable_references(value):
        if isinstance(value, dict):
            if value.get('type') == 'VARIABLE_ALIAS' and value.get('id') not in variable_ids:
                missing_variable_references.add(str(value.get('id')))
            for child in value.values():
                variable_references(child)
        elif isinstance(value, list):
            for child in value:
                variable_references(child)
    for node in nodes:
        variable_references(node.get('boundVariables', {}))
        variable_references(node.get('fills', []))
        variable_references(node.get('strokes', []))
        for reaction in node.get('reactions', []):
            for action in reaction.get('actions', [reaction.get('action')] if reaction.get('action') else []):
                target = action.get('destinationId')
                if target and target not in node_ids:
                    external_targets.append(target)
    for variable in data['variables']:
        variable_references(variable.get('valuesByMode', {}))
    source_match = None
    origin_match = None
    import_checks = []
    missing_screens = []
    contract = read_json(expected_contract)[1] if expected_contract is not None else None
    if source:
        raw, expected = read_json(source)
        validate(expected)
        digest = hashlib.sha256(raw).hexdigest()
        collection_map = {collection['id']: collection for collection in data.get('collections', [])}
        variable_map = {variable['id']: variable for variable in data['variables']}
        sys.path.insert(0, str(ROOT / 'tools'))
        from native_handoff import evaluate
        selected_notes = contract.get('required_annotations') if isinstance(contract, dict) and contract.get('mode') == 'strict-creation' else None
        import_checks = [compare_import(page, expected, digest, variable_map, collection_map, selected_notes) for page in data['pages']]
        generated = expected_handoff(expected)
        for page, check in zip(data['pages'], import_checks):
            if not check['origin_stamp_match']:
                continue
            selected = dict(data, pages=[page])
            native = evaluate(selected, generated, page['id'])
            check['native_handoff'] = native
            if not native['passed']:
                check['status'] = comparison_status([check['status'], 'unsupported'])
                check['native_handoff_coverage'] = 'partial'
        matching = [check for check in import_checks if check['origin_stamp_match']]
        origin_match = bool(matching)
        source_match = bool(matching) and all(check['status'] == 'match' for check in matching)
        missing_screens = sorted({identity for check in matching for identity in check['missing_screens']})
    native_reports = [check['native_handoff'] for check in import_checks if 'native_handoff' in check]
    native_report = ({'status': 'passed' if all(item['passed'] for item in native_reports) else 'blocked',
                      'passed': all(item['passed'] for item in native_reports), 'page_reports': native_reports}
                     if native_reports else None)
    if expected_contract is not None:
        sys.path.insert(0, str(ROOT / 'tools'))
        from native_handoff import evaluate
        native_report = evaluate(data, contract)
        source_match = source_match is True and native_report['passed']
    return {'native_handoff': native_report, 'generated_expected_contract': expected_handoff(expected) if source else None, 'native_handoff_coverage': ('complete' if source_match else 'partial') if source else 'partial-historical-inspection',
            'pages': len(data['pages']), 'nodes': len(nodes), 'variables': len(data['variables']),
            'reactions': sum(len(node.get('reactions', [])) for node in nodes),
            'semantic_ids': identities, 'source_sha256': sorted({page.get('source_sha256', '') for page in data['pages']}),
            'matches_supplied_source': source_match, 'external_reaction_targets': sorted(set(external_targets)),
            'origin_stamp_match': origin_match, 'import_checks': import_checks,
            'current_compared_state': (comparison_status([check['status'] for check in import_checks if check['origin_stamp_match']])
                                       if origin_match else 'source-mismatch') if source else None,
            'comparison_scope': 'Required native annotations and actual main-component instance links; per-import token values/aliases in all exported collection modes, screen names, element text, native click navigation and supported component/instance variable bindings; arbitrary visual edits are not compared',
            'external_variable_references': sorted(missing_variable_references),
            'missing_screens': missing_screens,
            'evidence': 'Local inspection of supplied export; does not authenticate Figma origin'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--reviewed-sha256')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--plugin-id')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--product-graph', type=Path)
    parser.add_argument('--draft-only', action='store_true')
    parser.add_argument('--batch', type=Path)
    parser.add_argument('--asset-receipts', type=Path)
    parser.add_argument('--inspect-readback', '--check-readback', type=Path)
    parser.add_argument('--require-match', action='store_true')
    parser.add_argument('--expected', type=Path, help='Additional native-ID-pinned handoff contract for native_handoff.evaluate')
    args = parser.parse_args()
    try:
        if args.expected and not args.inspect_readback:
            raise ValueError('--expected requires --inspect-readback')
        if args.require_match and (not args.inspect_readback or not args.input):
            raise ValueError('--require-match requires --inspect-readback and --input')
        if args.inspect_readback:
            if any((args.out, args.reviewed_sha256, args.plugin_id)):
                raise ValueError('Use --inspect-readback separately from compilation; --input can specify the known resolved source')
            result = inspect_readback(args.inspect_readback, args.input, args.expected)
        else:
            if not all((args.input, args.out, args.reviewed_sha256)):
                raise ValueError('Compilation requires --input, --reviewed-sha256 and a fresh --out directory')
            result = compile_plugin(args.input, args.reviewed_sha256, args.out, args.plugin_id, selection_path=args.selection, product_graph=args.product_graph, draft_only=args.draft_only, batch_path=args.batch, asset_receipts=args.asset_receipts)
        print(json.dumps(result, ensure_ascii=True))
        if args.require_match and result['matches_supplied_source'] is not True:
            return 1
    except (ValueError, OSError, TypeError, RecursionError) as error:
        print(f'figma-bridge: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
