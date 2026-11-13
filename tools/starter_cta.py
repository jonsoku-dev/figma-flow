#!/usr/bin/env python3
"""Prepare a page-scoped, idempotent Little Hands booking CTA provision plan."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from graph_design_system import load_graph, resolve_design_system
from graph_sync import token_native_names
from native_handoff import little_hands_source_labels, normalize
from native_edit import PLAN_SCHEMA, validate_plan


ROOT_KEY = 'little-hands/booking-cta/starter-frame'
PLAN_KIND = 'figma-flow-starter-cta-provision-v1'
SEED_COLLECTION = 'Little Hands · CTA SSOT seed'
SEED_VARIABLE = 'starter/little-hands/booking-cta-seed'
INSTANCE_KEYS = ('reserve-preview', 'reserve-login')


def _color(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError(f'Expected an opaque six-digit CSS color: {name}')
    return {channel: int(value[index:index + 2], 16) / 255 for channel, index in (('r', 1), ('g', 3), ('b', 5))}


def _root_projection(row):
    box = row.get('absoluteBoundingBox')
    if not isinstance(box, dict) or not all(type(box.get(field)) in (int, float) for field in ('x', 'y', 'width', 'height')):
        raise ValueError(f'Actual top-level bounds required: {row.get("id")}')
    return {field: row.get(field) for field in ('id', 'type', 'name', 'semanticKey', 'x', 'y', 'width', 'height', 'absoluteBoundingBox')}


def prepare(graph_path, readback_path, file_key, page_id, out):
    graph_file = Path(graph_path).resolve()
    graph = load_graph(graph_file)
    resolved = resolve_design_system(graph)
    design = graph.get('design_system', {})
    component = design.get('components', {}).get('button.bookingCTA')
    native = component.get('native') if isinstance(component, dict) else None
    if not isinstance(native, dict) or native.get('mainKeys') != ['bookingCTA'] or native.get('instanceKeys') != list(INSTANCE_KEYS):
        raise ValueError('Little Hands booking CTA native semantic key contract is missing or changed')
    if component['properties'].get('backgroundColor') != 'color.action.primary' or native.get('semanticToken') != 'color.action.primary':
        raise ValueError('Booking CTA component must use the graph semantic primary action color')
    token_value = resolved['tokens'].get('color.action.primary')
    if not isinstance(token_value, dict) or not all(type(token_value.get(channel)) in (int, float) for channel in 'rgb'):
        raise ValueError('Resolved graph primary action color is unavailable')
    _, native_names = token_native_names(graph, require_namespace=True)

    raw = Path(readback_path).read_bytes()
    readback = json.loads(raw)
    if (readback.get('schema') != 'figma-flow-graph-native-discovery-v1' or readback.get('fileKey') != file_key
            or readback.get('pageId') != page_id or readback.get('allowed_page_ids') != [page_id]):
        raise ValueError('Full native discovery must match the exact file and existing page')
    nodes, parents = normalize(readback)
    page = nodes.get(page_id)
    if not page or page.get('type') != 'PAGE':
        raise ValueError('Actual selected native page is absent from full discovery')
    owned = [row for row in readback['nodes'] if row.get('semanticKey') == ROOT_KEY]
    if len(owned) > 1:
        raise ValueError('Duplicate owned CTA workbench frame key')
    frame = owned[0] if owned else None
    if frame and parents.get(frame['id']) != page_id:
        raise ValueError('Existing CTA workbench key belongs to another parent')
    root_rows = [_root_projection(row) for row in readback['nodes'] if parents.get(row['id']) == page_id and row['id'] != (frame or {}).get('id')]
    root_rows.sort(key=lambda row: row['id'])
    expected_parents = {key: ROOT_KEY for key in ('bookingCTA', *INSTANCE_KEYS)}
    for key, parent_key in expected_parents.items():
        matches = [row for row in readback['nodes'] if row.get('semanticKey') == key]
        expected_parent_id = frame['id'] if frame and parent_key == ROOT_KEY else None
        if frame and parent_key != ROOT_KEY:
            expected_parent_id = next((row['id'] for row in readback['nodes'] if row.get('semanticKey') == parent_key), None)
        if len(matches) > 1 or (matches and (not frame or parents.get(matches[0]['id']) != expected_parent_id)):
            raise ValueError(f'CTA semantic key is already used outside the owned workbench: {key}')
    seed_collections = [row for row in readback.get('collections', []) if row.get('name') == SEED_COLLECTION]
    if frame:
        if (len(seed_collections) != 1 or seed_collections[0].get('owner', {}).get('pageId') != page_id
                or seed_collections[0].get('owner', {}).get('collectionId') != seed_collections[0].get('id')):
            raise ValueError('Existing CTA workbench requires its uniquely owned seed token collection')
    elif seed_collections:
        raise ValueError('CTA seed collection already exists without its owned frame; inspect the partial run')
    token_file = graph_file.parent / 'tokens.json'
    token_bytes = token_file.read_bytes()
    palette = json.loads(token_bytes)['colors']
    background = {channel: token_value[channel] for channel in 'rgb'}
    text_color = _color(palette['cream'], 'cream')
    if frame:
        box = frame.get('absoluteBoundingBox')
        if not isinstance(box, dict):
            raise ValueError('Existing owned CTA workbench bounds are required')
        position = {'x': box['x'], 'y': box['y']}
    else:
        if not root_rows:
            raise ValueError('Actual page children with bounds are required to place the workbench')
        position = {'x': max(row['absoluteBoundingBox']['x'] + row['absoluteBoundingBox']['width'] for row in root_rows) + 96,
                    'y': 0}
    action = next((node for node in graph.get('nodes', []) if node.get('web_action') == INSTANCE_KEYS[0]), None)
    copy_source = little_hands_source_labels(action, INSTANCE_KEYS)
    labels = copy_source.get('template_branch_labels', {})
    if any(not isinstance(labels.get(key), str) or not labels[key] for key in INSTANCE_KEYS):
        raise ValueError('Both booking CTA branch labels must exist in the declared app template')
    template = Path(__file__).resolve().parents[1] / copy_source['source']
    plan = {
        'schema': PLAN_SCHEMA, 'file_key': file_key, 'page_id': page_id,
        'provision': {
            'schema': PLAN_KIND, 'graph_sha256': graph.source_sha256,
            'token_source_sha256': hashlib.sha256(token_bytes).hexdigest(),
            'readback_sha256': hashlib.sha256(raw).hexdigest(),
            'source_graph_path': str(graph_file), 'token_source_path': str(token_file.resolve()),
            'readback_path': str(Path(readback_path).resolve()),
            'frame_key': ROOT_KEY, 'main_key': 'bookingCTA', 'instance_keys': list(INSTANCE_KEYS),
            'seed_collection_name': SEED_COLLECTION, 'seed_variable_name': SEED_VARIABLE,
            'canonical_variable_name': native_names['color.action.primary'],
            'background_color': background, 'text_color': text_color,
            'labels': {'main': '예약하기', **labels},
            'label_source_path': str(template), 'label_source_sha256': copy_source['source_sha256'],
            'page_roots': root_rows, 'position': position,
        },
    }
    validate_plan(plan)
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return {'plan': str(output.resolve()), 'file_key': file_key, 'page_id': page_id,
            'graph_sha256': graph.source_sha256, 'readback_sha256': hashlib.sha256(raw).hexdigest(),
            'status': 'prepared-not-executed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepare', choices=['prepare'])
    parser.add_argument('--graph', required=True)
    parser.add_argument('--readback', required=True)
    parser.add_argument('--file-key', required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.graph, args.readback, args.file_key, args.page_id, args.out)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'starter_cta: {error}\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
