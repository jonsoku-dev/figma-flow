#!/usr/bin/env python3
"""Compile and plan bounded updates from canonical graph and supplied cached evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from native_edit import PLAN_SCHEMA
from native_handoff import normalize
from specification_contract import NATIVE_SCHEMA, derive_specifications, render_screen_spec, validate_specification, connected_annotation_markdown


def load(path):
    return json.loads(Path(path).read_text())


def compile_graph(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    graph = json.loads(raw)
    return graph, {'path': str(path), 'sha256': sha}, derive_specifications(graph, source_graph_sha256=sha)


def _board_ref(board, row):
    entries = [entry for entry in board['entries'] if entry['hyperlink'] == {'type': 'NODE', 'value': row['node_id']}]
    if len(entries) != 1:
        raise ValueError('one exact connected specification entry required')
    return {'boardId': board['node_id'], 'textNodeId': entries[0]['textNodeId'],
            'key': entries[0]['key'][len(board['key']) + 1:]}


def _after_annotations(row, observed):
    previous = (row['before']['specification'] or {}).get('human_annotation')
    removed = {slot['index'] for slot in row['legacy_annotations']}
    if previous:
        removed.add(previous['index'])
    result = [value for index, value in enumerate(row['before']['annotations']) if index not in removed]
    if row['after'].get('presentation') == 'connected-spec-v2':
        human = (observed.get('specification') or {}).get('human_annotation') or {}
        index = previous['index'] if previous else row['legacy_annotations'][0]['index'] if row['legacy_annotations'] else len(result)
        result.insert(min(index, len(result)), human.get('annotation'))
    return result


def _valid_font(font):
    if not isinstance(font, dict) or not {'family', 'style'} <= set(font) or set(font) - {'family', 'style', 'variationSettings'}:
        return False
    if not all(isinstance(font[key], str) and font[key].strip() for key in ('family', 'style')):
        return False
    if 'variationSettings' not in font:
        return True
    settings = font['variationSettings']
    return (
        isinstance(settings, dict) and len(settings) <= 16
        and all(isinstance(axis, str) and re.fullmatch(r'[A-Za-z0-9]{4}', axis) and isinstance(value, (int, float))
                and not isinstance(value, bool) and math.isfinite(value) and abs(value) <= 10000
                for axis, value in settings.items())
    )


def export(graph_path, out):
    graph, pin, specs = compile_graph(graph_path)
    output = Path(out)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    contract = {'schema': 'figma-flow-specification-export-v1', 'source_graph': pin, 'specifications': specs}
    (output/'specifications.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2)+'\n')
    (output/'screen-spec.md').write_text(render_screen_spec(graph, source_graph_sha256=pin['sha256']))
    (output/'contract.json').write_text(json.dumps({'schema': contract['schema'], 'source_graph': pin, 'specification_ids': [s['id'] for s in specs]}, indent=2)+'\n')
    return contract


def snapshot(raw, board_key):
    observed, parents = normalize(raw)
    nodes = {}
    for identity, original in observed.items():
        node = dict(original)
        aliases = {node[field] for field in ('semanticKey', 'key', 'semantic_id') if isinstance(node.get(field), str) and node[field]}
        if len(aliases) > 1:
            raise ValueError('conflicting observed native semantic identities')
        if aliases:
            node['semanticKey'] = aliases.pop()
        nodes[identity] = node
    pages = [n['id'] for n in nodes.values() if n.get('type') == 'PAGE']
    page = raw.get('pageId') or (pages[0] if len(pages) == 1 else None)
    file = raw.get('fileKey') or raw.get('file_key')
    if not isinstance(file, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file) or not isinstance(page, str) or not re.fullmatch(r'\d+:\d+', page):
        raise ValueError('actual snapshot file/page identity required')
    def within(identity):
        seen = set()
        while identity and identity not in seen:
            if identity == page:
                return True
            seen.add(identity)
            identity = parents.get(identity)
        return False
    boards = [n for n in nodes.values() if n.get('semanticKey') == board_key and parents[n['id']] == page]
    if len(boards) != 1:
        raise ValueError('one existing owned board required')
    board = boards[0]
    if board.get('type') != 'FRAME' or board.get('visible') is False or board.get('layoutMode') != 'VERTICAL' or not isinstance(board.get('itemSpacing'), (int,float)) or board['itemSpacing'] <= 0:
        raise ValueError('actual visible vertical board required')
    page_node = nodes.get(page, {})
    owner_hash = raw.get('page_owner') or page_node.get('declared_metadata', {}).get('source_sha256')
    owner = board.get('designNoteBoard')
    if owner is None and owner_hash:
        owner = {'pageId': page, 'sourceHash': owner_hash}
    if not isinstance(owner, dict) or set(owner) != {'pageId', 'sourceHash'} or owner['pageId'] != page or not re.fullmatch(r'[a-fA-F0-9]{64}', owner.get('sourceHash', '')) or owner_hash and owner_hash != owner['sourceHash']:
        raise ValueError('known immutable page/board ownership required')
    children = [n for n in nodes.values() if parents[n['id']] == board['id']]
    entries = []
    for child in children:
        key = child.get('semanticKey')
        if child.get('visible') is False or not isinstance(child.get('fontSize'), (int,float)) or child['fontSize'] < 14:
            raise ValueError('actual visible readable board text required')
        if child.get('type') != 'TEXT' or not isinstance(key, str) or not key.startswith(board_key+':') or not isinstance(child.get('characters'), str) or 'hyperlink' not in child:
            raise ValueError('unknown or unavailable board child')
        if key != board_key+':title' and (child['hyperlink'] or {}).get('type') != 'NODE':
            raise ValueError('actual board target hyperlink required')
        if key != board_key+':title' and not within(child['hyperlink'].get('value')):
            raise ValueError('board hyperlink target outside page')
        if key != board_key+':title' and (child['hyperlink']['value'] not in nodes or not nodes[child['hyperlink']['value']].get('semanticKey')):
            raise ValueError('unknown board child semantic/link binding')
        entries.append({'key': key, 'textNodeId': child['id'], 'characters': child['characters'], 'hyperlink': child['hyperlink']})
    if not entries or len({e['key'] for e in entries}) != len(entries):
        raise ValueError('unique existing board entries required')
    fonts = [n.get('fontName') for n in children]
    if not fonts or any(f != fonts[0] for f in fonts) or not _valid_font(fonts[0]):
        raise ValueError('uniform observed board font required')
    return file, page, nodes, within, {'key': board_key, 'node_id': board['id'], 'owner': owner, 'font': fonts[0], 'entries': entries}


def plan(graph_path, readback, targets=(), board_key='design-note-board'):
    _, pin, specs = compile_graph(graph_path)
    file, page, nodes, within, board = snapshot(readback, board_key)
    bindings = {}
    for value in targets:
        note, sep, key = value.partition('=')
        if not sep or not note or not key or note in bindings:
            raise ValueError('unique NOTE_ID=NATIVE_SEMANTIC_KEY required')
        bindings[note] = key
    if set(bindings)-{s['id'] for s in specs}:
        raise ValueError('unknown graph note id')
    chosen = [s for s in specs if not bindings or s['id'] in bindings]
    rows = []
    for spec in chosen:
        key = bindings.get(spec['id'], spec['target_id'])
        matches = [n for n in nodes.values() if n.get('semanticKey') == key and within(n['id'])]
        if len(matches) != 1:
            raise ValueError('exact unique native semantic binding required: '+key)
        node = matches[0]
        entries = [e for e in board['entries'] if e['hyperlink'] == {'type': 'NODE', 'value': node['id']}]
        if len(entries) != 1:
            raise ValueError('existing exact board entry/link required: '+key)
        if node.get('specification_status') == 'invalid' or not isinstance(node.get('annotations'), list):
            raise ValueError('actual annotations/private metadata unavailable')
        previous = node.get('specification')
        if previous is not None:
            if (not isinstance(previous, dict) or previous.get('schema') != NATIVE_SCHEMA
                    or previous.get('semantic_key') != key or previous.get('target_id') != node['id']
                    or previous.get('source_owner_hash') != board['owner']['sourceHash'] or previous.get('state') != 'applied'
                    or not isinstance(previous.get('legacy_annotations'), list)
                    or entries[0]['characters'] != previous.get('specification', {}).get('title', '')+'\n'+previous.get('specification', {}).get('display_text', '')):
                raise ValueError('edited or invalid prior specification/display ownership')
        annotations = node['annotations']
        legacy = [{'index': i, 'annotation': a} for i, a in enumerate(annotations) if isinstance(a, dict) and str(a.get('label', '')).startswith('[figma-flow:'+key+']')]
        legacy_proof = None
        if previous is None and not legacy:
            previous_text = entries[0]['characters']
            metadata = node.get('declared_metadata', {})
            page_meta = nodes[page].get('declared_metadata', {})
            entry_key = entries[0]['key'][len(board_key)+1:]
            candidates = [{'index': i, 'annotation': a} for i, a in enumerate(annotations)
                          if isinstance(a, dict) and isinstance(a.get('label'), str) and a['label']
                          and previous_text == f"{node.get('name', '')} · {entry_key}\n{a['label']}\n화면·조작으로 이동"]
            if candidates:
                if (len(candidates) != 1 or metadata.get('annotation_mode') != 'native'
                        or metadata.get('semantic_id') != key or page_meta.get('source_sha256') != board['owner']['sourceHash']
                        or not isinstance(node.get('name'),str) or not node['name']):
                    raise ValueError('private import ownership required for unprefixed legacy annotation')
                legacy = candidates
                legacy_proof = {'annotation_mode': metadata['annotation_mode'], 'semantic_id': metadata['semantic_id'], 'page_source_sha256': page_meta['source_sha256'], 'target_name':node['name'], 'legacy_body':previous_text}
        if previous is not None and (legacy or any(slot.get('annotation') in annotations for slot in previous.get('legacy_annotations', []))):
            raise ValueError('unexpected legacy annotation on an applied specification')
        if len(legacy) > 1:
            raise ValueError('duplicate legacy annotation')
        rows.append({'node_id': node['id'], 'semantic_key': key, 'before': {'specification': node.get('specification'), 'annotations': annotations}, 'after': spec, 'legacy_annotations': legacy, 'legacy_proof': legacy_proof})
    result = {'schema': PLAN_SCHEMA, 'file_key': file, 'page_id': page, 'specifications': {'source_graph': pin, 'board': board, 'targets': rows}}
    validate_update(result)
    return result


def validate_update(plan):
    value = plan['specifications']
    if not isinstance(value, dict) or set(value) != {'source_graph', 'board', 'targets'}:
        raise ValueError('exact specifications contract required')
    pin, board, rows = value['source_graph'], value['board'], value['targets']
    if not isinstance(pin, dict) or set(pin) != {'path', 'sha256'} or not Path(pin['path']).is_absolute():
        raise ValueError('absolute source graph pin required')
    _, current, specs = compile_graph(pin['path'])
    if current != pin:
        raise ValueError('source graph changed; obtain a fresh plan')
    if not isinstance(board, dict) or set(board) != {'key', 'node_id', 'owner', 'font', 'entries'} or board['owner'].get('pageId') != plan['page_id']:
        raise ValueError('exact owned board snapshot required')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError('1–32 specification targets required')
    if (not isinstance(board['key'], str) or not board['key'] or not re.fullmatch(r'\d+:\d+', board['node_id'])
            or set(board['owner']) != {'pageId', 'sourceHash'} or not re.fullmatch(r'[a-fA-F0-9]{64}', board['owner']['sourceHash'])
            or not _valid_font(board['font'])
            or not isinstance(board['entries'], list) or not board['entries']):
        raise ValueError('valid board identity/owner/font/entries required')
    entry_ids, entry_keys = set(), set()
    for entry in board['entries']:
        if (not isinstance(entry, dict) or set(entry) != {'key','textNodeId','characters','hyperlink'}
                or not isinstance(entry['characters'], str) or not isinstance(entry['key'], str)
                or not entry['key'].startswith(board['key']+':') or not re.fullmatch(r'\d+:\d+', entry['textNodeId'])
                or entry['key'] in entry_keys or entry['textNodeId'] in entry_ids):
            raise ValueError('unique exact board child snapshots required')
        entry_keys.add(entry['key']); entry_ids.add(entry['textNodeId'])
        link = entry['hyperlink']
        if entry['key'] != board['key']+':title' and (not isinstance(link, dict) or set(link) != {'type','value'} or link['type'] != 'NODE' or not isinstance(link['value'],str) or not re.fullmatch(r'\d+:\d+',link['value'])):
            raise ValueError('exact board child native hyperlink required')
    seen, keys = set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'node_id', 'semantic_key', 'before', 'after', 'legacy_annotations', 'legacy_proof'} or not re.fullmatch(r'\d+:\d+', row['node_id']) or row['node_id'] in seen:
            raise ValueError('unique exact specification targets required')
        seen.add(row['node_id'])
        if not isinstance(row['semantic_key'], str) or not row['semantic_key'].strip() or row['semantic_key'] in keys:
            raise ValueError('unique full native semantic keys required')
        keys.add(row['semantic_key'])
        if row['after'] not in specs or not row['after']['display_text'].strip():
            raise ValueError('after specification must be recompiled from current graph meaning')
        if set(row['before']) != {'specification', 'annotations'} or not isinstance(row['before']['annotations'], list):
            raise ValueError('exact metadata/annotation before snapshots required')
        previous = row['before']['specification']
        if previous is not None:
            if not isinstance(previous, dict) or not isinstance(previous.get('specification'), dict):
                raise ValueError('valid previous private specification required')
            report = validate_specification(previous['specification'], previous, native_id=row['node_id'], semantic_key=row['semantic_key'],
                source_owner_hash=board['owner']['sourceHash'], require_trace=False, annotations=row['before']['annotations'],
                file_key=plan['file_key'], board_ref=_board_ref(board, row))
            if report['errors']:
                raise ValueError('invalid previous private specification: '+str(report['errors']))
        if len([e for e in board['entries'] if e['hyperlink'] == {'type':'NODE','value':row['node_id']}]) != 1:
            raise ValueError('exact existing display binding required')
        linked = [e for e in board['entries'] if e['hyperlink'] == {'type':'NODE','value':row['node_id']}]
        expected = [{'index': i, 'annotation': a} for i,a in enumerate(row['before']['annotations']) if isinstance(a,dict) and str(a.get('label','')).startswith('[figma-flow:'+row['semantic_key']+']')]
        proof = row['legacy_proof']
        if proof is not None:
            if (not isinstance(proof,dict) or set(proof) != {'annotation_mode','semantic_id','page_source_sha256','target_name','legacy_body'}
                    or proof.get('annotation_mode') != 'native' or proof.get('semantic_id') != row['semantic_key'] or proof.get('page_source_sha256') != board['owner']['sourceHash']
                    or not isinstance(proof['target_name'],str) or not proof['target_name']
                    or not isinstance(proof['legacy_body'],str)
                    or len(linked) != 1):
                raise ValueError('exact private legacy ownership proof required')
            entry_key = linked[0]['key'][len(board['key'])+1:]
            plain = [{'index':i,'annotation':a} for i,a in enumerate(row['before']['annotations']) if isinstance(a,dict) and isinstance(a.get('label'),str) and a['label'] and proof['legacy_body'] == f"{proof['target_name']} · {entry_key}\n{a['label']}\n화면·조작으로 이동" and linked[0]['characters'] == proof['legacy_body']]
            if len(plain) != 1:
                raise ValueError('unique exact unprefixed legacy slot required')
            expected.extend(plain)
        archived = (row['before']['specification'] or {}).get('legacy_annotations', [])
        if row['before']['specification'] is not None and (expected or any(slot.get('annotation') in row['before']['annotations'] for slot in archived)):
            raise ValueError('unexpected legacy annotation on an applied specification')
        if len(expected)>1 or row['legacy_annotations'] != expected:
            raise ValueError('exact unique legacy slot archive required')
        if (proof is None) != (not row['legacy_annotations'] or str(row['legacy_annotations'][0]['annotation'].get('label','')).startswith('[figma-flow:')):
            raise ValueError('legacy proof presence does not match annotation ownership mode')
    return plan


def verify(graph_path, prepared, readback):
    validate_update(prepared)
    _, pin, specs = compile_graph(graph_path)
    if pin != prepared['specifications']['source_graph']:
        raise ValueError('verification graph differs from prepared source')
    file, page, nodes, within, board = snapshot(readback, prepared['specifications']['board']['key'])
    errors, reports = [], []
    if (file,page,board['node_id'],board['owner']) != (prepared['file_key'],prepared['page_id'],prepared['specifications']['board']['node_id'],prepared['specifications']['board']['owner']):
        errors.append('actual file/page/board ownership differs')
    for row in prepared['specifications']['targets']:
        actual = nodes.get(row['node_id'], {})
        spec = next(s for s in specs if s['id'] == row['after']['id'])
        report = validate_specification(spec, actual.get('specification'), native_id=actual.get('id'), semantic_key=actual.get('semanticKey'),
            source_owner_hash=board['owner']['sourceHash'], annotations=actual.get('annotations'), file_key=file,
            board_ref=_board_ref(board, row))
        reports.append(report)
        if not within(row['node_id']):
            errors.append('actual target is outside prepared page')
        if actual.get('semanticKey') != row['semantic_key']:
            errors.append('actual target semantic key differs from plan')
        if row['legacy_proof'] is not None and (actual.get('declared_metadata',{}).get('annotation_mode') != 'native' or actual.get('declared_metadata',{}).get('semantic_id') != row['semantic_key'] or nodes[page].get('declared_metadata',{}).get('source_sha256') != board['owner']['sourceHash'] or actual.get('name') != row['legacy_proof']['target_name']):
            errors.append('actual private import legacy ownership proof differs')
        archive = (row['before']['specification'] or {}).get('legacy_annotations', []) + row['legacy_annotations']
        if (actual.get('specification') or {}).get('legacy_annotations') != archive:
            errors.append('private legacy archive differs')
        remaining = _after_annotations(row, actual)
        if any(str(a.get('label','')).startswith('[figma-flow:'+row['semantic_key']+']') for a in actual.get('annotations',[]) if isinstance(a,dict)):
            errors.append('owned legacy annotation remains on artwork')
        if actual.get('annotations') != remaining:
            errors.append('user annotations or legacy removal differ')
        planned_entry = next((entry for entry in prepared['specifications']['board']['entries'] if entry['hyperlink']=={'type':'NODE','value':row['node_id']}),None)
        if not any(planned_entry and e['textNodeId']==planned_entry['textNodeId'] and e['key']==planned_entry['key'] and e['characters']==spec['title']+'\n'+spec['display_text'] and e['hyperlink']==planned_entry['hyperlink'] for e in board['entries']):
            errors.append('actual display text/link differs')
    for planned in prepared['specifications']['board']['entries']:
        actual = next((entry for entry in board['entries'] if entry['textNodeId']==planned['textNodeId']),None)
        row = next((row for row in prepared['specifications']['targets'] if isinstance(planned['hyperlink'],dict) and row['node_id']==planned['hyperlink'].get('value')),None)
        expected_text = (next(spec for spec in specs if spec['id']==row['after']['id'])['title']+'\n'+row['after']['display_text']) if row else planned['characters']
        if not actual or actual['key'] != planned['key'] or actual['hyperlink'] != planned['hyperlink'] or actual['characters'] != expected_text:
            errors.append('actual board child identity or display differs')
    return {'schema':'figma-flow-specification-update-validation-v1','passed':not errors and all(r['passed'] for r in reports),'errors':errors,'targets':reports,'evidence':'supplied cached getter; actual origin unverified'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    for name in ('export','plan','verify'):
        sub=subs.add_parser(name);sub.add_argument('--graph',required=True)
        if name!='export': sub.add_argument('--readback',required=True)
        if name!='verify': sub.add_argument('--out',required=True)
        if name=='plan': sub.add_argument('--target',action='append',default=[]);sub.add_argument('--board-key',default='design-note-board')
        if name=='verify': sub.add_argument('--plan',required=True)
    args=parser.parse_args()
    try:
        if args.command=='export': result=export(args.graph,args.out)
        elif args.command=='plan':
            result=plan(args.graph,load(args.readback),args.target,args.board_key)
            with Path(args.out).open('x') as stream: json.dump(result,stream,ensure_ascii=False,indent=2)
            Path(args.out).chmod(0o600)
        else: result=verify(args.graph,load(args.plan),load(args.readback))
        print(json.dumps(result,ensure_ascii=False));return 1 if result.get('passed') is False else 0
    except (OSError,ValueError,TypeError,KeyError) as error:
        print(json.dumps({'status':'blocked','error':str(error)}));return 1

if __name__=='__main__': raise SystemExit(main())
