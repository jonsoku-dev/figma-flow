"""Project explicitly selected product graph records for native review surfaces."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts'))
from graph import validate_graph

# Review surfaces group original node types while preserving their identities and status.
KINDS = {'requirement': 'requirement', 'acceptance': 'requirement', 'screen': 'screen',
         'state': 'screen', 'action': 'screen', 'component': 'component', 'design-token': 'component',
         'test': 'evidence', 'code': 'evidence', 'reference': 'evidence', 'figma': 'evidence'}


def project_graph(path, selected_ids):
    path = Path(path)
    raw = path.read_bytes()
    graph = json.loads(raw)
    errors, _ = validate_graph(graph)
    if errors:
        raise ValueError('Invalid canonical graph: ' + '; '.join(errors[:3]))
    by_id = {node['id']: node for node in graph['nodes']}
    ids = list(selected_ids or [])
    if not ids:
        ids = list(by_id)
    if not 1 <= len(ids) <= 24 or len(set(ids)) != len(ids) or any(key not in by_id for key in ids):
        raise ValueError('Select 1–24 distinct existing review node IDs with --node')
    selected = set(ids)
    edges = [{'from': edge['from'], 'to': edge['to'], 'type': edge['type']}
             for edge in graph['edges'] if edge['from'] in selected and edge['to'] in selected]
    if len(edges) > 48:
        raise ValueError('Select a smaller subgraph with at most 48 relationships')
    nodes = []
    for key in ids:
        node = by_id[key]
        detail = node.get('detail') or ''
        if not isinstance(detail, str) or len(detail) > 4000 or len(node['title']) > 512 or len(key) > 256:
            raise ValueError(f'Review content exceeds the presentation bounds: {key[:64]}')
        nodes.append({'id': key, 'kind': KINDS[node['type']], 'type': node['type'],
                      'title': node['title'], 'detail': detail, 'status': node['status']})
    # A path or payload hash is not a stable project identity. Older design-system
    # graphs may already have one in the actual design_system declaration.
    identity = graph.get('id') or (graph.get('design_system') or {}).get('id')
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 180:
        raise ValueError('The canonical graph requires a stable id (or an existing design_system.id)')
    title = graph.get('title', identity)
    if not isinstance(title, str) or not title.strip() or len(title) > 512:
        raise ValueError('Review graph title must be a nonempty string up to 512 characters')
    return {'id': identity, 'title': title, 'nodes': nodes, 'edges': edges}, hashlib.sha256(raw).hexdigest()


def selection_sha256(graph):
    """The ordered review is a second identity within the exact source graph."""
    return hashlib.sha256(json.dumps(graph, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def typescript_projection(graph, sha):
    # This is a generated literal preceding reviewed recipe code, without eval or a URL loader.
    return ('type FlowReviewNode = {id:string;kind:"requirement"|"screen"|"component"|"evidence";'
            'type:string;title:string;detail:string;status:string};\n'
            'type FlowReviewEdge = {from:string;to:string;type:string};\n'
            'const FLOW_REVIEW_GRAPH: {id:string;title:string;nodes:FlowReviewNode[];edges:FlowReviewEdge[]} = '
            + json.dumps(graph, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
            + ';\nconst FLOW_REVIEW_GRAPH_SHA256 = ' + json.dumps(sha)
            + ';\nconst FLOW_REVIEW_SELECTION_SHA256 = ' + json.dumps(selection_sha256(graph)) + ';\n')
