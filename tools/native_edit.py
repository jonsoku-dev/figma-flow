#!/usr/bin/env python3
"""Prepare an exact, bounded native edit transaction; preparing never edits Figma."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets

from graph_design_system import SUPPORTED_PROPERTY_TYPES, _validate_property, _validate_value
from graph_sync import graph_panel

ROOT = Path(__file__).resolve().parents[1]
NODE_FIELDS = {'fontSize', 'fontFamily', 'paddingLeft', 'paddingRight', 'backgroundColor', 'color', 'borderRadius'}
ID = re.compile(r'(?:I?\d+:\d+)(?:;\d+:\d+)*\Z')


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get('schema') != 'figma-flow-native-edit-plan-v1':
        raise ValueError('Explicit native edit plan schema required')
    if set(plan) not in ({'schema', 'file_key', 'page_id', 'edits'}, {'schema', 'file_key', 'page_id', 'variableedit'}):
        raise ValueError('Plan requires exact file/page and either edits or variableedit')
    if not isinstance(plan['file_key'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', plan['file_key']) or not isinstance(plan['page_id'], str) or not ID.fullmatch(plan['page_id']):
        raise ValueError('Exact safe native file/page identity required')
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
    output.mkdir(parents=True, exist_ok=False)
    session = secrets.token_hex(16)
    digest = hashlib.sha256(raw).hexdigest()
    data = dict(file_key=plan['file_key'], page_id=plan['page_id'], allowed_page_ids=[plan['page_id']])
    rows = plan.get('edits', [plan.get('variableedit')])
    ui_plan = dict(tokens=[], components=[], collection_id='', graph_sha256=digest)
    # Standard graph panel carries the same read/apply consent protocol; all edits remain in the pinned plan.
    for index, row in enumerate(rows):
        target = (row['node_id'] + '.' + row['field']) if 'node_id' in row else row['variable_id'] + ':' + row['mode_id']
        ui_plan['tokens'].append(dict(key=str(index), root_variable_name=target, value=row['after'], before=row['before']))
    grouped = {}
    for row in plan.get('edits', []):
        main = row.get('main_id', row['node_id'])
        grouped.setdefault(main, {})[row['field']] = str(len(grouped))
    ui_plan['components'] = [dict(id=main, main_keys=[main], instance_keys=[], properties=fields) for main, fields in grouped.items()]
    source = (ROOT/'figma-bridge/native_semantic_read.js').read_text()
    source += '\nconst NATIVE_EDIT_SESSION = ' + json.dumps(session) + ';\nconst NATIVE_EDIT_SHA256 = ' + json.dumps(digest) + ';\nconst NATIVE_EDIT_PLAN = ' + json.dumps(plan, ensure_ascii=True, allow_nan=False) + ';\n'
    source += (ROOT/'figma-bridge/native_edit.js').read_text()
    (output/'code.js').write_text(source)
    (output/'ui.html').write_text(graph_panel('sync', data, ui_plan, session=session))
    (output/'native-edit-plan.json').write_bytes(raw)
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
