#!/usr/bin/env python3
"""Prepare an exact, bounded native edit transaction; preparing never edits Figma."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import secrets

from graph_design_system import SUPPORTED_PROPERTY_TYPES, _validate_property, _validate_value
from graph_sync import graph_panel
from specification_contract import spec_label_prelude

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA = 'figma-flow-native-edit-plan-v1'
NODE_FIELDS = {'fontSize', 'fontFamily', 'paddingLeft', 'paddingRight', 'backgroundColor', 'color', 'borderRadius'}
ID = re.compile(r'(?:I?\d+:\d+)(?:;\d+:\d+)*\Z')


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get('schema') != PLAN_SCHEMA:
        raise ValueError('Explicit native edit plan schema required')
    if set(plan) not in ({'schema', 'file_key', 'page_id', 'edits'}, {'schema', 'file_key', 'page_id', 'variableedit'}, {'schema', 'file_key', 'page_id', 'specifications'}, {'schema', 'file_key', 'page_id', 'provision'}):
        raise ValueError('Plan requires exact file/page and one supported edit variant')
    if not isinstance(plan['file_key'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', plan['file_key']) or not isinstance(plan['page_id'], str) or not ID.fullmatch(plan['page_id']):
        raise ValueError('Exact safe native file/page identity required')
    if 'specifications' in plan:
        from specifications import validate_update
        return validate_update(plan)
    if 'provision' in plan:
        provision = plan['provision']
        required = {'schema', 'graph_sha256', 'token_source_sha256', 'readback_sha256', 'frame_key', 'main_key',
                    'instance_keys', 'seed_collection_name', 'seed_variable_name', 'canonical_variable_name', 'background_color', 'text_color',
                    'labels', 'page_roots', 'position', 'source_graph_path', 'token_source_path', 'readback_path'}
        if not isinstance(provision, dict) or set(provision) != required or provision['schema'] != 'figma-flow-starter-cta-provision-v1':
            raise ValueError('Exact Little Hands CTA provision contract required')
        for field in ('graph_sha256', 'token_source_sha256', 'readback_sha256'):
            if not isinstance(provision[field], str) or not re.fullmatch(r'[a-f0-9]{64}', provision[field]):
                raise ValueError(f'Valid pinned {field} required')
        for field, digest_field in (('source_graph_path', 'graph_sha256'), ('token_source_path', 'token_source_sha256'), ('readback_path', 'readback_sha256')):
            source = provision[field]
            if not isinstance(source, str) or not Path(source).is_absolute() or hashlib.sha256(Path(source).read_bytes()).hexdigest() != provision[digest_field]:
                raise ValueError(f'Pinned Starter CTA source changed or is unavailable: {field}')
        if (provision['frame_key'] != 'little-hands/booking-cta/starter-frame' or provision['main_key'] != 'bookingCTA'
                or provision['instance_keys'] != ['reserve-preview', 'reserve-login']):
            raise ValueError('Stable Little Hands booking CTA semantic keys required')
        if provision['seed_collection_name'] != 'Little Hands · CTA SSOT seed' or provision['seed_variable_name'] != 'starter/little-hands/booking-cta-seed':
            raise ValueError('Dedicated owned Little Hands CTA seed token mapping required')
        if not isinstance(provision['canonical_variable_name'], str) or not re.fullmatch(r'ssot/little-hands/color/action/primary', provision['canonical_variable_name']):
            raise ValueError('Current graph native semantic token name required')
        for field in ('background_color', 'text_color'):
            _validate_value('COLOR', provision[field], field)
            _validate_property('backgroundColor', 'COLOR', provision[field])
        if (not isinstance(provision['labels'], dict) or set(provision['labels']) != {'main', *provision['instance_keys']}
                or any(not isinstance(label, str) or not label.strip() or len(label) > 120 for label in provision['labels'].values())):
            raise ValueError('Exact bounded CTA main and instance labels required')
        position = provision['position']
        if not isinstance(position, dict) or set(position) != {'x', 'y'} or any(type(position[key]) not in (int, float) or not math.isfinite(position[key]) for key in position):
            raise ValueError('Finite existing-page CTA frame position required')
        roots = provision['page_roots']
        if not isinstance(roots, list) or len(roots) > 4000:
            raise ValueError('Bounded existing page root snapshot required')
        seen = set()
        fields = {'id', 'type', 'name', 'semanticKey', 'x', 'y', 'width', 'height', 'absoluteBoundingBox'}
        for row in roots:
            if (not isinstance(row, dict) or set(row) != fields or not isinstance(row['id'], str) or not ID.fullmatch(row['id'])
                    or row['id'] in seen or not isinstance(row['type'], str) or not isinstance(row['name'], str)):
                raise ValueError('Invalid or duplicate existing page root')
            seen.add(row['id'])
            box = row['absoluteBoundingBox']
            if not isinstance(box, dict) or set(box) != {'x', 'y', 'width', 'height'} or any(type(box[key]) not in (int, float) or not math.isfinite(box[key]) for key in box):
                raise ValueError('Finite existing page root bounds required')
        return plan
    if 'variableedit' in plan:
        row = plan['variableedit']
        if not isinstance(row, dict) or set(row) != {'variable_id', 'mode_id', 'before', 'after'}:
            raise ValueError('Variable edit requires variable_id/mode_id/before/after')
        if not all(isinstance(row[k], str) and row[k].strip() and len(row[k]) <= 200 for k in ('variable_id', 'mode_id')):
            raise ValueError('Existing variable and mode IDs required')
        for value in (row['before'], row['after']):
            kind = 'STRING' if isinstance(value, str) else 'COLOR' if isinstance(value, dict) else 'FLOAT'
            _validate_value(kind, value, row['variable_id'])
            if kind == 'STRING':
                _validate_property('fontFamily', kind, value)
            if kind == 'FLOAT' and value < 0:
                raise ValueError('Supported native variable sizes must be non-negative')
        if type(row['before']) is not type(row['after']) and not all(type(v) in (int, float) for v in (row['before'], row['after'])):
            raise ValueError('Variable value type must stay unchanged')
        return plan
    rows = plan['edits']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError('Provide 1–32 explicit node edits')
    seen, fonts = set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) not in ({'node_id', 'field', 'before', 'after'}, {'node_id', 'main_id', 'field', 'before', 'after'}):
            raise ValueError('Exact node_id/field/before/after (plus scoped main_id for text) required')
        if not isinstance(row['node_id'], str) or not ID.fullmatch(row['node_id']) or not isinstance(row['field'], str) or row['field'] not in NODE_FIELDS:
            raise ValueError('Unsupported native node or field')
        key = (row['node_id'], row['field'])
        if key in seen:
            raise ValueError('Duplicate native edit target')
        seen.add(key)
        text = row['field'] in ('fontSize', 'fontFamily', 'color')
        if text != ('main_id' in row) or text and (not isinstance(row['main_id'], str) or not ID.fullmatch(row['main_id'])):
            raise ValueError('Text edits require their exact local main_id; component fields do not')
        if row['field'].startswith('font'):
            if row['node_id'] in fonts:
                raise ValueError('Only one font mutation per text node per transaction')
            fonts.add(row['node_id'])
        for value in (row['before'], row['after']):
            _validate_value(SUPPORTED_PROPERTY_TYPES[row['field']], value, row['field'])
            _validate_property(row['field'], SUPPORTED_PROPERTY_TYPES[row['field']], value)
    return plan


def prepare(plan_path, out, plugin_id=None):
    raw = Path(plan_path).read_bytes()
    if len(raw) > 128_000:
        raise ValueError('Bounded plan JSON required')
    plan = validate_plan(json.loads(raw))
    if plugin_id and not re.fullmatch(r'\d+', plugin_id):
        raise ValueError('Use the actual assigned numeric plugin ID')
    output = Path(out)
    output.mkdir(parents=True, exist_ok=False, mode=0o700 if 'specifications' in plan or 'provision' in plan else 0o777)
    session = secrets.token_hex(16)
    digest = hashlib.sha256(raw).hexdigest()
    runtime_plan = json.loads(json.dumps(plan))
    if 'provision' in runtime_plan:
        for field in ('source_graph_path', 'token_source_path', 'readback_path'):
            runtime_plan['provision'].pop(field)
    data = dict(file_key=plan['file_key'], page_id=plan['page_id'], allowed_page_ids=[plan['page_id']])
    if 'provision' in plan:
        rows = [plan['provision']]
    else:
        rows = plan['specifications']['targets'] if 'specifications' in plan else plan.get('edits', [plan.get('variableedit')])
    ui_plan = dict(tokens=[], components=[], collection_id='', graph_sha256=digest)
    # Standard graph panel carries the same read/apply consent protocol; all edits remain in the pinned plan.
    for index, row in enumerate(rows):
        if 'provision' in plan:
            ui_plan['tokens'].append(dict(key=str(index), root_variable_name='Little Hands booking CTA workbench',
                value='Create or validate one owned frame on the pinned existing page',
                before='Existing page and siblings preserved; main bookingCTA; instances reserve-preview and reserve-login'))
            continue
        if 'specifications' in plan:
            before = (row['before']['specification'] or {}).get('specification', {}).get('display_text', '')
            matches = [e for e in plan['specifications']['board']['entries'] if e['hyperlink'] == {'type':'NODE','value':row['node_id']}]
            if len(matches) != 1:
                raise ValueError('One exact observed board hyperlink per specification target required')
            entry = matches[0]
            ui_plan['tokens'].append(dict(key=str(index), root_variable_name=row['after']['title']+' ('+str(index+1)+')', value=row['after']['display_text'], before=before or entry['characters']))
            continue
        target = (row['node_id'] + '.' + row['field']) if 'node_id' in row else row['variable_id'] + ':' + row['mode_id']
        ui_plan['tokens'].append(dict(key=str(index), root_variable_name=target, value=row['after'], before=row['before']))
    grouped = {}
    for row in plan.get('edits', []):
        main = row.get('main_id', row['node_id'])
        grouped.setdefault(main, {})[row['field']] = str(len(grouped))
    ui_plan['components'] = [dict(id=main, main_keys=[main], instance_keys=[], properties=fields) for main, fields in grouped.items()]
    source = spec_label_prelude() + 'var NATIVE_EDIT_PLAN_SCHEMA = ' + json.dumps(PLAN_SCHEMA) + ';\n' + (ROOT/'figma-bridge/native_semantic_read.js').read_text()
    source += '\nconst NATIVE_EDIT_SESSION = ' + json.dumps(session) + ';\nconst NATIVE_EDIT_SHA256 = ' + json.dumps(digest) + ';\nconst NATIVE_EDIT_PLAN = ' + json.dumps(runtime_plan, ensure_ascii=True, allow_nan=False) + ';\n'
    if 'specifications' in plan:
        for helper in ('native_annotations.js', 'design_note_board.js', 'native_specifications.js'):
            source += '\n' + (ROOT/'figma-bridge'/helper).read_text()
    if 'provision' in plan:
        source += '\n' + (ROOT/'figma-bridge/native_provision.js').read_text()
    source += '\n' + (ROOT/'figma-bridge/native_edit.js').read_text()
    (output/'code.js').write_text(source)
    (output/'ui.html').write_text(graph_panel('sync', data, ui_plan, session=session))
    (output/'native-edit-plan.json').write_bytes(raw)
    if 'specifications' in plan or 'provision' in plan:
        pins = [dict(path=str(Path(plan_path).resolve()), sha256=digest)]
        if 'specifications' in plan:
            pins.append(plan['specifications']['source_graph'])
        else:
            provision = plan['provision']
            pins.extend({'path': provision[path_field], 'sha256': provision[digest_field]} for path_field, digest_field in (
                ('source_graph_path', 'graph_sha256'), ('token_source_path', 'token_source_sha256'), ('readback_path', 'readback_sha256')))
        (output/'source-inputs.json').write_text(json.dumps({'schema':'figma-flow-source-pins-v1','pins':pins}, indent=2)+'\n')
        (output/'source-inputs.json').chmod(0o600)
        (output/'native-edit-plan.json').chmod(0o600)
    manifest = dict(name='Figma Flow · Scoped native edit', api='1.0.0', main='code.js', ui='ui.html', editorType=['figma'], documentAccess='dynamic-page', networkAccess={'allowedDomains':['none']}, enablePrivatePluginApi=True)
    if plugin_id:
        manifest['id'] = plugin_id
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return dict(manifest=str((output/'manifest.json').resolve()), plan=str((output/'native-edit-plan.json').resolve()), file_key=plan['file_key'], page_id=plan['page_id'], plan_sha256=digest, status='prepared-not-executed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare')
    build.add_argument('--plan', required=True)
    build.add_argument('--out', required=True)
    build.add_argument('--plugin-id')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.plan, args.out, args.plugin_id)))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status':'blocked', 'error':str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
