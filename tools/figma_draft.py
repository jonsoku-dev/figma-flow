#!/usr/bin/env python3
"""Prepare and verify exploratory Figma directions. Never selects or approves one."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import secrets
import re
import shutil
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS=Path(__file__).resolve().parent
if str(TOOLS) not in sys.path: sys.path.insert(0,str(TOOLS))
from embedded_assets import embedded_asset_warnings
from plugin_panel import render_panel
import annotation_contract
from specification_contract import spec_label_prelude
from draft_foundation_audit import audit_draft_foundations
from draft_token_plan import foundation_bindings
import design_directions
import design_quality

PLUGIN=TOOLS.parent
HELPERS=('semantic_tokens.js','native_annotations.js','native_semantic_read.js','foundation_palette.js','design_note_board.js')
PRIVATE=Path.home()/'Library/Application Support/Figma Flow/night-editions'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def review_plugin_code(packet_json, helpers, review_source):
    """Keep const DRAFT first so workspace review parsing can raw-decode the packet."""
    production = ('var FLOW_PRODUCTION_SCHEMA = ' + json.dumps(PRODUCTION_SCHEMA) + ';\n'
                  'var FLOW_PRODUCTION_READBACK = ' + json.dumps(PRODUCTION_READBACK) + ';\n')
    return 'const DRAFT=' + packet_json + ';\n' + spec_label_prelude() + production + helpers + '\n' + review_source

def canonical_sha(value): return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def now(): return datetime.now(timezone.utc).isoformat()
def write_json(path,value): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def checked_review(manifest):
    result=design_directions.validate_draft(Path(manifest),require_native_review=False)
    data=result['data']
    counts = (1,) if data.get('mode') == 'direct' else (2, 3)
    if data.get('scope')!='exploratory-only' or len(data['candidates']) not in counts:
        raise ValueError('Checked exploratory candidate count differs from the requested direction mode')
    for candidate in data['candidates']:
        for field in ('source','review','product_graph'):
            design_directions.current(candidate[field])
        for preview in candidate['previews']: design_directions.current(preview['file'])
    return data




BASE_LAYER=('id','kind','x','y','w','h')
LAYER_FIELDS={'text':BASE_LAYER+('value','size','leading','ink','font','align','letter_spacing','max_lines'),
              'rect':BASE_LAYER+('fill','radius','stroke','stroke_width','opacity','role','shadows'),
              'ellipse':BASE_LAYER+('fill','stroke','stroke_width','opacity','role','shadows'),
              'gradient':BASE_LAYER+('direction','stops','opacity','role'),
              'image':BASE_LAYER+('asset','fit','opacity','role')}
LAYER_ROLES={'background','surface','illustration','image','divider','ornament','frame'}
IMAGE_FITS={'FILL','FIT','CROP','TILE'}


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def check_shadows(shadows, where):
    """Keep authored CSS shadow geometry explicit before constructing native effects."""
    if not isinstance(shadows, list):
        raise ValueError("shadows must be an ordered array: " + where)
    fields = {"x", "y", "blur", "spread", "color", "opacity"}
    for index, shadow in enumerate(shadows):
        valid = (
            isinstance(shadow, dict)
            and set(shadow) == fields
            and all(_finite(shadow[field]) for field in ("x", "y", "blur", "spread", "opacity"))
            and shadow["blur"] >= 0
            and 0 <= shadow["opacity"] <= 1
            and isinstance(shadow["color"], str)
            and re.fullmatch(r"#[0-9a-fA-F]{6}", shadow["color"])
        )
        if not valid:
            raise ValueError(
                f"Invalid shadows[{index}] at {where}; require finite x/y/blur/spread, blur >= 0, #RRGGBB color and opacity in [0, 1]"
            )

def check_layer(layer,colors,assets,key):
    """Reject an authored layer before any Figma write unless every property is declared and in range."""
    where=key+'.'+str(layer.get('id','?'))if isinstance(layer,dict)else key
    if not isinstance(layer,dict)or layer.get('kind')not in LAYER_FIELDS:raise ValueError('Only declared native draft layer kinds allowed: '+where)
    kind=layer['kind'];extra=set(layer)-set(LAYER_FIELDS[kind])
    if extra:raise ValueError('Undeclared native draft layer property '+', '.join(sorted(extra))+' at '+where)
    if not isinstance(layer.get('id'),str)or not layer['id']or not all(_finite(layer.get(k))for k in('x','y','w','h'))or layer['w']<=0 or layer['h']<=0:raise ValueError('Finite positive native layer geometry required: '+where)
    if 'role'in layer and layer['role']not in LAYER_ROLES:raise ValueError('Unknown native layer role '+repr(layer['role'])+' at '+where)
    if 'opacity'in layer and not(_finite(layer['opacity'])and 0<layer['opacity']<=1):raise ValueError('Native layer opacity must be within (0, 1]: '+where)
    if kind == "text":
        if "leading" in layer and not (_finite(layer["leading"]) and layer["leading"] > 0):
            raise ValueError("leading must be finite and positive: " + where)
        if "letter_spacing" in layer and not _finite(layer["letter_spacing"]):
            raise ValueError("letter_spacing must be finite pixels: " + where)
        if "max_lines" in layer and not (type(layer["max_lines"]) is int and layer["max_lines"] > 0):
            raise ValueError("max_lines must be a positive integer: " + where)
        if layer.get("align", "left") not in ("left", "center", "right", "justified"):
            raise ValueError("Unsupported text alignment: " + where)
    if kind in('rect','ellipse'):
        if 'shadows' in layer:
            check_shadows(layer['shadows'], where)
        if layer.get('fill')not in colors:raise ValueError('Declared color role required for fill at '+where)
        thin=min(layer['w'],layer['h'])/2
        if ('stroke'in layer)!=('stroke_width'in layer):raise ValueError('stroke and stroke_width must be declared together: '+where)
        if 'stroke'in layer:
            if layer['stroke']not in colors:raise ValueError('Declared color role required for stroke at '+where)
            if not(_finite(layer['stroke_width'])and 0<layer['stroke_width']<=thin):raise ValueError('stroke_width must be within (0, min(w,h)/2]: '+where)
        if 'radius'in layer and not(_finite(layer['radius'])and 0<=layer['radius']<=thin):raise ValueError('radius must be within [0, min(w,h)/2]: '+where)
    elif kind=='image':
        if layer.get('asset')not in assets:raise ValueError('Pinned raster asset required at '+where)
        if 'fit'in layer and layer['fit']not in IMAGE_FITS:raise ValueError('Image fit must be one of FILL, FIT, CROP, TILE (Figma scaleMode): '+where)
    elif kind=='gradient':
        stops=layer.get('stops')
        if layer.get('direction','vertical')not in('horizontal','vertical'):raise ValueError('Gradient direction must be horizontal or vertical: '+where)
        if not isinstance(stops,list)or len(stops)<2 or not all(isinstance(stop,dict)for stop in stops):raise ValueError('Gradient needs at least two stops: '+where)
        last=0
        for stop in stops:
            if set(stop)!={'position','color','opacity'}or not isinstance(stop['color'],str)or not re.fullmatch(r'#[0-9a-fA-F]{6}',stop['color'])or not all(_finite(stop[k])and 0<=stop[k]<=1 for k in('position','opacity'))or stop['position']<last:
                raise ValueError('Gradient stops need #RRGGBB color, opacity and non-decreasing position in [0, 1]: '+where)
            last=stop['position']


def check_control_icon(style, assets, key):
    if 'justifyContent' in style and style['justifyContent'] not in ('center', 'space-between'):
        raise ValueError('Control justifyContent must be center or space-between: ' + key)
    icon = style.get('icon')
    if icon is None:
        if style.get('justifyContent') == 'space-between':
            raise ValueError('Control space-between requires a label and icon: ' + key)
        if 'icon' in style:
            raise ValueError('Explicit control icon object required: ' + key)
        return
    if (not isinstance(icon, dict) or set(icon) != {'asset', 'placement', 'width', 'height', 'gap'}
            or icon.get('asset') not in assets or assets[icon['asset']].get('reference')
            or icon.get('placement') not in ('before', 'after')
            or any(not _finite(icon.get(k)) or icon[k] <= 0 for k in ('width', 'height'))
            or not _finite(icon.get('gap')) or icon['gap'] < 0):
        raise ValueError('Pinned non-reference raster control icon with placement/width/height/gap required: ' + key)
    if _finite(style.get('maxWidth')) and _finite(style.get('paddingX')) and icon['width'] + icon['gap'] >= style['maxWidth'] - 2 * style['paddingX']:
        raise ValueError('Control icon leaves no padded label width: ' + key)


def layout_errors(authored):
    """Every authored-layout problem at once (before any packet or Figma write), not only the first."""
    problems=[]
    rows=authored.get('candidates')
    rows=list(rows.values())if isinstance(rows,dict)else rows if isinstance(rows,list)else[]
    assets=authored.get('assets')if isinstance(authored.get('assets'),dict)else{}
    for c in rows:
        if not isinstance(c,dict):problems.append('candidate row must be an object');continue
        cid=str(c.get('id','?'));colors=c.get('colors')if isinstance(c.get('colors'),dict)else{};fonts=c.get('fonts')if isinstance(c.get('fonts'),dict)else{}
        if not fonts.get('body'): problems.append(f'{cid}: required review annotation font role missing: body')
        for role,font in fonts.items():
            if not isinstance(font,dict)or not isinstance(font.get('family'),str)or not font['family']or not isinstance(font.get('style'),str)or not font['style']:problems.append(f'{cid}: font role {role} needs family and style')
        for viewport, styles in (c.get("control_styles") or {}).items():
            for variant, style in styles.items():
                key = f"{cid}.{viewport}.component.{variant}"
                if not isinstance(style, dict):
                    problems.append(key + ": control style must be an object")
                    continue
                try:
                    check_control_icon(style, assets, key)
                except (ValueError, TypeError) as error:
                    problems.append(str(error))
                if "shadows" in style:
                    try:
                        check_shadows(style["shadows"], key)
                    except ValueError as error:
                        problems.append(str(error))
                if style.get("font", "body") not in fonts:
                    problems.append(key + ": unknown control font role")
                for field in ("fontSize", "minHeight", "maxWidth"):
                    if not _finite(style.get(field)) or style[field] <= 0:
                        problems.append(key + ": " + field + " must be finite and positive")
                for field in ("paddingX", "paddingY", "radius"):
                    if not _finite(style.get(field)) or style[field] < 0:
                        problems.append(key + ": " + field + " must be finite and non-negative")
                if "leading" in style and not (_finite(style["leading"]) and style["leading"] > 0):
                    problems.append(key + ": leading must be finite and positive")
                if "letter_spacing" in style and not _finite(style["letter_spacing"]):
                    problems.append(key + ": letter_spacing must be finite pixels")
                if "stroke" in style:
                    if style["stroke"] not in colors:
                        problems.append(key + ": undeclared stroke color")
                    if not _finite(style.get("stroke_width", 1)) or style.get("stroke_width", 1) <= 0:
                        problems.append(key + ": stroke_width must be finite and positive")
                elif "stroke_width" in style:
                    problems.append(key + ": stroke_width requires stroke")
        for viewport,states in(c.get('state_layouts')or{}).items():
            for state_id,l in(states or{}).items():
                key=f'{cid}.{viewport}.{state_id}'
                if not isinstance(l,dict)or not all(_finite(l.get(k))and l[k]>0 for k in('width','height')):problems.append(key+': width/height must be finite and > 0');continue
                controls=set(l.get('control_boxes')or{});seen=set()
                products = l.get("product_buttons") or {}
                if not isinstance(products, dict):
                    problems.append(key + ": product_buttons must be an object")
                    products = {}
                for button_id, button in products.items():
                    where = key + "." + str(button_id)
                    if (
                        not isinstance(button_id, str)
                        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", button_id)
                        or button_id in controls
                    ):
                        problems.append(where + ": unique safe product button id required")
                    if not isinstance(button, dict) or set(button) != {"box", "variant", "label"}:
                        problems.append(where + ": product button requires box, variant and label")
                        continue
                    box = button["box"]
                    if (
                        not isinstance(box, list)
                        or len(box) != 4
                        or not all(_finite(v) for v in box)
                        or box[2] <= 0
                        or box[3] <= 0
                    ):
                        problems.append(where + ": finite positive product button geometry required")
                    if button["variant"] not in (c.get("control_styles", {}).get(viewport) or {}):
                        problems.append(where + ": unknown product button variant")
                    if not isinstance(button["label"], str) or not button["label"].strip():
                        problems.append(where + ": non-empty product button label required")
                for layer in l.get('layers')if isinstance(l.get('layers'),list)else[]:
                    try:check_layer(layer,colors,assets,key)
                    except ValueError as error:problems.append(str(error));continue
                    lid=layer['id']
                    if lid in seen:problems.append(f'{key}.{lid}: duplicate layer id')
                    if lid in controls or lid in products:problems.append(f'{key}.{lid}: layer id collides with control id')
                    seen.add(lid)
                    if layer['kind']=='text':
                        if not isinstance(layer.get('value'),str)or not layer['value'].strip()or not _finite(layer.get('size'))or layer['size']<=0:problems.append(f'{key}.{lid}: text needs a value and a positive size')
                        if(layer.get('font')or'body')not in fonts:problems.append(f"{key}.{lid}: unknown font role {layer.get('font')or'body'!r}")
                        if layer.get('ink')not in colors:problems.append(f"{key}.{lid}: undeclared ink {layer.get('ink')!r}")
    return problems


def _hex_map(value):
    """Compare color roles by name and value; HEX letter case is not a different color."""
    return {k:v.lower()for k,v in value.items()}if isinstance(value,dict)and all(isinstance(v,str)for v in value.values())else value


PRODUCTION_SCHEMA = 'figma-flow-native-selected-production-v1'
PRODUCTION_READBACK = 'figma-flow-native-selected-production-readback-v1'


def _production_diff(before, after, path=()):
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return [change for key in sorted(set(before) | set(after))
                for change in _production_diff(before.get(key), after.get(key), (*path, key))]
    return [{'path': list(path), 'before': before, 'after': after}]


def _production_layer_map(candidate, entry_state=None):
    candidate = json.loads(json.dumps(candidate))
    candidate.pop('graph', None)
    if 'layouts' in candidate:
        if not entry_state or any(layout != candidate['state_layouts'][viewport][entry_state] for viewport,layout in candidate['layouts'].items()):
            raise ValueError('Entry layouts mirror must equal canonical state layout')
        candidate.pop('layouts')
    for layouts in candidate['state_layouts'].values():
        for layout in layouts.values():
            rows = layout['layers']
            if len({row['id'] for row in rows}) != len(rows):
                raise ValueError('Unique selected-production layer IDs required')
            layout['layers'] = {row['id']: row for row in rows}
    return candidate


def _observed_production_geometry(request, path, expected):
    """Check a declared subpixel correction against its pinned actual DOM observation."""
    try:
        record = request['measurements'][path[1] + '|' + path[2]]
        data = json.loads(design_directions.current(record['source']).read_text())
        if data.get('viewport') != path[1] or data.get('state') not in path[2]:
            return False
        if len(path) == 6 and path[3] == 'layers':
            identity = record.get('layer_ids', {}).get(path[4], path[4])
            layers = data['layers'] + [{**row, 'id':row['id']+'-raster'} for row in data.get('svg_layers', [])]
            layer = next(row for row in layers if row['id'] == identity)
            actual = layer.get(path[5])
            return actual == expected or _finite(actual) and _finite(expected) and abs(actual-expected) <= .01
        if len(path) == 5 and path[3] == 'control_boxes':
            return data['control_boxes'][path[4]] == expected
        if len(path) == 4 and path[3] in ('width','height'):
            return data[path[3]] == expected
    except (KeyError, ValueError, OSError, StopIteration, TypeError):
        return False
    return False


def _selected_production_inputs(selected, reviewed, authored, layout_path, graph_path, request_path):
    if not request_path or not graph_path:
        raise ValueError('Selected production requires pinned --change-request and --product-graph')
    request = json.loads(Path(request_path).read_text())
    original_layout = design_directions.current(reviewed.get('native_layout') or reviewed['native_target']['layout'], Path(reviewed['project_root']))
    original = json.loads(original_layout.read_text())
    old = next(row for row in original['candidates'] if row['id'] == selected['candidate_id'])
    if authored.get('schema') != 'figma-flow-authored-native-production-v1' or authored.get('scope') != 'selected-production' or len(authored.get('candidates', [])) != 1:
        raise ValueError('Distinct single-candidate selected-production authored layout required')
    candidate = authored['candidates'][0]
    provenance = {'path': selected['selection_path'], 'sha256': selected['selection_sha256'],
                  'candidate_id': selected['candidate_id'], 'candidate_sha256': selected['candidate_sha256'],
                  'review_layout_sha256': sha(original_layout.read_bytes())}
    if authored.get('sourceSelection') != provenance or candidate.get('id') != selected['candidate_id']:
        raise ValueError('Production layout source selection differs from actual chosen candidate')
    graph_pin = design_directions.pin(graph_path)
    expected = {'schema': 'figma-flow-selected-production-change-v1', 'selection': {'path': selected['selection_path'], 'sha256': selected['selection_sha256']},
                'candidate_id': selected['candidate_id'], 'reviewed_layout': {'path': str(original_layout.resolve()), 'sha256': provenance['review_layout_sha256']},
                'production_layout': {'path': str(layout_path), 'sha256': sha(layout_path.read_bytes())}, 'production_graph': graph_pin}
    if any(request.get(key) != value for key, value in expected.items()):
        raise ValueError('Exact selected-production change-request source pins required')
    if not isinstance(request.get('categories'), list) or not request['categories'] or set(request['categories']) - {'contrast', 'sync'}:
        raise ValueError('Only explicitly authorized contrast/sync categories are supported')
    user = request.get('user', {})
    user_path = Path(user.get('path', '')).resolve()
    if not user_path.is_relative_to(design_directions.user_record_root().resolve()) or user_path.is_symlink() or not user_path.is_file():
        raise ValueError('Actual managed user turn required for production revision')
    message = next((row for row in design_directions._messages(user_path) if row['prefix_length'] == user.get('prefix_length')), None)
    directive = user.get('directive')
    human = selected.get('human', {})
    if (user_path != Path(human.get('path', '')).resolve()
            or user.get('prefix_length') < human.get('prefix_length', float('inf'))):
        raise ValueError('Production revision must come from the selected user conversation')

    if not message or message['role'] != 'user' or message['prefix_sha256'] != user.get('prefix_sha256') or not isinstance(directive, str) or len(directive.strip()) < 20 or directive not in message['text']:
        raise ValueError('Managed user prefix and literal production directive do not match')
    if any(not re.search(r'contrast|대비|명암|가독' if category == 'contrast' else r'sync|동기화|양방향|연동', directive, re.I)
           for category in request['categories']):
        raise ValueError('Managed directive must explicitly authorize each production change category')

    graph = json.loads(Path(graph_path).read_text())
    previous_graph = json.loads(design_directions.current(selected['product_graph']).read_text())
    if {k:v for k,v in graph.items() if k not in ('design_foundations','design_system')} != {k:v for k,v in previous_graph.items() if k not in ('design_foundations','design_system')}:
        raise ValueError('Selected graph nodes, edges, actions and prototype semantics must stay unchanged')
    if 'design_system' in graph:
        if 'sync' not in request['categories'] or 'design_system' in previous_graph and graph['design_system'] != previous_graph['design_system']:
            raise ValueError('Only explicitly authorized addition of selected-component design_system is supported')
        from graph_design_system import resolve_design_system
        resolve_design_system(graph)
        mains = {f"{selected['candidate_id']}.{viewport}.component.{variant}" for viewport,styles in candidate['control_styles'].items() for variant in styles}
        instances = {f"{selected['candidate_id']}.{edge['viewport']}.{edge['source_state']}.{edge['control_id']}" for edge in graph['draft_prototype']['bindings']}
        instances.update('review.palette.'+selected['candidate_id']+'.'+sample['component'] for sample in graph['design_foundations']['palette']['samples'])
        for component in graph['design_system']['components'].values():
            native = component.get('native', {})
            if not native.get('mainKeys') or not native.get('instanceKeys') or not set(native['mainKeys']) <= mains or not set(native['instanceKeys']) <= instances:
                raise ValueError('Production sync scope must use only selected candidate native component/instance keys')
    if candidate.get('graph') != graph_pin:
        raise ValueError('Production candidate must pin its actual production graph')
    prototype = graph['draft_prototype']
    entries = [state['id'] for state in prototype['states'] if state.get('entry')]
    entry = prototype.get('entry_state') or (entries[0] if len(entries) == 1 else prototype['states'][0]['id'])
    normalized_old, normalized_new = _production_layer_map(old, entry), _production_layer_map(candidate, entry)
    actual = _production_diff(normalized_old, normalized_new)
    declarations = request.get('changes')
    if not isinstance(declarations, list) or len({tuple(row.get('path', [])) for row in declarations}) != len(declarations):
        raise ValueError('Unique complete production delta declarations required')
    declared = {tuple(row['path']): row for row in declarations}
    if {tuple(row['path']) for row in actual} != set(declared):
        raise ValueError('Production deltas differ from declared authorization')
    new_rects = {}
    removed_surfaces = set()
    for delta in actual:
        path = tuple(delta['path']); declaration = declared[path]
        if any(declaration.get(key) != delta[key] for key in ('before', 'after')) or declaration.get('category') not in request['categories']:
            raise ValueError('Exact authorized before/after/category required')
        if declaration['category'] != 'contrast':
            raise ValueError('Sync authority does not permit visual layout edits')
        if len(path) in (5, 6) and path[0] == 'state_layouts' and path[3] == 'layers':
            viewport, state_id, layer_id = path[1], path[2], path[4]
            old_layout = old['state_layouts'][viewport][state_id]
            new_layout = candidate['state_layouts'][viewport][state_id]
            old_layers = {row['id']:row for row in old_layout['layers']}
            layer = next((row for row in new_layout['layers'] if row['id'] == layer_id), None)
            if layer is None:
                previous = old_layers.get(layer_id, {})
                if len(path) != 5 or previous.get('kind') != 'rect' or previous.get('role') != 'surface':
                    raise ValueError('Only obsolete contrast surface rectangles may be removed')
                removed_surfaces.add((viewport, state_id, layer_id))
                continue
            if len(path) == 5:
                if delta['before'] is not None or layer.get('kind') not in ('rect', 'gradient') or layer.get('role') not in ('surface','background'):
                    raise ValueError('Only a declared contrast surface may be added')
                if layer['kind'] == 'rect' and (layer.get('opacity', 1) != 1 or layer.get('fill') not in candidate['colors']):
                    raise ValueError('A backing RECT requires an opaque named fill')
                if layer['kind'] == 'gradient':
                    check_layer(layer, candidate['colors'], authored['assets'], 'authorized contrast gradient')

                targets = declaration.get('text_ids', [])
                if not targets or any(key not in old_layers or old_layers[key]['kind'] != 'text' for key in targets):
                    raise ValueError('New backing RECT must name existing text targets')
                bleed = 1 if layer.get('role') == 'background' else 0
                if layer['x'] < -bleed or layer['y'] < -bleed or layer['x'] + layer['w'] > new_layout['width']+bleed or layer['y'] + layer['h'] > new_layout['height']+bleed:
                    raise ValueError('Backing RECT exceeds its selected screen')
                for key in targets:
                    if not any(row['id'] == key for row in new_layout['layers']): raise ValueError('Selected original text cannot be removed')
                    text = old_layers[key]
                    if not (layer['x'] <= text['x'] and layer['y'] <= text['y'] and layer['x']+layer['w'] >= text['x']+text['w'] and layer['y']+layer['h'] >= text['y']+text['h']):
                        raise ValueError('Backing RECT must cover its exact existing text bounds')
                    if new_layout['layers'].index(layer) >= next(i for i,row in enumerate(new_layout['layers']) if row['id'] == key):
                        raise ValueError('Backing RECT must render behind its text')
                if layer['kind'] == 'rect':
                    new_rects[f"{selected['candidate_id']}.{viewport}.{state_id}.{layer_id}"] = layer['fill']
            elif path[-1] in ('x','y','w','h','leading') and _finite(delta['before']) and _finite(delta['after']) and abs(delta['before'] - delta['after']) <= 1 and _observed_production_geometry(request, path, delta['after']):
                pass
            elif (layer['kind'] == 'text' and path[-1] == 'w' and old_layers[layer_id].get('align', 'left') == 'left'
                  and 0 < delta['after'] <= delta['before']):
                pass
            elif not ((layer['kind'] == 'text' and path[-1] == 'ink') or (layer['kind'] in ('rect','ellipse') and path[-1] in ('fill','stroke','opacity'))):
                raise ValueError('Only existing text/backing contrast fields may change')
        elif len(path) == 2 and path[0] == 'references':
            if path[1] not in ('desktop','mobile') or not authored['assets'].get(delta['after'], {}).get('reference'):
                raise ValueError('Only pinned viewport reference screenshots may change')
        elif len(path) == 4 and path[0] == 'state_layouts' and path[3] in ('width','height') and _finite(delta['before']) and _finite(delta['after']) and abs(delta['before'] - delta['after']) <= 1 and _observed_production_geometry(request, path, delta['after']):
            pass
        elif len(path) == 4 and path[0] == 'state_layouts' and path[3] == 'control_boxes':
            raise ValueError('Individual measured control boxes must remain named')
        elif len(path) == 5 and path[0] == 'state_layouts' and path[3] == 'control_boxes' and all(_finite(a) and _finite(b) and abs(a-b)<=1 for a,b in zip(delta['before'],delta['after'])) and len(delta['before'])==len(delta['after'])==4 and _observed_production_geometry(request, path, delta['after']):
            pass
        elif not (len(path) == 4 and path[0] == 'control_styles' and path[-1] in ('fill','ink','stroke')):
            raise ValueError('Selected production cannot change art, text, fonts, geometry or behavior')
    for viewport, layouts in old['state_layouts'].items():
        for state_id, layout in layouts.items():
            old_ids = [row['id'] for row in layout['layers'] if (viewport, state_id, row['id']) not in removed_surfaces]
            if [row['id'] for row in candidate['state_layouts'][viewport][state_id]['layers'] if row['id'] in old_ids] != old_ids:
                raise ValueError('Original selected layers and relative order must remain intact')
    old_foundations = previous_graph['design_foundations']; new_foundations = graph['design_foundations']
    if {k:v for k,v in old_foundations.items() if k != 'roles'} != {k:v for k,v in new_foundations.items() if k != 'roles'} or len(old_foundations['roles']) != len(new_foundations['roles']):
        raise ValueError('Only new actual color consumers may extend selected foundations')
    for before, after in zip(old_foundations['roles'], new_foundations['roles']):
        b, a = json.loads(json.dumps(before)), json.loads(json.dumps(after))
        old_bindings = b.get('native', {}).pop('bindings', []); new_bindings = a.get('native', {}).pop('bindings', [])
        if b != a or new_bindings[:len(old_bindings)] != old_bindings:
            raise ValueError('Selected foundation values and original consumers must be preserved')
        for binding in new_bindings[len(old_bindings):]:
            if before['kind'] != 'color' or binding.get('field') != 'fills' or new_rects.get(binding.get('key')) != before['token'].split('/')[-1]:
                raise ValueError('New foundation consumers must be authorized backing RECT fills')
    reference_changes = request.get('reference_assets', {})
    for name, asset in authored.get('assets', {}).items():
        previous = original['assets'].get(name)
        actual_path = (layout_path.parent/asset['path']).resolve()
        previous_path = (original_layout.parent/previous['path']).resolve() if previous else None
        if previous and {k:v for k,v in asset.items() if k != 'path'} == {k:v for k,v in previous.items() if k != 'path'}:
            continue
        if not previous or not previous.get('reference') or asset.get('reference') is not True or 'contrast' not in request['categories']:
            raise ValueError('Production must reuse the exact previously reviewed art assets')
        if {k:v for k,v in asset.items() if k not in ('path','sha256')} != {k:v for k,v in previous.items() if k not in ('path','sha256')}:
            raise ValueError('Reference replacement may only change screenshot file/hash')
        if reference_changes.get(name) != {'before':design_directions.pin(previous_path),'after':design_directions.pin(actual_path)}:
            raise ValueError('Exact original/new screenshot reference pins required')
    if any(name not in authored['assets'] or not authored['assets'][name].get('reference') for name in reference_changes):
        raise ValueError('Reference authority cannot replace campaign art')
    return provenance, graph_pin, design_directions.pin(request_path)


def make_packet(manifest,layout_path=None,file_key=None,*,selection_path=None,product_graph=None,change_request=None):
    selected = design_directions.require_selected(selection_path) if selection_path else None
    if selected:
        if manifest and Path(manifest).resolve() != Path(selected['draft_path']).resolve(): raise ValueError('Production selection and review manifest differ')
        manifest = selected['draft_path']
    data=checked_review(manifest)
    reviewed = data
    if selected:
        data = json.loads(json.dumps(data)); data['candidates'] = [row for row in data['candidates'] if row['id'] == selected['candidate_id']]
    packet_hash=design_directions.review_packet_sha256(reviewed)
    content=json.loads(design_directions.current(data['content']).read_text())
    root=Path(data['project_root']).resolve();layout_record=data.get('native_layout')or data.get('native_target',{}).get('layout')
    if not layout_record:raise ValueError('Checked review must pin its owned authored native layout before packaging')
    pinned_layout=design_directions.current(layout_record,root).resolve()
    layout_path=Path(layout_path or pinned_layout).resolve()
    if not selected and layout_path!=pinned_layout:raise ValueError('Explicit layout differs from immutable reviewed layout pin')
    if root not in layout_path.parents: raise ValueError('Authored layout must belong to the reviewed project')
    authored=json.loads(layout_path.read_text());layout_hash=sha(layout_path.read_bytes())
    if not selected and (authored.get('schema')!=design_quality.LAYOUT_SCHEMA or authored.get('scope')!='exploratory-only'):raise ValueError('Explicit exploratory native layout required')
    provenance = graph_pin = request_pin = None
    if selected:
        provenance, graph_pin, request_pin = _selected_production_inputs(selected, reviewed, authored, layout_path, product_graph, change_request)
        quality = design_quality.evaluate(authored, layout_dir=root)
        if not quality['passed']:
            raise ValueError(design_quality.blocking_summary(quality, layout_path))

        data['candidates'][0]['product_graph'] = graph_pin
        source = authored['candidates'][0]
        for preview in data['candidates'][0]['previews']:
            name = source.get('references', {}).get(preview['viewport'])
            if name not in authored['assets'] or authored['assets'][name].get('reference') is not True: raise ValueError('Production reference screenshot required')
            preview['file'] = design_directions.pin((layout_path.parent/authored['assets'][name]['path']).resolve())
    problems=layout_errors(authored)
    if problems:raise ValueError('Authored layout invalid ('+str(len(problems))+'):\n- '+'\n- '.join(problems))
    target=data.get('native_target',{'mode':'current-design-file'})
    if target.get('mode')not in ('current-design-file','exact-file'):raise ValueError('Explicit current-design-file or exact-file native target required')
    if target['mode']=='exact-file':
        if file_key and file_key!=target.get('file_key'):raise ValueError('Explicit target differs from reviewed exact file')
        file_key=target.get('file_key')
    if file_key and not re.fullmatch(r'[A-Za-z0-9_-]+',file_key):raise ValueError('Safe exact target file key required')
    prepared_target={'mode':'exact-file','file_key':file_key}if file_key else{'mode':'current-design-file'}
    native_candidates={c['id']:c for c in authored['candidates']}
    if set(native_candidates)!={c['id']for c in data['candidates']}:raise ValueError('Layout candidate identities must match reviewed candidates')
    candidates=[];assets={};pins=[]
    for candidate in data['candidates']:
        graph=json.loads(design_directions.current(candidate['product_graph']).read_text());prototype=graph.get('draft_prototype')
        if not prototype or not prototype.get('states') or not prototype.get('bindings'): raise ValueError('Canonical native draft prototype states/returns required: '+candidate['id'])
        notes=annotation_contract.derive_notes(graph);by_node={n['id']:n for n in graph['nodes']};by_note={n['id']:n for n in notes}
        states={state['id']:state for state in prototype['states']}
        if not states or len(states)!=len(prototype['states']):raise ValueError('Unique canonical review states required')
        marked=[state['id']for state in states.values()if state.get('entry')]
        entry=prototype.get('entry_state')or(marked[0]if len(marked)==1 else next(iter(states)))
        if len(marked)>1 or entry not in states:raise ValueError('Unambiguous declared entry state required')
        def reached(edges,start):
            found={start};todo=[start]
            while todo:
                for other in edges.get(todo.pop(),[]):
                    if other not in found:found.add(other);todo.append(other)
            return found
        for viewport in ('desktop','mobile'):
            forward={};reverse={}
            for edge in prototype['bindings']:
                if edge['viewport']!=viewport:continue
                forward.setdefault(edge['source_state'],[]).append(edge['target_state']);reverse.setdefault(edge['target_state'],[]).append(edge['source_state'])
            if reached(forward,entry)!=set(states)or reached(reverse,entry)!=set(states):raise ValueError('Every canonical state must be reachable out and back in each viewport')
        for state in states.values():
            if by_node.get(state['id'],{}).get('type')!='state' or by_node.get(state['screen'],{}).get('type')!='screen': raise ValueError('State/screen must be canonical')
        for edge in prototype['bindings']:
            action=by_node.get(edge['action'],{});note=by_note.get(edge['action'],{})
            if action.get('type')!='action' or edge['source_state']not in states or edge['target_state']not in states or edge['viewport']not in('desktop','mobile'):
                raise ValueError('Canonical per-viewport prototype edge required')
            matches=[n for n in notes if n.get('action')==edge['action']and edge['control_id']in(set(n.get('control_ids',[]))|{n.get('control_id')})]
            if len(matches)!=1: raise ValueError('Control does not match canonical annotation')
        foundations=graph['design_foundations']
        if len((foundations.get('palette')or{}).get('samples')or[])<2:raise ValueError('Documented primary/secondary samples required: '+candidate['id'])
        colors={r['token'].split('/')[-1]:r['value']for r in foundations['roles']if r['kind']=='color'}
        source=native_candidates[candidate['id']]
        if source['graph']['sha256']!=candidate['product_graph']['sha256']or _hex_map(source.get('colors'))!=_hex_map(colors):raise ValueError('Authored layout graph/color roles mismatch')
        if not source.get('fonts')or not source.get('control_styles'):raise ValueError('Exact configured native fonts/control styles required')
        action_notes={edge['action']+'|'+edge['control_id']:next(n for n in notes if n.get('action')==edge['action']and edge['control_id']in(set(n.get('control_ids',[]))|{n.get('control_id')}))for edge in prototype['bindings']}
        for viewport in ('desktop','mobile'):
            if set(source['state_layouts'][viewport])!=set(states):raise ValueError('Exact canonical states required in every viewport')
            for state_id,state_layout in source['state_layouts'][viewport].items():
                expected_controls={e['control_id']for e in prototype['bindings']if e['viewport']==viewport and e['source_state']==state_id}
                if set(state_layout['control_boxes'])!=expected_controls:raise ValueError('Exact state control layout required')
                if not any(l['kind']=='text'for l in state_layout['layers']):raise ValueError('Editable text required; screenshots-only review is invalid')
                for layer in state_layout['layers']:
                    check_layer(layer,source['colors'],authored['assets'],f"{candidate['id']}.{viewport}.{state_id}")
                    if layer['kind']=='image'and authored['assets'][layer['asset']].get('reference'):raise ValueError('Browser screenshots may only be separate labeled references')
        refs={}
        for preview in candidate['previews']:
            names=[name for name,record in authored['assets'].items()if record.get('reference')and record['sha256']==preview['file']['sha256']]
            if len(names)!=1:raise ValueError('Exact labeled raster reference required')
            refs[preview['viewport']]=names[0]
        c={**source,'id':candidate['id'],'title':candidate['title'],'sha256':candidate['sha256'],'graph':graph,'notes':notes,'action_notes':action_notes,'action_labels':{node['id']:node['title']for node in graph['nodes']if node['type']=='action'},'foundations':foundations,'colors':colors,'prototype':prototype,'entry_state':entry,'references':refs}
        if data.get('mode') in ('direct', 'compare'):
            from specification_contract import derive_specifications
            specifications = derive_specifications(graph, source_graph_sha256=candidate['product_graph']['sha256'])
            if any(spec['trace']['status'] != 'complete' for spec in specifications):
                raise ValueError('Readable specifications need current graph requirement, acceptance and test links before native preparation')
            c['specifications'] = {spec['id']: spec for spec in specifications}
        c['foundationBindings'] = foundation_bindings(source, graph)
        candidates.append(c)
    used_assets = None
    if selected:
        used_assets = {name for candidate in candidates for name in candidate['references'].values()}
        for candidate in candidates:
            used_assets.update(layer['asset'] for layouts in candidate['state_layouts'].values() for layout in layouts.values() for layer in layout['layers'] if layer['kind'] == 'image')
            used_assets.update(style['icon']['asset'] for styles in candidate['control_styles'].values() for style in styles.values() if style.get('icon'))
    for name,record in authored['assets'].items():
        if used_assets is not None and name not in used_assets: continue
        path=(layout_path.parent/record['path']).resolve()
        if root not in path.parents or path.is_symlink()or sha(path.read_bytes())!=record['sha256']:raise ValueError('Pinned owned draft asset required')
        assets[name]=base64.b64encode(path.read_bytes()).decode();pins.append({'path':str(path),'sha256':record['sha256']})
    importer_hash=canonical_sha({name:sha((PLUGIN/'figma-bridge'/name).read_bytes())for name in (*HELPERS,'direction_review.js')})
    instance_hash=canonical_sha({'packet':packet_hash,'layout':layout_hash,'fileKey':file_key,'importer':importer_hash})
    packet = {'schema':'figma-flow-native-direction-review-v1','scope':'exploratory-only','production_admitted':False,'fileKey':file_key,'prepared_target':prepared_target,'instance_sha256':instance_hash,'importer_sha256':importer_hash,'layout_sha256':layout_hash,'layout_pin':{'path':str(layout_path),'sha256':layout_hash},'packet_sha256':packet_hash,'manifest':str(Path(manifest).resolve()),'candidate_pins':{c['id']:c['sha256']for c in candidates},'content':content,'candidates':candidates,'assets':assets,'input_pins':pins,'prepared_at':now(),'execution_status':'prepared-not-executed','boundary':'Reference images are raster; authored titles/body/controls/role palette are native editable nodes. No approval, final asset batch or reservation.'}
    if selected:
        packet.update(schema=PRODUCTION_SCHEMA, scope='selected-production', production_admitted=True,
            sourceSelection=provenance, production_graph=graph_pin, change_request=request_pin,
            excluded_candidates=[row['id'] for row in reviewed['candidates'] if row['id'] != selected['candidate_id']],
            boundary='Selected production authoring from exact reviewed art/layout plus pinned authorized contrast changes. Native readback is required; not a new design approval.')
        packet['packet_sha256'] = canonical_sha({'review': packet_hash, 'selection': provenance, 'graph': graph_pin, 'changes': request_pin})
        packet['instance_sha256'] = canonical_sha({'packet': packet['packet_sha256'], 'layout': layout_hash, 'fileKey': file_key, 'importer': importer_hash})
    return packet



def _native_shadow_findings(node, authored, layer):
    if "shadows" not in authored:
        return []
    shadows = authored["shadows"]
    effects = node.get("effects")
    message = "Read and restore declared native DROP_SHADOW effects in authored order, including geometry, visibility and RGBA color."
    finding = {"code": "shadow-drift", "layer": layer, "message": message}
    if not isinstance(effects, list) or len(effects) != len(shadows):
        return [finding]
    for effect, shadow in zip(effects, shadows):
        if not isinstance(effect, dict):
            return [finding]
        if (
            effect.get("type") != "DROP_SHADOW"
            or effect.get("visible") is not True
            or effect.get("blendMode") != "NORMAL"
            or effect.get("showShadowBehindNode") is not True
        ):
            return [finding]
        offset = effect.get("offset")
        color = effect.get("color")
        if not isinstance(offset, dict) or not isinstance(color, dict):
            return [finding]
        geometry = (
            (offset.get("x"), shadow["x"]),
            (offset.get("y"), shadow["y"]),
            (effect.get("radius"), shadow["blur"]),
            (effect.get("spread"), shadow["spread"]),
        )
        rgba = {
            channel: int(shadow["color"][start : start + 2], 16) / 255
            for channel, start in (("r", 1), ("g", 3), ("b", 5))
        }
        rgba["a"] = shadow["opacity"]
        if any(
            not _finite(actual) or abs(actual - expected) > 0.001 for actual, expected in geometry
        ):
            return [finding]
        if any(
            not _finite(color.get(channel)) or abs(color[channel] - expected) > 0.0001
            for channel, expected in rgba.items()
        ):
            return [finding]
    return []

def _native_visibility_findings(node, layer):
    """Older supplied reports may omit opacity; explicit hidden/invalid values never pass."""
    visible = node.get("visible", True)
    opacity = node.get("opacity", 1)
    if visible is not True or not _finite(opacity) or not 0 < opacity <= 1:
        return [
            {
                "code": "visibility-drift",
                "layer": layer,
                "message": "Restore a visible native element with positive opacity (at most 1).",
            }
        ]
    return []


def _native_readback_nodes(raw, packet):
    rows = raw.get("nodes")
    if not isinstance(rows, list):
        raise ValueError("Native readback nodes must be a list")
    required_keys = set()
    for candidate in packet["candidates"]:
        for viewport in ("desktop", "mobile"):
            for state in candidate["prototype"]["states"]:
                key = f"{candidate['id']}.{viewport}.{state['id']}"
                required_keys.add(key)
                layout = candidate.get("state_layouts", {}).get(viewport, {}).get(state["id"])
                if not layout:
                    continue
                required_keys.update(key + "." + layer["id"] for layer in layout["layers"])
                control_ids = set(layout.get("control_boxes") or {}) | set(
                    layout.get("product_buttons") or {}
                )
                for control_id in control_ids:
                    required_keys.update(
                        (key + "." + control_id, key + "." + control_id + ".label")
                    )
            for variant, style in candidate.get('control_styles', {}).get(viewport, {}).items():
                main_key = f"{candidate['id']}.{viewport}.component.{variant}"
                required_keys.add(main_key)
                if style.get('icon'):
                    required_keys.update((main_key + '.icon', main_key + '.label'))
            for state in candidate['prototype']['states']:
                layout = candidate.get('state_layouts', {}).get(viewport, {}).get(state['id'], {})
                for control_id in set(layout.get('control_boxes') or {}) | set(layout.get('product_buttons') or {}):
                    required_keys.add(f"{candidate['id']}.{viewport}.{state['id']}.{control_id}.icon")

    for candidate in packet['candidates']:
        for sample in candidate.get('foundations', {}).get('palette', {}).get('samples', []):
            key = 'review.palette.' + candidate['id'] + '.' + sample['component']
            required_keys.update((key, key + '.label', key + '.icon'))

    nodes, keyed = {}, {}
    for node in rows:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise ValueError("Every native readback node requires a non-empty string id")
        if node["id"] in nodes:
            raise ValueError("Duplicate native node id: " + node["id"])
        nodes[node["id"]] = node
        key = node.get("semanticKey")
        if key is None or key == "":
            continue
        if not isinstance(key, str):
            raise ValueError("Native semanticKey must be a string: " + node["id"])
        if key in required_keys and key in keyed:
            raise ValueError("Duplicate required native semantic key: " + key)
        keyed[key] = node
    return nodes, keyed


def _native_box(node):
    """Return only usable native geometry; mixed or missing readback values fail closed."""
    if not isinstance(node, dict):
        return None
    values = tuple(node.get(field) for field in ("x", "y", "width", "height"))
    if not all(_finite(value) for value in values):
        return None
    return values if values[2] > 0 and values[3] > 0 else None


def _native_leading(authored):
    multiplier = 1.07 if authored.get("font") == "display" else 1.55
    return authored.get("leading", math.ceil(authored["size"] * multiplier))


def _native_pixels(value, font_size):
    if not isinstance(value, dict) or not _finite(value.get("value")):
        return None
    if value.get("unit") == "PIXELS":
        return value["value"]
    if value.get("unit") == "PERCENT":
        return value["value"] * font_size / 100
    return None


def _native_text_findings(candidate, node, authored, layer, resize_mode='HEIGHT'):
    findings = []

    def add(code, message):
        findings.append({"code": code, "layer": layer, "message": message})

    expected_font = candidate["fonts"][authored.get("font", "body")]
    observed_font = node.get("fontName")
    observed_font = observed_font if isinstance(observed_font, dict) else {}
    observed_axes = observed_font.get("variationSettings")
    observed_axes = observed_axes if isinstance(observed_axes, dict) else {}
    font_matches = (
        all(observed_font.get(field) == expected_font[field] for field in ("family", "style"))
        and all(
            observed_axes.get(axis) == value
            for axis, value in expected_font.get("variationSettings", {}).items()
        )
        and _finite(node.get("fontSize"))
        and abs(node["fontSize"] - authored["size"]) <= 0.001
    )
    if (
        node.get("type") != "TEXT"
        or node.get("characters") != authored["value"]
        or not font_matches
    ):
        add(
            "text-font-drift",
            "Restore authored editable characters, font family/style/axes and size.",
        )

    leading = _native_leading(authored)
    for field, expected in (
        ("lineHeight", leading),
        ("letterSpacing", authored.get("letter_spacing", 0)),
    ):
        pixels = _native_pixels(node.get(field), authored["size"])
        if pixels is None or abs(pixels - expected) > 0.01:
            add("text-" + field + "-drift", f"Read and restore {field} to {expected:g}px.")

    alignment = authored.get("align", "left").upper()
    if node.get("textAlignHorizontal") != alignment:
        add("text-alignment-drift", "Read and restore textAlignHorizontal=" + alignment + ".")
    if node.get("textAutoResize") != resize_mode:
        add("text-resize-drift", "Restore the authored " + resize_mode + " text auto-resize mode.")
    height = node.get("height")
    if "max_lines" in authored and _finite(height) and height > leading * authored["max_lines"] + 1:
        add(
            "text-max-lines",
            f"Rendered text exceeds max_lines={authored['max_lines']}; widen its allocation or shorten the text.",
        )
    return findings


def _native_palette_label_findings(parent, label, main, main_label, component_set, expected, key):
    main_ref = (main_label.get('componentPropertyReferences') or {}).get('characters')
    reference = (label.get('componentPropertyReferences') or {}).get('characters')
    definitions = component_set.get('componentPropertyDefinitions') or {}
    properties = parent.get('componentProperties') or {}
    actual = properties.get(main_ref, {})
    if (parent.get('type') != 'INSTANCE' or main.get('type') != 'COMPONENT'
            or parent.get('mainComponentId') != main.get('id') or main.get('componentSetId') != component_set.get('id')
            or label.get('type') != 'TEXT' or label.get('parentId') != parent.get('id') or label.get('characters') != expected
            or not isinstance(main_ref, str) or definitions.get(main_ref, {}).get('type') != 'TEXT'
            or actual.get('type') != 'TEXT' or actual.get('value') != expected
            or reference is not None and reference != main_ref):
        return [{'code': 'palette-label-drift', 'layer': key + '.label',
                 'message': 'Restore the authored action label, exact reusable main and its exposed TEXT property value.'}]
    return []


def _native_control_fill_findings(node, style, key):
    if 'fill' in style and style['fill'] is None and (node.get('fills') != [] or (node.get('boundVariables') or {}).get('fills')):
        return [{'code': 'control-fill-drift', 'layer': key, 'message': 'Explicit null control fill requires empty native fills and no fill variable.'}]
    return []


def _native_control_icon_findings(parent, label, icon_node, style, key, assets):
    spec = style.get('icon')
    if not spec:
        return []
    findings = []
    if 'justifyContent' in style and parent.get('primaryAxisAlignItems') != ('SPACE_BETWEEN' if style['justifyContent'] == 'space-between' else 'CENTER'):
        findings.append({'code': 'control-alignment-drift', 'layer': key, 'message': 'Restore the explicit control primary axis alignment.'})
    def add(code, message):
        findings.append({'code': code, 'layer': key + '.icon', 'message': message})
    if 'justifyContent' in style:
        for field, expected in [('paddingLeft', style['paddingX']), ('paddingRight', style['paddingX']), ('paddingTop', style['paddingY']), ('paddingBottom', style['paddingY'])]:
            if not _finite(parent.get(field)) or abs(parent[field] - expected) > 1:
                add('control-padding-drift', 'Restore the explicit control padding: ' + field)
    node = icon_node if isinstance(icon_node, dict) else {}
    box, label_box = _native_box(node), _native_box(label)
    if node.get('type') != 'RECTANGLE' or node.get('parentId') != parent.get('id') or box is None:
        add('control-icon-missing', 'Read the pinned raster icon inside the reusable control.')
        return findings
    findings.extend(_native_visibility_findings(node, key + '.icon'))
    fills = node.get('fills')
    paint = fills[0] if isinstance(fills, list) and len(fills) == 1 and isinstance(fills[0], dict) else {}
    if (paint.get('type') != 'IMAGE' or not paint.get('imageHash') or paint.get('scaleMode') != 'FIT'
            or paint.get('visible', True) is not True or paint.get('opacity', 1) != 1
            or node.get('controlIconAsset') != spec['asset']):
        add('control-icon-asset', 'Restore the exact pinned raster IMAGE paint with FIT scale mode.')
    try:
        observed = base64.b64decode(node.get('iconImageBytes', ''), validate=True)
        expected = base64.b64decode((assets or {})[spec['asset']], validate=True)
        if not observed or sha(observed) != sha(expected):
            raise ValueError('Raster bytes differ')
    except (ValueError, TypeError, KeyError):
        add('control-icon-asset', 'Read actual image bytes matching the pinned packet asset.')
    if label.get('textAutoResize') != 'WIDTH_AND_HEIGHT' or label.get('layoutSizingHorizontal') != 'HUG':
        add('control-icon-sizing', 'Restore intrinsic HUG text sizing on the reusable main, without fixed instance label widths.')
    ix, iy, iw, ih = box
    if abs(iw - spec['width']) > .01 or abs(ih - spec['height']) > .01:
        add('control-icon-geometry', 'Restore the exact icon width and height.')
    if label_box is None or label.get('parentId') != parent.get('id'):
        add('control-icon-group', 'Read the label alongside its icon in the same reusable control.')
    if label_box is not None:
        lx, ly, lw, lh = label_box
        width, height = parent.get('width'), parent.get('height')
        if not _finite(width) or not _finite(height):
            add('control-icon-geometry', 'Read finite control dimensions.')
            return findings
        gap = lx - ix - iw if spec['placement'] == 'before' else ix - lx - lw
        spacing = parent.get('itemSpacing')
        between = style.get('justifyContent') == 'space-between'
        if not _finite(spacing) or abs(spacing - spec['gap']) > .01 or (gap < spec['gap'] - 1 if between else abs(gap - spec['gap']) > 1):
            add('control-icon-gap', 'Restore the authored icon placement and gap.')
        left, right = min(ix, lx), max(ix + iw, lx + lw)
        px, py = style['paddingX'], style['paddingY']
        if (left < px - 1 or right > width - px + 1 or iy < py - 1 or iy + ih > height - py + 1
                or (abs(left - px) > 1 or abs(right - (width - px)) > 1 if between else abs((left + right) / 2 - width / 2) > 1)
                or abs(iy + ih / 2 - height / 2) > 1 or between and (abs(ly + lh / 2 - height / 2) > 1 or ly < py - 1 or ly + lh > height - py + 1)):
            add('control-icon-alignment', 'Restore the combined label/icon alignment inside the padded control.')
    return findings


def native_screen_findings(candidate, viewport, state_id, frame, keyed, page_id=None, assets=None):
    """Compare rendered native boxes with authored allocations, never estimated font widths."""
    key = f"{candidate['id']}.{viewport}.{state_id}"
    layout = candidate["state_layouts"][viewport][state_id]
    findings = []
    texts = []
    controls = []
    control_labels = []

    def add(code, layer, message):
        findings.append({"code": code, "layer": layer, "message": message})

    def geometry(node, expected, layer, height_budget=False, parent=None):
        actual = _native_box(node)
        if actual is None:
            add("geometry-missing", layer, "Read finite positive x/y/width/height from Figma.")
            return None
        if parent is not None and node.get("parentId") != parent:
            add("parent-drift", layer, "Restore the authored parent frame/control.")
        for index, field in enumerate(("x", "y", "width", "height")):
            overflow = field == "height" and height_budget
            differs = (
                actual[index] > expected[index] + 1
                if overflow
                else abs(actual[index] - expected[index]) > 1
            )
            if differs:
                remedy = (
                    " height budget; enlarge the allocation or fix wrapping."
                    if overflow
                    else "; restore the authored allocation."
                )
                add(
                    "text-overflow" if overflow else "geometry-drift",
                    layer,
                    f"Rendered {field} {actual[index]:g}px differs from authored {expected[index]:g}px"
                    + remedy,
                )
        return actual

    def off_canvas(box):
        x, y, width, height = box
        return max(-x, -y, x + width - layout["width"], y + height - layout["height"]) > 1

    findings.extend(_native_visibility_findings(frame, key))
    if page_id is not None and frame.get("parentId") != page_id:
        add(
            "parent-drift",
            key,
            "Restore the authored screen directly inside the owned review page.",
        )
    if _native_box(frame) is None:
        add("geometry-missing", key, "Read finite screen x/y and positive width/height from Figma.")

    for dimension in ("width", "height"):
        observed = frame.get(dimension)
        if not _finite(observed) or abs(observed - layout[dimension]) > 1:
            add("frame-size-drift", key, "Restore authored screen width/height.")
            break

    for layer in layout["layers"]:
        name = key + "." + layer["id"]
        node = keyed.get(name)
        if not isinstance(node, dict):
            add("layer-missing", name, "Read the authored editable native layer.")
            continue
        findings.extend(_native_visibility_findings(node, name))
        findings.extend(_native_shadow_findings(node, layer, name))
        is_text = layer["kind"] == "text"
        allocation = tuple(layer[field] for field in ("x", "y", "w", "h"))
        actual = geometry(node, allocation, name, height_budget=is_text, parent=frame["id"])
        if is_text:
            findings.extend(_native_text_findings(candidate, node, layer, name))
            if actual is not None and node.get("visible", True):
                texts.append((name, actual))
        allows_bleed = not is_text and layer.get("role") in design_quality.BLEED_ROLES
        if actual is not None and off_canvas(actual) and not allows_bleed:
            add(
                "off-canvas",
                name,
                "Rendered box leaves the screen; restore its position or enlarge the authored screen.",
            )

    control_specs = []
    for edge in candidate["prototype"]["bindings"]:
        if edge["viewport"] != viewport or edge["source_state"] != state_id:
            continue
        note = candidate["action_notes"][edge["action"] + "|" + edge["control_id"]]
        control_specs.append(
            (
                edge["control_id"],
                layout["control_boxes"][edge["control_id"]],
                note["visual_variant"],
                candidate["action_labels"][edge["action"]],
                False,
            )
        )
    for control_id, spec in (layout.get("product_buttons") or {}).items():
        control_specs.append((control_id, spec["box"], spec["variant"], spec["label"], True))

    for control_id, allocation, variant, label_value, is_product in control_specs:
        name = key + "." + control_id
        node = keyed.get(name)
        node = node if isinstance(node, dict) else {}
        findings.extend(_native_visibility_findings(node, name))
        actual = geometry(node, allocation, name, parent=frame["id"])
        if actual is not None:
            controls.append((name, actual))
            if off_canvas(actual):
                add(
                    "off-canvas",
                    name,
                    "Control leaves the screen; restore its authored allocation.",
                )

        style = candidate["control_styles"][viewport][variant]
        findings.extend(_native_shadow_findings(node, style, name))
        findings.extend(_native_control_fill_findings(node, style, name))
        main = keyed.get(candidate["id"] + "." + viewport + ".component." + variant)
        main = main if isinstance(main, dict) else {}
        if (
            node.get("type") != "INSTANCE"
            or main.get("type") != "COMPONENT"
            or node.get("mainComponentId") != main.get("id")
        ):
            add(
                "control-source-drift",
                name,
                "Restore the reusable " + variant + " component instance.",
            )
        radius = style["radius"]
        observed_radius = node.get("cornerRadius")
        if not _finite(observed_radius) or abs(observed_radius - radius) > 0.001:
            add("control-shape-drift", name, f"Restore the authored cornerRadius={radius:g}px.")
        if "stroke" in style:
            weight = node.get("strokeWeight")
            strokes = node.get("strokes")
            has_stroke = isinstance(strokes, list) and any(
                isinstance(paint, dict)
                and paint.get("type") == "SOLID"
                and paint.get("visible", True)
                for paint in strokes
            )
            if (
                not has_stroke
                or not _finite(weight)
                or abs(weight - style.get("stroke_width", 1)) > 0.001
            ):
                add(
                    "control-shape-drift",
                    name,
                    "Restore the authored visible stroke and stroke width.",
                )
        if is_product and node.get("reactions"):
            add(
                "product-control-reaction",
                name,
                "Product preview controls must not perform review navigation.",
            )
        if 'justifyContent' in style and node.get('primaryAxisAlignItems') != ('SPACE_BETWEEN' if style['justifyContent'] == 'space-between' else 'CENTER'):
            add('control-alignment-drift', name, 'Restore the explicit control primary axis alignment.')
        padding = {
            "paddingLeft": style["paddingX"],
            "paddingRight": style["paddingX"],
            "paddingTop": style["paddingY"],
            "paddingBottom": style["paddingY"],
        }
        for field, expected in padding.items():
            observed = node.get(field)
            if not _finite(observed) or abs(observed - expected) > 1:
                add("control-padding-drift", name, "Restore " + field + "=" + str(expected) + ".")

        label_name = name + ".label"
        label = keyed.get(label_name)
        label = label if isinstance(label, dict) else {}
        label_style = {
            "value": label_value,
            "size": style["fontSize"],
            "font": style.get("font", "body"),
            "align": "center",
            "max_lines": 1,
        }
        for field in ("leading", "letter_spacing"):
            if field in style:
                label_style[field] = style[field]
        findings.extend(_native_visibility_findings(label, label_name))
        findings.extend(_native_text_findings(candidate, label, label_style, label_name, resize_mode='WIDTH_AND_HEIGHT' if style.get('icon') else 'HEIGHT'))
        if "\n" in label_value or "\r" in label_value:
            add("text-max-lines", label_name, "Control labels must contain one line of text.")
        label_box = _native_box(label)
        if label_box is None or label.get("parentId") != node.get("id"):
            add(
                "control-label-missing",
                label_name,
                "Read the editable label inside its control instance.",
            )
        elif actual is not None:
            x, y, width, height = actual
            lx, ly, lw, lh = label_box
            px, py = style["paddingX"], style["paddingY"]
            control_labels.append((label_name, (x + lx, y + ly, lw, lh)))
            if lx < px - 1 or ly < py - 1 or lx + lw > width - px + 1 or ly + lh > height - py + 1:
                add(
                    "control-label-overflow",
                    label_name,
                    "Label exceeds the padded control; enlarge the authored control or shorten the label.",
                )
            if (not style.get('icon') and abs(lx + lw / 2 - width / 2) > 1) or abs(ly + lh / 2 - height / 2) > 1:
                add(
                    "control-label-alignment",
                    label_name,
                    "Center the rendered label within its control instance.",
                )

        if style.get('icon'):
            findings.extend(_native_control_icon_findings(node, label, keyed.get(name + '.icon'), style, name, assets))
            main_key = candidate['id'] + '.' + viewport + '.component.' + variant
            findings.extend(_native_control_icon_findings(main, keyed.get(main_key + '.label', {}), keyed.get(main_key + '.icon'), style, main_key, assets))

    rendered_texts = texts + control_labels
    for index, (name, box) in enumerate(rendered_texts):
        for other_name, other_box in rendered_texts[index + 1 :]:
            smaller_area = min(box[2] * box[3], other_box[2] * other_box[3])
            if (
                design_quality._intersection(box, other_box)
                > design_quality.OVERLAP_SHARE * smaller_area
            ):
                add(
                    "text-overlap",
                    other_name,
                    "Rendered text overlaps "
                    + name
                    + "; separate their allocations or fix wrapping.",
                )
    for name, box in texts:
        for control_name, control_box in controls:
            if design_quality._intersection(box, control_box) > 0:
                add(
                    "control-text-overlap",
                    name,
                    "Rendered text intersects " + control_name + "; move text outside the control.",
                )
    return findings

def _attested_review_packet(manifest_path, raw):
    packet = make_packet(manifest_path, raw.get('layout_pin', {}).get('path'), raw.get('prepared_target', {}).get('file_key'))
    # The sidecar preserves the actual selected manifest bytes and its original human hash.
    sidecar = Path(manifest_path).resolve().parent / 'renderer-snapshot.json'
    if not sidecar.exists():
        return packet
    snapshot = json.loads(design_directions.current(design_directions.pin(sidecar)).read_text())
    names = (*HELPERS, 'direction_review.js')
    if snapshot.get('schema') != 'figma-flow-native-renderer-snapshot-v1' or set(snapshot.get('sources', {})) != set(names):
        raise ValueError('Exact historical renderer source set required')
    sources = {name:design_directions.current(snapshot['sources'][name]).read_bytes() for name in names}
    original = json.loads(design_directions.current(snapshot['packet']).read_text())
    if original.get('schema') != 'figma-flow-native-direction-review-v1' or original.get('scope') != 'exploratory-only' or original.get('production_admitted') is not False:
        raise ValueError('Historical snapshot must be an original exploratory review packet')
    if original['importer_sha256'] != canonical_sha({name:sha(value) for name,value in sources.items()}):
        raise ValueError('Historical renderer implementation digest differs from exact archived sources')
    code = review_plugin_code(json.dumps(original, ensure_ascii=False), '\n'.join(sources[name].decode() for name in HELPERS), sources['direction_review.js'].decode())
    if design_directions.current(snapshot['code']).read_bytes() != code.encode():
        raise ValueError('Historical generated code does not exactly contain its attested packet and sources')
    instance = canonical_sha({'packet':original['packet_sha256'],'layout':original['layout_sha256'],'fileKey':original['fileKey'],'importer':original['importer_sha256']})
    if original['instance_sha256'] != instance:
        raise ValueError('Historical renderer instance digest is invalid')
    packet['prepared_at'] = original['prepared_at']
    ignored = {'importer_sha256', 'instance_sha256'}
    if {k:v for k,v in packet.items() if k not in ignored} != {k:v for k,v in original.items() if k not in ignored}:
        raise ValueError('Historical renderer logical candidate/layout/font/art/graph contract differs from current reviewed inputs')
    if raw.get('instance_sha256') != instance:
        raise ValueError('Actual readback does not belong to the attested original renderer')
    return original


def _verify_native_packet(packet,readback_path):
    report={'passed':False,'errors':[],'scope':packet['scope'],'production_admitted':packet['production_admitted'],'evidence':'supplied-native-readback-not-origin-authentication','screens':[],'layout_findings':[],'annotation_checks':[],'foundation_checks':[],'prototype_checks':[],'return_checks':[],'design_note_board_checks':[],'dev_mode_required':False}
    try:
        raw=json.loads(Path(readback_path).read_text())
        if isinstance(raw,dict) and raw.get('schema')=='figma-flow-native-geometry-failure-v1':
            raise ValueError('Native geometry failure diagnostics are not an admissible readback')
        nodes, keyed = _native_readback_nodes(raw, packet)
        if not raw.get('fileKey')or packet['fileKey']and raw.get('fileKey')!=packet['fileKey']or raw.get('instance_sha256')!=packet['instance_sha256'] or raw.get('packet_sha256')!=packet['packet_sha256'] or raw.get('candidate_pins')!=packet['candidate_pins'] or raw.get('scope')!=packet['scope']or raw.get('production_admitted')is not packet['production_admitted'] or raw.get('approved')is True: raise ValueError('Exact current checked draft inputs/file/scope required')
        if packet['scope'] == 'selected-production':
            if raw.get('schema') != PRODUCTION_READBACK or raw.get('sourceSelection') != packet['sourceSelection'] or raw.get('production_graph') != packet['production_graph'] or raw.get('change_request') != packet['change_request']:
                raise ValueError('Selected production native source/scope attestation missing')
            if set(raw.get('noteFrames', {})) != set(packet['candidate_pins']) or set(raw.get('palettes', {})) != set(packet['candidate_pins']):
                raise ValueError('Production page must contain only selected candidate notes and palette')
            for node in nodes.values():
                key = node.get('semanticKey') or node.get('key') or ''
                if any(key.startswith(other+'.') or key.startswith('review.palette.'+other+'.') for other in packet['excluded_candidates']):
                    raise ValueError('Unselected candidate found in production page')
        page=nodes.get(raw.get('pageId'),{});report.update(file_key=raw['fileKey'],page_id=raw['pageId'],packet_sha256=raw['packet_sha256'])
        if page.get('type')!='PAGE' or raw.get('page_owner')!=packet['instance_sha256']: raise ValueError('Owned draft root page required')
        for candidate in packet['candidates']:
            for viewport in ('desktop', 'mobile'):
                for state in candidate['prototype']['states']:
                    key = f"{candidate['id']}.{viewport}.{state['id']}"
                    frame = keyed.get(key)
                    if not frame or frame.get('type') != 'FRAME':
                        report['layout_findings'].append({
                            'code': 'frame-missing', 'layer': key,
                            'message': 'Read the actual editable screen frame inside the owned review page.',
                        })
                        continue
                    if frame and frame.get('type') == 'FRAME':
                        report['layout_findings'].extend(
                            native_screen_findings(candidate, viewport, state['id'], frame, keyed, page_id=raw['pageId'], assets=packet.get('assets', {}))
                        )
        for candidate in packet['candidates']:
            for viewport, styles in candidate['control_styles'].items():
                for variant, style in styles.items():
                    key = candidate['id'] + '.' + viewport + '.component.' + variant
                    report['layout_findings'].extend(_native_control_fill_findings(keyed.get(key, {}), style, key))
            for sample in candidate.get('foundations', {}).get('palette', {}).get('samples', []):
                style = candidate['control_styles']['desktop'][sample['variant']]
                key = 'review.palette.' + candidate['id'] + '.' + sample['component']
                parent = keyed.get(key, {})
                report['layout_findings'].extend(_native_control_fill_findings(parent, style, key))
                main_key = candidate['id'] + '.desktop.component.' + sample['variant']
                report['layout_findings'].extend(_native_palette_label_findings(parent, keyed.get(key + '.label', {}), keyed.get(main_key, {}), keyed.get(main_key + '.label', {}), keyed.get(candidate['id'] + '.desktop.component-set', {}), candidate['action_labels'][sample['action']], key))
                if style.get('icon'):
                    report['layout_findings'].extend(_native_control_icon_findings(parent, keyed.get(key + '.label', {}), keyed.get(key + '.icon'), style, key, packet.get('assets', {})))
        if report['layout_findings']:
            report['errors'].extend(
                f"{finding['layer']}: {finding['code']}: {finding['message']}"
                for finding in report['layout_findings']
            )
            return report
        for candidate in packet['candidates']:
            notes={n['id']:n for n in candidate['notes']};states={s['id']:s for s in candidate['prototype']['states']}
            for viewport in ('desktop','mobile'):
                for state in states.values():
                    key=f"{candidate['id']}.{viewport}.{state['id']}";node=keyed.get(key)
                    if not node or node.get('type')!='FRAME': raise ValueError('Actual editable draft frame missing: '+key)
                    for layer in candidate['state_layouts'][viewport][state['id']]['layers']:
                        actual=keyed.get(key+'.'+layer['id'])
                        if layer['kind']=='text':
                            expected_font=candidate['fonts'][layer.get('font','body')];actual_font=(actual or{}).get('fontName',{})
                            if not actual or actual.get('type')!='TEXT'or actual.get('characters')!=layer['value']or any(actual_font.get(field)!=expected_font[field]for field in ('family','style'))or any(actual_font.get('variationSettings',{}).get(axis)!=value for axis,value in expected_font.get('variationSettings',{}).items())or abs(actual.get('fontSize',0)-layer['size'])>.001:raise ValueError('Actual editable text/font differs from authored layout: '+key+'.'+layer['id'])
                        elif layer['kind']in('rect','ellipse'):
                            expected_type='RECTANGLE'if layer['kind']=='rect'else'ELLIPSE'
                            if not actual or actual.get('type')!=expected_type:raise ValueError('Actual editable native shape missing: '+key+'.'+layer['id'])
                            checks=[('opacity',layer.get('opacity',1))]
                            if layer['kind']=='rect'and layer.get('radius'):checks.append(('cornerRadius',layer['radius']))
                            if 'stroke'in layer:checks.append(('strokeWeight',layer['stroke_width']))
                            for field,expected in checks:
                                observed=actual.get(field,1 if field=='opacity'else None)
                                if not _finite(observed)or abs(observed-expected)>.001:raise ValueError('Native shape '+field+' differs from authored layout: '+key+'.'+layer['id'])
                            if 'stroke'in layer and not any(paint.get('type')=='SOLID'and paint.get('visible',True)for paint in actual.get('strokes',[])or[]):raise ValueError('Native shape stroke missing: '+key+'.'+layer['id'])
                        elif layer['kind']=='gradient':
                            fills=(actual or{}).get('fills');paint=fills[0]if isinstance(fills,list)and fills and isinstance(fills[0],dict)else{}
                            if paint.get('type')!='GRADIENT_LINEAR'or len(paint.get('gradientStops',[]))!=len(layer['stops']):raise ValueError('Editable native source gradient missing')
                            for stop,expected in zip(paint['gradientStops'],layer['stops']):
                                rgb_value={k:int(expected['color'][offset:offset+2],16)/255 for k,offset in [('r',1),('g',3),('b',5)]};rgb_value['a']=expected['opacity']
                                if abs(stop['position']-expected['position'])>.0001 or any(abs(stop['color'][k]-v)>.0001 for k,v in rgb_value.items()):raise ValueError('Native gradient differs from authored source stops')
                    note = notes[state['screen']]
                    spec = candidate['specifications'][note['id']] if 'specifications' in candidate else None
                    check_note(node,note,spec,packet['instance_sha256'],raw);report['screens'].append({'key':key,'id':node['id'],'viewport':viewport,'state':state['id']})
                for edge in [e for e in candidate['prototype']['bindings']if e['viewport']==viewport]:
                    src=f"{candidate['id']}.{viewport}.{edge['source_state']}";target=keyed[f"{candidate['id']}.{viewport}.{edge['target_state']}"]
                    node=keyed.get(src+'.'+edge['control_id']);note=candidate['action_notes'][edge['action']+'|'+edge['control_id']]
                    if not node or node.get('type')!='INSTANCE' or nodes.get(node.get('mainComponentId'),{}).get('type')!='COMPONENT': raise ValueError('Real reusable control missing')
                    spec = candidate['specifications'][note['id']] if 'specifications' in candidate else None
                    check_note(node,note,spec,packet['instance_sha256'],raw);report['annotation_checks'].append({'key':node['semanticKey'],'action':edge['action'],'states':note['functional_states']})
                    actions=[a for r in node.get('reactions',[])for a in r.get('actions',[])if r.get('trigger',{}).get('type')=='ON_CLICK']
                    if not any(a.get('type')=='NODE'and a.get('navigation')=='NAVIGATE'and a.get('destinationId')==target['id']for a in actions): raise ValueError('Exact native click destination missing: '+node['semanticKey'])
                    item={'source':node['id'],'destination':target['id'],'action':edge['action']};report['prototype_checks'].append(item)
                    if edge['target_state']==candidate['entry_state']:report['return_checks'].append(item)
            palette=raw.get('palettes',{}).get(candidate['id'],{})
            if not palette.get('libraryId')in nodes or not nodes[palette['libraryId']].get('visible',True):raise ValueError('Visible role palette missing')
            if len(palette.get('samples',[]))<2:raise ValueError('Documented primary/secondary samples required')
            for sample in palette['samples']:
                if nodes.get(sample.get('instanceId'),{}).get('type')!='INSTANCE' or not sample.get('action')or not sample.get('state')or not sample.get('useCases'):raise ValueError('Real meaningful palette sample missing')
            note_board=raw.get('noteFrames',{}).get(candidate['id'],{})
            board_node=nodes.get(note_board.get('boardId'),{})
            if board_node.get('type')!='FRAME'or board_node.get('visible')is False or board_node.get('layoutMode')!='VERTICAL':raise ValueError('Ordinary Design-mode note board missing')
            if 'specifications' in candidate:
                box = _native_box(board_node)
                if box is None:
                    raise ValueError('Readable specification board bounds unavailable')
                for other in packet['candidates']:
                    for viewport in ('desktop', 'mobile'):
                        for state in other['prototype']['states']:
                            art = _native_box(keyed.get(f"{other['id']}.{viewport}.{state['id']}"))
                            if art is None:
                                raise ValueError('Artwork bounds unavailable for specification placement')
                            if box[0] < art[0] + art[2] and art[0] < box[0] + box[2] and box[1] < art[1] + art[3] and art[1] < box[1] + box[3]:
                                raise ValueError('Readable specification board overlaps artwork')
            entries={entry['targetId']:entry for entry in note_board.get('entries',[])}
            targets=[]
            for viewport in ('desktop','mobile'):
                for state in states.values():targets.append((keyed[f"{candidate['id']}.{viewport}.{state['id']}"],notes[state['screen']]))
                for edge in [e for e in candidate['prototype']['bindings']if e['viewport']==viewport]:targets.append((keyed[f"{candidate['id']}.{viewport}.{edge['source_state']}."+edge['control_id']],candidate['action_notes'][edge['action']+'|'+edge['control_id']]))
            for target,note in targets:
                entry=entries.get(target['id'],{});text=nodes.get(entry.get('textNodeId'),{})
                if text.get('type')!='TEXT'or text.get('visible')is False or text.get('fontSize',0)<14 or text.get('parentId')!=board_node['id']:raise ValueError('Readable ordinary Design note text missing')
                if 'specifications' in candidate:
                    spec = candidate['specifications'][note['id']]
                    if text.get('characters') != spec['title'] + '\n' + spec['display_text']:
                        raise ValueError('Visible Design specification differs from current graph meaning')
                else:
                    for field in ('purpose','behavior','result','journey','action'):
                        if note.get(field)and note[field]not in text.get('characters',''):raise ValueError('Visible Design note omits source meaning')
                link=text.get('hyperlink')
                if not isinstance(link,dict)or link.get('type')!='NODE'or link.get('value')!=target['id']:raise ValueError('Actual same-file Design target hyperlink missing')
                if text.get('y',0)+text.get('height',0)>board_node.get('height',0)-board_node.get('paddingBottom',0)+1:raise ValueError('Ordinary note board clips readable text')
            report['design_note_board_checks'].append({'candidate':candidate['id'],'board_id':board_node['id'],'linked_targets':len(targets),'design_url':'https://www.figma.com/design/'+raw['fileKey']+'?node-id='+board_node['id'].replace(':','-')})
            audit=audit_draft_foundations(raw,candidate,production_packet=packet if packet["scope"] == "selected-production" else None);report['foundation_checks'].append(audit)
            if not audit.get('passed',audit.get('ok')):raise ValueError('Actual draft foundations: '+'; '.join(audit.get('errors',[])))
        if not raw.get('variables')or not raw.get('collections')or not raw.get('textStyles'):raise ValueError('Actual native variables and typography styles required')
        variable_ids={v['id']for v in raw['variables']}
        for n in nodes.values():
            if n.get('type')=='PAGE':continue
            for field in('fills','strokes'):
                for paint in n.get(field,[])if isinstance(n.get(field),list)else[]:
                    if paint.get('type')=='SOLID'and paint.get('visible',True)and paint.get('opacity',1)>0:
                        alias=paint.get('boundVariables',{}).get('color',{})
                        if alias.get('id')not in variable_ids:raise ValueError('Unbound visible solid paint: '+n['id'])
            if n.get('type')=='TEXT'and n.get('characters'):
                alias=n.get('boundVariables',{}).get('fontSize',{})
                if isinstance(alias,list):alias=alias[0]if len(alias)==1 else{}
                if alias.get('id')not in variable_ids:raise ValueError('Native typography role unbound: '+n['id'])
        report['source_readback']={'path':str(Path(readback_path).resolve()),'sha256':sha(Path(readback_path).read_bytes())}
        report['layout_sha256']=packet['layout_sha256']
        report['design_url']='https://www.figma.com/design/'+raw['fileKey']+'?node-id='+raw['pageId'].replace(':','-')
        report['passed']=True;report['observed_at']=raw.get('observed_at');report['received_at']=now()
    except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError)as error:report['errors'].append(str(error))
    return report


def verify_native_review(manifest_path,readback_path):
    try:
        raw = json.loads(Path(readback_path).read_text())
        if raw.get('schema') == 'figma-flow-native-geometry-failure-v1':
            raise ValueError('Native geometry failure diagnostics are not an admissible readback')
        return _verify_native_packet(_attested_review_packet(manifest_path, raw), readback_path)
    except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError) as error:
        return {'passed':False,'scope':'exploratory-only','production_admitted':False,'errors':[str(error)]}


def verify_native_production(packet_path,readback_path):
    try:
        declared = json.loads(Path(packet_path).read_text())
        if declared.get('schema') != PRODUCTION_SCHEMA: raise ValueError('Distinct selected production packet required')
        packet = make_packet(declared['manifest'], declared['layout_pin']['path'], declared['fileKey'],
            selection_path=declared['sourceSelection']['path'],product_graph=declared['production_graph']['path'],change_request=declared['change_request']['path'])
        packet['prepared_at'] = declared['prepared_at']
        if packet != declared: raise ValueError('Prepared production packet differs from current admitted source pins')
        report = _verify_native_packet(packet, readback_path)
        report['schema'] = 'figma-flow-native-selected-production-verification-v1'
        report['source_packet'] = design_directions.pin(packet_path)
        report['sourceSelection'] = packet['sourceSelection']
        return report
    except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError) as error:
        return {'passed':False,'scope':'selected-production','production_admitted':True,'errors':[str(error)]}


def check_note(node,note,specification=None,owner_hash=None,readback=None):
    if specification is not None:
        from specification_contract import validate_specification, connected_board_reference
        from native_handoff import normalize
        current = readback or {'nodes': [node]}
        observed_nodes, parents = normalize(current)
        board_ref = connected_board_reference(observed_nodes, parents, node['id'], specification,
            page_id=current.get('pageId'), source_owner_hash=owner_hash)
        report = validate_specification(specification, node.get('specification'), native_id=node['id'],
            semantic_key=node.get('semanticKey'), source_owner_hash=owner_hash,
            annotations=node.get('annotations'), file_key=current.get('fileKey'), board_ref=board_ref)
        if not report['passed']:
            raise ValueError('Canonical readable specification differs: ' + '; '.join(report['errors'] + report['unverified']))
        prefix = '[figma-flow:' + node.get('semanticKey', '') + '] '
        if any(item.get('label', '').startswith(prefix) for item in node.get('annotations', [])):
            raise ValueError('Owned technical annotation still overlays its artwork target')
        return
    text='\n'.join(a.get('label','')for a in node.get('annotations',[]))
    for field in('purpose','behavior','result','journey','first_action','action'):
        if note.get(field)and note[field]not in text:raise ValueError('Canonical native annotation field missing: '+field)
    for state in note.get('functional_states',[]):
        if state not in text:raise ValueError('Canonical native functional state missing')


def prepare(manifest,out,register=False,port=49185,layout_path=None,file_key=None,plugin_id=None,night_demo=False,*,selection_path=None,product_graph=None,change_request=None):
    if register and not night_demo:raise ValueError('No implicit NIGHT registration: use an explicit task demo or the normal portable local plugin package.')
    if register:
        allowed_file = os.environ.get('FIGMA_FLOW_NIGHT_FILE_KEY')
        assigned_id = os.environ.get('FIGMA_FLOW_NIGHT_PLUGIN_ID')
        if not allowed_file or not assigned_id:
            raise ValueError('Set the owned NIGHT demo file key and plugin ID before private registration')
        if file_key not in (None, allowed_file) or plugin_id not in (None, assigned_id):
            raise ValueError('Task-owned NIGHT registration cannot target another file or plugin')
        file_key, plugin_id = allowed_file, assigned_id
    if selection_path and register: raise ValueError('Selected production cannot use exploratory demo registration')
    packet=make_packet(manifest,layout_path,file_key,selection_path=selection_path,product_graph=product_graph,change_request=change_request)
    if not selection_path:
        admission=design_directions.admit_native_draft(Path(manifest))
        if admission['packet_sha256']!=packet['packet_sha256']:raise ValueError('Draft admission packet mismatch')
    if not isinstance(plugin_id,str) or not re.fullmatch(r'[0-9]+',plugin_id):raise ValueError('Supply the numeric local plugin ID assigned by Figma; a demo plugin identity cannot be used implicitly')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    write_json(out/'packet.json',packet)
    helpers='\n'.join((PLUGIN/'figma-bridge'/name).read_text()for name in HELPERS)
    payload_json = json.dumps(packet, ensure_ascii=False)
    warnings = embedded_asset_warnings(payload_json, packet['assets'].values())
    code=review_plugin_code(payload_json, helpers, (PLUGIN/'figma-bridge/direction_review.js').read_text())
    portable=out/'plugin';portable.mkdir(exist_ok=True)
    manifest_data={'name':'Figma Flow · Selected production'if selection_path else'NIGHT · A/B/C Figma 방향 검토'if register else'Figma Flow · 디자인 방향 검토','id':plugin_id,'api':'1.0.0','editorType':['figma'],'main':'code.js','ui':'ui.html','documentAccess':'dynamic-page','enablePrivatePluginApi':True,'networkAccess':{'allowedDomains':['none']}}
    for name,value in{'code.js':code,'ui.html':ui_html(night_demo=night_demo,review=packet),'manifest.json':json.dumps(manifest_data,ensure_ascii=False,indent=2)}.items():(portable/name).write_text(value)
    zip_name='Figma-Selected-Production.zip'if selection_path else'NIGHT-Figma-Draft-Review.zip'if night_demo else'Figma-Direction-Review.zip'
    with zipfile.ZipFile(out/zip_name,'w',zipfile.ZIP_DEFLATED)as z:
        for path in portable.iterdir():z.write(path,path.name)
    if register:
        pair=PRIVATE/'draft-pair';pair.mkdir(parents=True,exist_ok=True,mode=0o700);token_path=pair/'capability'
        if not token_path.exists():token_path.write_text(secrets.token_hex(32));token_path.chmod(0o600)
        private=PRIVATE/'plugin';private.mkdir(parents=True,exist_ok=True,mode=0o700)
        for path in portable.iterdir():shutil.copyfile(path,private/path.name);(private/path.name).chmod(0o600)
        manifest_data['networkAccess']['devAllowedDomains']=[f'http://localhost:{port}']
        (private/'manifest.json').write_text(json.dumps(manifest_data,ensure_ascii=False,indent=2));(private/'ui.html').write_text(ui_html({'url':f'http://localhost:{port}/draft-readback','capability':token_path.read_text().strip()},night_demo=True,review=packet));(private/'ui.html').chmod(0o600)
    (out/'사용방법.txt').write_text(('지정한 Figma 파일에서 로컬 검토 플러그인을 열고')+' 「검토 시안 만들기」를 한 번 누르세요.\n이 도구는 검토용 화면·주석·팔레트·클릭 이동만 만듭니다. 방향 선택·승인·본 제작은 하지 않습니다.\nDev Mode나 유료 업그레이드 없이 일반 Design 모드의 「주석 읽기」 프레임에서 설명을 읽고 링크로 해당 화면·조작으로 이동하세요.\n원화와 브라우저 참조는 래스터이고 제목·본문·행동 제어·팔레트는 편집 가능한 실제 Figma 노드입니다. 「결과 JSON 저장」으로 원본 읽기 결과를 내보내세요. 로컬 수신기를 연결한 경우에는 결과가 그 수신기에도 전달됩니다.\n')
    if selection_path:
        (out/'사용방법.txt').write_text('Selected production authoring from the validated user choice and pinned contrast changes. Run the prepared workspace create operation, preserve its actual readback, then verify-production --packet packet.json --readback ACTUAL.json. This does not approve a new direction or final delivery.\n')
    write_json(out/'prepared.json',{'status':'prepared-not-executed','packet_sha256':packet['packet_sha256'],'fileKey':packet['fileKey'],'production_admitted':packet['production_admitted'],'scope':packet['scope'],'manifest':str(portable/'manifest.json'),'registered':register,'warnings':warnings})
    return {'manifest':str((PRIVATE/'plugin/manifest.json')if register else portable/'manifest.json'),'packet':str(out/'packet.json'),'zip':str(out/zip_name),'status':'prepared-not-executed','warnings':warnings}


def review_thumbnails(review, candidate):
    """Only decode the packet's raster references; never read paths or fetch URLs."""
    from io import BytesIO
    try:
        from PIL import Image
    except ImportError:
        return []
    if not review or review.get('schema') not in ('figma-flow-native-direction-review-v1', PRODUCTION_SCHEMA):
        return []
    thumbnails = []
    for viewport in ('desktop', 'mobile'):
        name = candidate.get('references', {}).get(viewport)
        encoded = review.get('assets', {}).get(name)
        if not isinstance(encoded, str) or len(encoded) > 16_000_000:
            continue
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(BytesIO(raw)) as image:
                if image.format != 'PNG' or image.width * image.height > 16_000_000:
                    continue
                image.thumbnail((640, 360), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.convert('RGBA').save(output, format='PNG', optimize=True)
            if output.tell() <= 256_000:
                thumbnails.append((viewport, base64.b64encode(output.getvalue()).decode('ascii')))
        except (ValueError, OSError, Image.DecompressionBombError):
            continue
    return thumbnails


def ui_html(pair=None, night_demo=False, review=None):
    if review and review.get('scope') == 'selected-production':
        if pair or night_demo: raise ValueError('Selected production is not an exploratory receiver/demo')
        from plugin_panel import render_app
        candidate = review['candidates'][0]
        previews = [{'viewport':viewport,'src':'data:image/png;base64,'+data} for viewport,data in review_thumbnails(review,candidate)]
        model = {'candidates':[{'title':candidate['title'],'previews':previews}], 'pair':None,
                 'filePinned':bool(review.get('fileKey')), 'pageName':'PRODUCTION · '+candidate['title']+' · '+review['packet_sha256'][:8],
                 'selectedProduction':True,'scope':review['scope'],'sourceSelection':review['sourceSelection']}
        return render_app('review',model).replace('</head>','<script>\nconst PAIR = null;\n</script></head>',1)
    messages = json.loads((PLUGIN / 'figma-bridge/locales/review.json').read_text())

    def text(key, **params):
        value = messages['review.' + key]['ko']
        for name, replacement in params.items():
            value = value.replace('{' + name + '}', str(replacement))
        return escape(value)

    def localized(tag, key, **params):
        attributes = ' data-i18n="review.' + key + '"'
        if params:
            attributes += ' data-i18n-params="' + escape(json.dumps(params, ensure_ascii=False), quote=True) + '"'
        return '<' + tag + attributes + '>' + text(key, **params) + '</' + tag + '>'

    candidates = review.get('candidates', []) if review else []
    context = localized('h1', 'heading', count=len(candidates)) if candidates else localized('h1', 'emptyHeading')
    context += '<p>' + escape(' · '.join(str(candidate['title']) for candidate in candidates)) + '</p>' if candidates else localized('p', 'emptyNames')
    target = localized('span', 'exactFile' if review and review.get('fileKey') else 'currentFile')
    page = localized('span', 'reviewPage')
    if review and review.get('packet_sha256'):
        native_page = 'DRAFT · A/B/C 방향 검토 · ' + review['packet_sha256'][:8]
        page = localized('span', 'pageLabel') + ': <span>' + escape(native_page) + '</span>'
    references = []
    for candidate in candidates:
        title = str(candidate['title'])
        previews = []
        for viewport, encoded in review_thumbnails(review, candidate):
            params = escape(json.dumps({'name': title, 'viewport': messages['review.' + viewport]['ko']}, ensure_ascii=False), quote=True)
            previews.append('<figure><img loading="lazy" src="data:image/png;base64,' + encoded + '" alt="' + text('previewAlt', name=title, viewport=messages['review.' + viewport]['ko']) + '" data-preview-name="' + escape(title, quote=True) + '" data-preview-viewport="' + viewport + '" data-i18n-alt="review.previewAlt" data-i18n-params="' + params + '"><figcaption><span data-i18n="review.previewLabel" data-preview-label="' + viewport + '">' + text('previewLabel', viewport=messages['review.' + viewport]['ko']) + '</span></figcaption></figure>')
        references.append('<article class="review-reference panel-preview"><h3>' + escape(title) + '</h3><div class="review-previews">' + (''.join(previews) or localized('p', 'noPreview')) + '</div></article>')
    pair_json = json.dumps(pair).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = '''<!doctype html><html lang="ko" data-flow-view="review"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>/* FIGMA_FLOW_PANEL_CSS */
.review-references {display:grid;gap:14px;margin:16px 0 20px}
.review-reference {min-width:0}
.review-reference h3 {font-size:13px;font-weight:650;margin-bottom:10px}
.review-previews {display:flex;align-items:start;gap:10px;flex-wrap:wrap}
.review-previews figure {margin:0;flex:1 1 180px;min-width:0}
.review-previews img {display:block;width:100%;height:160px;object-fit:contain;background:var(--surface);border:1px solid var(--line);border-radius:4px}
.review-previews figcaption {font-size:11px;color:var(--muted);margin-top:5px}
.review-step {font-size:14px;margin-bottom:10px}
@media(max-width:360px){.review-previews img{height:140px}}
</style>
<body class="panel">
<!-- FLOW_SHELL -->
<main class="workspace">
<section class="intro">__REVIEW_CONTEXT__</section>
<div class="review-references">__REFERENCES__</div>
<section class="work-section"><h2 data-i18n="review.createStep">__CREATE_STEP__</h2><p class="metadata">__REVIEW_SCOPE__</p><p data-i18n="review.createBody">__CREATE_BODY__</p><div class="actions"><button class="primary" id="make" data-i18n-aria="review.make" aria-label="__MAKE__">__MAKE__</button></div></section>
<section class="work-section"><h2 class="review-step" data-i18n="review.readStep">__READ_STEP__</h2><!-- FLOW_STATUS --><details class="details" id="status-details" hidden><summary data-i18n="review.details">__DETAILS__</summary><pre id="status"></pre></details></section>
<section class="work-section"><h2 data-i18n="review.saveStep">__SAVE_STEP__</h2>__SAVE_BODY__<div class="actions"><button class="secondary" id="save" disabled data-i18n-aria="review.save" aria-label="__SAVE__">__SAVE__</button></div></section>
<p class="metadata" data-i18n="review.boundary">__BOUNDARY__</p>
</main>
<script>
const PAIR = __PAIR__;
const t = (key, params) => FlowUI.t('review.' + key, params);
let result = null;
let resultKind = null;
let receiptOutcome = null;
let receiptDetails = '';
let persistenceFailed = false;
let nativeBusy = false;
let currentStatus = ['ready', 'readyTitle', 'readyBody', ''];
const makeButton = document.getElementById('make');
const saveButton = document.getElementById('save');
const status = document.getElementById('status');
const statusDetails = document.getElementById('status-details');
const localeSelect = document.getElementById('workspace-locale');
function showStatus(state, title, body, details = '') {
  currentStatus = [state, title, body, details];
  FlowPanel.status({region:'status-panel',title:'status-title',body:'status-body',state,titleText:t(title),bodyText:t(body)});
  status.textContent = details;
  statusDetails.hidden = !details;
}
function setBusy(busy) {
  if (typeof busy === 'boolean') nativeBusy = busy;
  const waiting = nativeBusy || (PAIR && resultKind === 'readback' && receiptOutcome === null && !persistenceFailed);
  makeButton.disabled = !!waiting;
  makeButton.textContent = t(waiting ? 'makeBusy' : 'make');
  makeButton.setAttribute('aria-label', makeButton.textContent);
}
function refreshLocale() {
  FlowUI.apply();
  localeSelect.value = FlowUI.locale;
  setBusy();
  saveButton.textContent = t(resultKind === 'failure' ? 'saveFailure' : 'save');
  saveButton.setAttribute('aria-label', saveButton.textContent);
  showStatus(...currentStatus);
  document.querySelectorAll('[data-preview-viewport]').forEach(image => {
    const viewport = t(image.dataset.previewViewport);
    const params = {name:image.dataset.previewName, viewport};
    image.dataset.i18nParams = JSON.stringify(params);
    image.setAttribute('alt', t('previewAlt', params));
  });
  document.querySelectorAll('[data-preview-label]').forEach(label => {
    const params = {viewport:t(label.dataset.previewLabel)};
    label.dataset.i18nParams = JSON.stringify(params);
    label.textContent = t('previewLabel', params);
  });
}
window.addEventListener('flow:locale', refreshLocale);
function showReadbackStatus() {
  if (receiptOutcome !== null) {
    showStatus(receiptOutcome ? 'success' : 'error', receiptOutcome ? 'verifiedTitle' : 'rejectedTitle',
      receiptOutcome ? 'verifiedBody' : 'rejectedBody', receiptDetails);
  } else {
    showStatus(PAIR ? 'busy' : 'success', PAIR ? 'sendingTitle' : 'readTitle', PAIR ? 'sendingBody' : 'readBody');
  }
}
makeButton.onclick = () => {
  result = null;
  resultKind = null;
  receiptOutcome = null;
  receiptDetails = '';
  persistenceFailed = false;
  setBusy(true);
  saveButton.disabled = true;
  saveButton.className = 'secondary';
  makeButton.className = 'primary';
  saveButton.textContent = t('save');
  saveButton.setAttribute('aria-label', saveButton.textContent);
  showStatus('busy', 'creatingTitle', 'creatingBody');
  parent.postMessage({pluginMessage: {type: 'draft-review'}}, '*');
};
saveButton.onclick = () => {
  if (!result) return;
  const anchor = document.createElement('a');
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}));
  anchor.href = url;
  anchor.download = resultKind === 'failure' ? 'figma-direction-review-failure.json' : 'figma-direction-review-readback.json';
  anchor.click();
  URL.revokeObjectURL(url);
};
window.onmessage = async event => {
  const message = event.data && event.data.pluginMessage;
  if (!message) return;
  if (message.type === 'status') {
    setBusy(!!message.busy);
    if (resultKind === 'failure' || persistenceFailed) return;
    if (resultKind === 'readback' && receiptOutcome !== null) {
      showReadbackStatus();
    } else if (message.state === 'error') {
      showStatus('error', resultKind === 'readback' ? 'rejectedTitle' : 'generationFailed', 'errorBody', message.message);
    } else if (resultKind === 'readback') {
      showReadbackStatus();
    } else if (message.busy) {
      showStatus('busy', 'creatingTitle', 'creatingBody', message.message);
    } else {
      showStatus('ready', 'createdTitle', 'readyBody', message.message);
    }
    return;
  }
  if (message.type === 'geometry-failure') {
    const diagnostic = message.data;
    if (!diagnostic || diagnostic.schema !== 'figma-flow-native-geometry-failure-v1' || diagnostic.passed !== false) return;
    result = diagnostic;
    resultKind = 'failure';
    saveButton.disabled = false;
    saveButton.className = 'primary';
    makeButton.className = 'secondary';
    saveButton.textContent = t('saveFailure');
    saveButton.setAttribute('aria-label', saveButton.textContent);
    showStatus('error', 'geometryTitle', 'geometryBody', JSON.stringify(diagnostic, null, 2));
    return;
  }
  if (message.type !== 'readback') return;
  result = message.data;
  resultKind = 'readback';
  saveButton.disabled = false;
  saveButton.className = 'primary';
  makeButton.className = 'secondary';
  saveButton.textContent = t('save');
  saveButton.setAttribute('aria-label', saveButton.textContent);
  showReadbackStatus();
  setBusy();
  if (!PAIR) return;
  try {
    const response = await fetch(PAIR.url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + PAIR.capability},
      body: JSON.stringify(message.data)
    });
    const receipt = await response.json();
    if (!response.ok && receipt.passed !== false) throw Error(receipt.errors?.join('; ') || receipt.error || response.status);
    receiptOutcome = response.ok && receipt.passed === true;
    receiptDetails = receiptOutcome ? '' : JSON.stringify(receipt, null, 2);
    setBusy();
    showReadbackStatus();
    parent.postMessage({pluginMessage: {type: 'receipt', passed: receipt.passed}}, '*');
  } catch (error) {
    persistenceFailed = true;
    setBusy();
    showStatus('error', 'deliveryTitle', 'deliveryBody', String(error));
  }
};
refreshLocale();
</script></body></html>'''
    filled = (html.replace('__PAIR__', pair_json).replace('__REVIEW_SCOPE__', target + ' / ' + page)
              .replace('__REVIEW_CONTEXT__', context).replace('__REFERENCES__', ''.join(references))
              .replace('__SAVE_BODY__', localized('p', 'saveBodyPaired' if pair else 'saveBodyPortable'))
              .replace('__CREATE_STEP__', text('createStep')).replace('__CREATE_BODY__', text('createBody'))
              .replace('__MAKE__', text('make')).replace('__READ_STEP__', text('readStep'))
              .replace('__DETAILS__', text('details')).replace('__SAVE_STEP__', text('saveStep'))
              .replace('__SAVE__', text('save')).replace('__BOUNDARY__', text('boundary')))
    return render_panel(filled)

class DraftReceiver(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204);self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Authorization,Content-Type');self.send_header('Access-Control-Allow-Methods','POST,OPTIONS');self.end_headers()
    def do_POST(self):
        import hmac
        try:
            if self.path!='/draft-readback'or self.headers.get('Host')!=f'localhost:{self.server.server_port}'or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.capability):raise ValueError('Exact paired local draft endpoint required')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<25_000_000 or self.headers.get('Transfer-Encoding'):raise ValueError('Bounded draft JSON required')
            raw=json.loads(self.rfile.read(length));packet=json.loads(self.server.packet.read_text())
            if not raw.get('fileKey')or packet['fileKey']and raw.get('fileKey')!=packet['fileKey']or raw.get('instance_sha256')!=packet['instance_sha256'] or raw.get('packet_sha256')!=packet['packet_sha256']:raise ValueError('Exact prepared direction-review packet required')
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder=self.server.output/stamp;write_json(folder/'readback.json',raw)
            report=verify_native_review(packet['manifest'],folder/'readback.json');write_json(folder/'receipt.json',report)
            write_json(self.server.output/'latest.json',{'folder':str(folder),'passed':report['passed'],'packet_sha256':packet['packet_sha256']})
            status=200 if report['passed']else 409
        except(ValueError,OSError,TypeError,KeyError)as error:report={'passed':False,'errors':[str(error)]};status=409
        body=json.dumps(report,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    build=commands.add_parser('prepare');build.add_argument('--manifest',type=Path);build.add_argument('--out',type=Path,required=True);build.add_argument('--register-night',action='store_true');build.add_argument('--port',type=int,default=49185);build.add_argument('--layout',type=Path);build.add_argument('--file-key');build.add_argument('--plugin-id');build.add_argument('--selection',type=Path);build.add_argument('--product-graph',type=Path);build.add_argument('--change-request',type=Path)
    verify=commands.add_parser('verify');verify.add_argument('--manifest',type=Path,required=True);verify.add_argument('--readback',type=Path,required=True)
    production=commands.add_parser('verify-production');production.add_argument('--packet',type=Path,required=True);production.add_argument('--readback',type=Path,required=True)
    serve=commands.add_parser('serve');serve.add_argument('--packet',type=Path,required=True);serve.add_argument('--out',type=Path,required=True);serve.add_argument('--port',type=int,default=49185);serve.add_argument('--pair-dir',type=Path,required=True)
    args=parser.parse_args()
    try:
        _run(parser,args)
    except (OSError,ValueError,KeyError,TypeError)as exc:
        print(json.dumps({'passed':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)


def _run(parser,args):
    if args.command=='prepare':print(json.dumps(prepare(args.manifest,args.out,args.register_night,args.port,args.layout,args.file_key,args.plugin_id,night_demo=args.register_night,selection_path=args.selection,product_graph=args.product_graph,change_request=args.change_request),ensure_ascii=False))
    elif args.command=='verify-production':
        result=verify_native_production(args.packet,args.readback);print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['passed']else 2)
    elif args.command=='verify':
        result=verify_native_review(args.manifest,args.readback);print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['passed']else 2)
    else:
        packet=json.loads(args.packet.read_text());current=make_packet(packet['manifest'],packet['layout_pin']['path'],packet['fileKey'])
        if {k:v for k,v in packet.items() if k!='prepared_at'}!={k:v for k,v in current.items() if k!='prepared_at'}:
            parser.error('Prepared draft packet no longer matches the reviewed layout, importer, target or inputs')
        capability=(args.pair_dir/'capability').read_text().strip()
        if not re.fullmatch(r'[0-9a-f]{64}', capability):parser.error('Valid local pairing is required')
        args.out.mkdir(parents=True,exist_ok=True)
        with HTTPServer(('127.0.0.1',args.port),DraftReceiver)as server:
            server.packet=args.packet.resolve();server.output=args.out.resolve();server.capability=capability;print('Figma draft-only receiver '+str(args.port),flush=True);server.serve_forever()


if __name__=='__main__':main()
