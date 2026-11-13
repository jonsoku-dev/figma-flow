#!/usr/bin/env python3
"""Prepare an offline, file-scoped developer-plugin inspection of Design services."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import api_priority

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'library/figma-recipes/inspection'


def prepare(destination, file_key, page_id, plugin_id, *, inventory=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', file_key) or not re.fullmatch(r'\d+:\d+', page_id):
        raise ValueError('A Design file key and existing page ID are required.')
    if not re.fullmatch(r'\d+', plugin_id):
        raise ValueError('Supply the development plugin ID issued by Figma.')
    destination = Path(destination).absolute()
    if destination.exists() or any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError('Choose a new, private output directory.')
    inventory = inventory or api_priority.build(include_public_overlays=True)
    policy = json.loads((RECIPE / 'members.json').read_bytes())
    members = []
    for receiver, spec in policy.items():
        for kind, names in spec.items():
            for name in names:
                candidates = [r for r in inventory['rows'] if r['owner'] == receiver and r['name'] == name
                              and r['kind'] == kind]
                if len(candidates) != 1:
                    raise ValueError(f'Expected one exact {kind} for {receiver}.{name}, found {len(candidates)}.')
                r = candidates[0]
                members.append(dict(id=r['api_member_id'], owner=receiver, name=name, kind=kind,
                                    score=r['priority_score'], evidence_status=r['evidence_status']))
    if len({m['id'] for m in members}) != len(members):
        raise ValueError('Duplicate inspection member.')
    members.sort(key=lambda r: (-r['score'], r['id']))
    graph = dict(version=1, id='design-service-inspection', title='Local Design service and value inspections',
                 nodes=[dict(id='REQ-INSPECT', type='requirement', status='planned', title='Measure the selected Design services')],
                 edges=[])
    for m in members:
        graph['nodes'].append(dict(id=m['id'], type='figma', status='planned', title=m['owner']+'.'+m['name'],
                                   owner=m['owner'], member=m['name'], kind=m['kind'], priority=m['score']))
        graph['edges'].append(dict(type='inspect', **{'from':'REQ-INSPECT','to':m['id']}))
    raw = (json.dumps(graph, ensure_ascii=False, indent=2)+'\n').encode()
    pin = hashlib.sha256(raw).hexdigest()
    scope = dict(file=file_key, page=page_id, sha256=pin, members=members)
    code = 'const INSPECTION = ' + json.dumps(scope, separators=(',', ':')) + ';\n' + (RECIPE/'services.js').read_text()
    manifest = dict(id=plugin_id, name='Figma Flow · Design service inspection', api='1.0.0', main='code.js',
                    editorType=['figma'], documentAccess='dynamic-page', enablePrivatePluginApi=True,
                    networkAccess={'allowedDomains':['none']})
    destination.mkdir(mode=0o700, parents=True)
    for filename, data in [('graph.json', raw), ('code.js', code.encode()),
                           ('manifest.json', (json.dumps(manifest, indent=2)+'\n').encode())]:
        path = destination / filename
        with path.open('xb') as f:
            f.write(data)
        path.chmod(0o600)
    return dict(graph_sha256=pin, selected_members=len(members), output=str(destination))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file-key', required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--plugin-id', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.out, args.file_key, args.page_id, args.plugin_id)))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc)+'\n')
