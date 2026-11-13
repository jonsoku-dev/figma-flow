#!/usr/bin/env python3
"""Bind the public typography recipe graph to an operator-selected Design file/page."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'library/figma-recipes/design-type-review.graph.json'
sys.path.insert(0, str(ROOT / 'tools'))
from api_priority import build as build_priority, queue as priority_queue


def build_graph(file_key, page_id, *, baseline_only=False, template=None):
    if not isinstance(file_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', file_key):
        raise ValueError('A valid Figma file key is required.')
    if not isinstance(page_id, str) or not re.fullmatch(r'\d+:\d+', page_id):
        raise ValueError('A valid existing Figma page ID is required.')
    source_template = json.loads(Path(template or TEMPLATE).read_text(encoding='utf-8'))
    if source_template.get('schema') != 'figma-flow-typography-review-graph-template-v1':
        raise ValueError('Unsupported public typography graph template.')
    graph = source_template.get('graph')
    specs = source_template.get('priority_members')
    if (not isinstance(graph, dict) or not isinstance(specs, list) or len(specs) > 20
            or len(graph.get('nodes', [])) + len(specs) > 24):
        raise ValueError('Typography template exceeds the reviewed graph budget.')
    inventory = build_priority(include_public_overlays=not baseline_only)
    rows_by_owner_name = {}
    for row in inventory['rows']:
        rows_by_owner_name.setdefault((row['owner'], row['name']), []).append(row)
    queue_by_receiver = {}
    for spec in specs:
        key = (spec.get('owner'), spec.get('name'))
        matches = rows_by_owner_name.get(key, [])
        if len(matches) != 1:
            raise ValueError(f'Pinned audit does not resolve one exact row for {key[0]}.{key[1]}.')
        row = matches[0]
        receiver = spec.get('receiver')
        if receiver not in row['receiver_types']:
            raise ValueError(f'{row["owner"]}.{row["name"]} is not applicable to receiver {receiver}.')
        if row['feasibility'] not in ('readable-property', 'read-only-method', 'owned-write-method'):
            raise ValueError(f'{row["owner"]}.{row["name"]} has no approved recipe scenario.')
        if spec.get('purpose') and not isinstance(spec['purpose'], str):
            raise ValueError('Every recipe member purpose must be a string.')
        if row['evidence_status'] not in ('observed', 'observed-in-observation-graph'):
            if receiver not in queue_by_receiver:
                queue_by_receiver[receiver] = priority_queue(inventory, limit=None, receiver=receiver)
            if not any(candidate['api_member_id'] == row['api_member_id']
                       for candidate in queue_by_receiver[receiver]):
                raise ValueError(f'{row["owner"]}.{row["name"]} is missing from the {receiver} priority queue.')
        queue_position = next((index + 1 for index, candidate in enumerate(queue_by_receiver.get(receiver, []))
                               if candidate['api_member_id'] == row['api_member_id']), None)
        detail = {
            'api_member_id': row['api_member_id'], 'owner': row['owner'], 'name': row['name'],
            'signature': row['signature'], 'priority_score': row['priority_score'],
            'feasibility': row['feasibility'], 'receiver_types': row['receiver_types'],
            'queue_receiver': receiver, 'queue_position': queue_position,
            'release_status': row['release_status'], 'evidence_status': row['evidence_status'],
            'priority_reasons': row['priority_reasons'],
            'official_source_url': row['official_declaration']['source_url'],
            'purpose': spec.get('purpose', ''),
        }
        graph['nodes'].append({
            'id': 'figma:' + row['api_member_id'], 'type': 'figma',
            'title': row['owner'] + '.' + row['name'],
            'detail': json.dumps(detail, ensure_ascii=False, sort_keys=True),
            'status': 'observed' if detail['evidence_status'] in
                      ('observed', 'observed-in-observation-graph') else 'planned',
            'source': row['official_declaration']['source_url'],
        })
        target = ('component:typography' if row['name'] in {
            'createComponentFromNode', 'setRangeFontName', 'setRangeFontSize', 'setRangeLineHeight',
            'setRangeLetterSpacing', 'setRangeFills', 'cornerRadius', 'effects', 'dashPattern',
            'strokeWeight', 'strokes', 'fills'} else 'test:actual-readback')
        graph['edges'].append({'from': target, 'to': 'figma:' + row['api_member_id'],
                               'type': 'uses prioritized API member'})
    scope_node = next((node for node in graph['nodes'] if node['id'] == 'scope:lab'), None)
    if not scope_node:
        raise ValueError('Typography template has no lab scope node.')
    source = json.loads((ROOT / 'library/figma-api/source.json').read_text())
    scope_node['detail'] = json.dumps({
        'fileKey': file_key, 'pageId': page_id,
        'auditSha256': hashlib.sha256((ROOT / 'library/figma-api/audit/members.json').read_bytes()).hexdigest(),
        'apiSource': source['version'], 'apiSourceRef': source['ref'],
        'priorityInventorySha256': inventory['sha256'], 'recipeVersion': '1.0.0',
        'baselineOnly': baseline_only, 'overlayGraphIds': inventory['source']['overlay_graph_ids'],
        'queueCommands': [
            'python3 tools/api_priority.py build ' + ('--baseline-only ' if baseline_only else '')
            + '--out .figma-flow/api-priority.json',
            *[f'python3 tools/api_priority.py queue --inventory .figma-flow/api-priority.json --receiver {receiver} --limit 10000'
              for receiver in ('TEXT', 'FRAME', 'PluginAPI')],
        ]}, ensure_ascii=False, sort_keys=True)
    return graph


def write_private_new(path, content):
    path = Path(path).expanduser().absolute()
    if (not path.parent.is_dir() or any(parent.is_symlink() for parent in [path, *path.parents])):
        raise ValueError('Output parent must exist and must not contain symlinks.')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file-key', required=True, help='Explicit Figma file key admitted for this lab run')
    parser.add_argument('--page-id', required=True, help='Explicit existing Design page ID admitted for this lab run')
    parser.add_argument('--out', type=Path, required=True, help='New private graph path; it is created without overwrite')
    parser.add_argument('--baseline-only', action='store_true', help='Replay the original 0.29 queue without public overlays')
    parser.add_argument('--template', type=Path, default=TEMPLATE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        graph = build_graph(args.file_key, args.page_id, baseline_only=args.baseline_only, template=args.template)
        sys.path.insert(0, str(ROOT / 'skills/figma-flow/scripts'))
        from graph import validate_graph
        errors, _warnings = validate_graph(graph)
        if errors:
            raise ValueError('Generated graph is invalid: ' + '; '.join(errors[:3]))
        content = (json.dumps(graph, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        write_private_new(args.out, content)
        scope = json.loads(next(node['detail'] for node in graph['nodes'] if node['id'] == 'scope:lab'))
        print(json.dumps({'path': str(args.out), 'graph_id': graph['id'], 'nodes': len(graph['nodes']),
            'edges': len(graph['edges']), 'audit_sha256': scope['auditSha256'],
            'priority_inventory_sha256': scope['priorityInventorySha256'],
            'overlay_graph_ids': scope['overlayGraphIds'], 'mode': oct(args.out.stat().st_mode & 0o777)}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f'design-type-review-graph: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
