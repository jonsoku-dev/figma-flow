#!/usr/bin/env python3
"""Bind reviewed browser observations and pinned local images to a canonical graph."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from web_design import image_signature, validate_graph


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bind_screens(captures, graph_id, title, output, asset_index=None):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new graph output; keep the original observation.')
    bindings = {}
    if asset_index is not None:
        for asset in json.loads(Path(asset_index).read_bytes()):
            uri = (asset['origin'], asset['requestTarget'])
            if uri in bindings:
                raise ValueError('Ambiguous image binding')
            bindings[uri] = asset
    nodes, edges = [], []
    for path in captures:
        raw = Path(path).read_bytes()
        capture = json.loads(raw)
        screen = capture['screen']
        screen_id = screen['id']
        if any(not isinstance(e.get('path'), list) for e in [*screen['elements'], *capture['images']]):
            raise ValueError('Capture did not retain ancestor paths; remeasure this screen.')
        if any(node['id'] == screen_id for node in nodes):
            raise ValueError('Duplicate captured screen ID')
        # The paint list keeps DOM order, including images at the same index.
        omissions = Counter()
        for item in reversed(capture['images']):
            key = capture['origin'], item['requestTarget']
            asset = bindings.get(key)
            if not asset:
                omissions['unbound local image'] += 1
                continue
            target = urlsplit(item['requestTarget'])
            if target.scheme or target.netloc or not target.path.startswith('/') or target.fragment:
                raise ValueError('Expected a captured root-relative image request')
            rel = Path(asset['path'])
            if rel.is_absolute() or '..' in rel.parts or not rel.parts:
                raise ValueError('Expected a graph-relative asset file')
            file = output.parent / rel
            if not file.resolve().is_relative_to(output.parent.resolve()) or any(
                part.is_symlink() for part in (file, *file.parents) if part.is_relative_to(output.parent)
            ):
                raise ValueError('Image binding must stay inside the graph asset directory')
            content = file.read_bytes()
            if sha(content) != asset['sha256'] or not image_signature(content, asset['mimeType']):
                raise ValueError('Image content does not match declared signature or SHA-256')
            layer = {k: item[k] for k in ('id', 'box', 'paint', 'path')}
            layer.update(
                kind='image',
                objectFit=item.get('objectFit', 'cover'),
                asset={k: asset[k] for k in ('path', 'sha256', 'mimeType')},
            )
            screen['elements'].insert(item['position'], layer)
        evidence_id = 'OBS-' + screen_id
        nodes += [
            screen,
            {
                'id': evidence_id,
                'type': 'reference',
                'title': screen['title'] + ' browser observation',
                'status': 'observed',
                'detail': 'Browser measurement of rendered geometry, CSS and visible text.',
                'capture_sha256': sha(raw),
                'observed_at': capture['observedAt'],
                'origin': capture['origin'],
                'page_path': capture['pathname'],
                'extent': capture['extent'],
                'viewport': capture['viewport'],
                'limitations': capture['limitations'],
                'omitted_images': dict(omissions),
            },
        ]
        edges.append({'from': screen_id, 'to': evidence_id, 'type': 'sourced from'})
    graph = {'version': 1, 'id': graph_id, 'title': title, 'nodes': nodes, 'edges': edges}
    validate_graph(graph)
    with output.open('x', encoding='utf-8') as store:
        json.dump(graph, store, ensure_ascii=False, indent=2, allow_nan=False)
        store.write('\n')
    return {'graph': str(output), 'sha256': sha(output.read_bytes()), 'screens': len(captures)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--id', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                bind_screens(args.capture, args.id, args.title, args.out, args.assets),
                ensure_ascii=False,
            )
        )
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f'web-design-source: {error}\n')


if __name__ == '__main__':
    main()
