#!/usr/bin/env python3
"""Build an evidence-pinned impact review from explicit graph relations only."""

import argparse
import ast
from html import escape
import hashlib
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'skills' / 'figma-flow' / 'scripts'
sys.path.insert(0, str(SCRIPT_DIR))
import ssot
import graph
import graph_diff


def read_graph(path):
    raw = Path(path).read_bytes()
    graph = json.loads(raw)
    nodes = graph.get('nodes')
    edges = graph.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('graph requires node and edge arrays')
    by_id = {node['id']: node for node in nodes if isinstance(node, dict) and isinstance(node.get('id'), str)}
    if len(by_id) != len(nodes):
        raise ValueError('graph node IDs must be unique strings')
    for edge in edges:
        if not isinstance(edge, dict) or not {'from', 'to', 'type'} <= set(edge) or edge['from'] not in by_id or edge['to'] not in by_id:
            raise ValueError('graph has an invalid edge')
    return graph, by_id, edges, hashlib.sha256(raw).hexdigest()


def build_report(before_path, current_path, policy_id, *, source_root=None):
    source_root = Path(source_root or Path(current_path).absolute().parent).absolute()
    old, old_nodes, _, old_sha = read_graph(before_path)
    current, nodes, edges, current_sha = read_graph(current_path)
    if policy_id not in old_nodes or policy_id not in nodes:
        raise ValueError(f'policy node must exist in both graphs: {policy_id}')
    old_policy, new_policy = old_nodes[policy_id], nodes[policy_id]
    if old_policy == new_policy and old_sha == current_sha:
        raise ValueError('the selected policy and graph are unchanged')
    direct_screens = []
    for edge in edges:
        target = nodes[edge['to']]
        if edge['from'] == policy_id and target.get('type') == 'screen':
            rationale = edge.get('rationale')
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f'missing rationale on policy-to-screen edge: {edge["to"]}')
            direct_screens.append({'id': target['id'], 'title': target['title'], 'relation': edge['type'],
                                   'rationale': rationale})
    acceptance_ids = {edge['to'] for edge in edges if edge['from'] == policy_id and nodes[edge['to']].get('type') == 'acceptance'}
    tests = []
    for edge in edges:
        if edge['from'] in acceptance_ids and edge['type'] == 'checked by' and nodes[edge['to']].get('type') == 'test':
            node = nodes[edge['to']]
            tests.append({'id': node['id'], 'title': node['title'], 'status': node['status'], 'source': node.get('source', '')})
    actions = []
    for edge in edges:
        node = nodes[edge['to']]
        if edge['from'] == policy_id and edge['type'] == 'requires review' and node.get('type') == 'action':
            rationale = edge.get('rationale')
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f'missing rationale on policy-to-action edge: {edge["to"]}')
            actions.append({'id': node['id'], 'title': node['title'], 'webAction': node.get('web_action', ''), 'rationale': rationale})
    business_evidence = _business_evidence(current_path, nodes, edges, tests, policy_id, source_root)
    old_graph, old_nodes, _, _ = read_graph(before_path)
    current_freshness = {item['id']: item['freshness'] for item in business_evidence}
    freshness_changes = []
    for item in business_evidence:
        old_status = _freshness(before_path, old_nodes.get(item['id']), source_root=source_root)
        new_status = current_freshness[item['id']]
        if old_status != new_status:
            freshness_changes.append({'id': item['id'], 'before': old_status, 'current': new_status})
    old_fingerprints = ssot.graph_fingerprints(old_graph)
    current_fingerprints = ssot.graph_fingerprints(current)
    reviewed_ids = {policy_id, *(item['id'] for item in direct_screens),
                    *(item['id'] for item in actions), *(item['id'] for item in tests),
                    *(item['id'] for item in business_evidence), *acceptance_ids}
    graph_freshness = []
    for node_id in sorted(reviewed_ids):
        previous_fingerprint = old_fingerprints.get(node_id)
        current_fingerprint = current_fingerprints.get(node_id)
        if previous_fingerprint != current_fingerprint:
            graph_freshness.append({'id': node_id, 'before': previous_fingerprint,
                                    'current': current_fingerprint, 'status': 'changed-review-required'})
    diff = _compare_graphs(before_path, current_path, old_sha, current_sha)
    policy_node_changes = [item for item in diff['nodes']['modified'] if item['id'] == policy_id]
    policy_edge_changes = {
        'added': [edge for edge in diff['edges']['added'] if edge['from'] == policy_id],
        'removed': [edge for edge in diff['edges']['removed'] if edge['from'] == policy_id],
    }
    strict_errors, strict_warnings = graph.validate_graph(current, strict_local=True, include_figma_warnings=False)
    business_evidence_digest = hashlib.sha256(json.dumps(
        business_evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return {
        'schema': 1,
        'policyId': policy_id,
        'beforeGraphSha256': old_sha,
        'currentGraphSha256': current_sha,
        'policyChanged': old_policy != new_policy,
        'before': old_policy,
        'current': new_policy,
        'directScreens': sorted(direct_screens, key=lambda item: item['id']),
        'actions': sorted(actions, key=lambda item: item['id']),
        'acceptance': [nodes[node_id] for node_id in sorted(acceptance_ids)],
        'tests': sorted(tests, key=lambda item: item['id']),
        'businessEvidence': business_evidence,
        'businessEvidenceSha256': business_evidence_digest,
        'freshnessChanges': freshness_changes,
        'graphFreshness': graph_freshness,
        'graphDiff': {'counts': diff['counts'], 'policyNodeChanges': policy_node_changes,
                      'policyEdgeChanges': policy_edge_changes},
        'freshnessBasis': 'Source hashes and graph declarations only; no test execution or semantic result is claimed.',
        'strictLocal': {'passed': not strict_errors, 'failures': strict_errors, 'warnings': strict_warnings},
        'reviewDecision': 'pending',
        'scopeRule': 'Only explicit policy-to-screen and policy-to-acceptance-to-test edges are included; no name or proximity inference.',
    }


def _compare_graphs(before_path, current_path, before_sha, current_sha):
    manifest = {'version': 1, 'revision': 1,
                'inputs': {'graph': {'availability': 'local-hashed', 'sha256': before_sha}}}
    manifest['manifest_sha256'] = ssot.digest(manifest)
    check = {'inputs': {'graph': {'availability': 'local-hashed', 'sha256': current_sha}}}
    return graph_diff.compare_graphs(before_path, current_path, manifest, check)


def _symbol_digest(path, symbol):
    try:
        source_text = path.read_text(encoding='utf-8')
        tree = ast.parse(source_text, filename=str(path))
        function = next((child for child in ast.walk(tree)
                         if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == symbol), None)
        segment = ast.get_source_segment(source_text, function) if function else None
    except (OSError, UnicodeError, SyntaxError):
        segment = None
    return hashlib.sha256(segment.encode('utf-8')).hexdigest() if segment is not None else None


def _evidence_item(graph_path, node, source_root=None):
    source = node.get('source', '')
    path_ref, separator, symbol = source.partition('#')
    path = ((source_root or Path(graph_path).absolute().parent) / path_ref).resolve()
    item = {'id': node['id'], 'type': node['type'], 'graphStatus': node['status'], 'source': source,
            'freshness': _freshness(graph_path, node, source_root=source_root), 'fileSha256': None, 'symbolSha256': None,
            'symbolFound': False}
    if not path.is_file():
        return item
    raw = path.read_bytes()
    item['fileSha256'] = hashlib.sha256(raw).hexdigest()
    if not separator or not symbol:
        item['symbolFound'] = True
        item['symbolSha256'] = item['fileSha256']
        return item
    symbol_sha = _symbol_digest(path, symbol)
    if symbol_sha is not None:
        item['symbolFound'] = True
        item['symbolSha256'] = symbol_sha
    return item


def _freshness(graph_path, node, *, source_root=None):
    if node is None:
        return 'untracked'
    source = node.get('source', '')
    path_ref = source.split('#', 1)[0]
    path = ((source_root or Path(graph_path).absolute().parent) / path_ref).resolve()
    if not path.is_file():
        return 'source-missing'
    if '#' in source and _symbol_digest(path, source.split('#', 1)[1]) is None:
        return 'symbol-missing'
    if node.get('status') == 'verified':
        return 'source-present-verified-declaration'
    return 'source-present-unverified'


def _business_evidence(graph_path, nodes, edges, tests, policy_id, source_root):
    code_ids = [edge['to'] for edge in edges if edge['from'] == policy_id
        and edge['type'] == 'implemented by' and nodes[edge['to']].get('type') == 'code']
    ids = sorted(set(code_ids) | {test['id'] for test in tests})
    rows = [_evidence_item(graph_path, nodes[node_id], source_root) for node_id in ids]
    return rows


def render_html(report):
    esc = lambda value: escape(str(value), quote=True)
    screens = ''.join('<li><strong>' + esc(item['id']) + ' · ' + esc(item['title']) + '</strong><p>' + esc(item['rationale']) + '</p></li>' for item in report['directScreens'])
    tests = ''.join('<li><strong>' + esc(item['id']) + ' · ' + esc(item['title']) + '</strong><p>상태: ' + esc(item['status']) + ' · ' + esc(item['source']) + '</p></li>' for item in report['tests'])
    acceptance = ''.join('<li><strong>' + esc(item['id']) + ' · ' + esc(item['title']) + '</strong><p>상태: ' + esc(item['status']) + ' · ' + esc(item.get('detail', '')) + '</p></li>' for item in report['acceptance'])
    actions = ''.join('<li><strong>' + esc(item['id']) + ' · ' + esc(item['title']) + '</strong><p>동작: ' + esc(item['webAction']) + ' · ' + esc(item['rationale']) + '</p></li>' for item in report['actions'])
    evidence = ''.join('<li><strong>' + esc(item['id']) + '</strong><p>' + esc(item['source']) + ' · 상태: ' + esc(item['freshness']) + '</p><p>파일 SHA-256: ' + esc(item['fileSha256']) + '</p><p>대상 SHA-256: ' + esc(item['symbolSha256']) + '</p></li>' for item in report['businessEvidence'])
    freshness = ''.join('<li><strong>' + esc(item['id']) + '</strong>: ' + esc(item['before']) + ' → ' + esc(item['current']) + '</li>' for item in report['freshnessChanges'])
    graph_freshness = ''.join('<li><strong>' + esc(item['id']) + '</strong>: graph content changed; review required.</li>' for item in report['graphFreshness'])
    strict_failures = ''.join('<li>' + esc(item) + '</li>' for item in report['strictLocal']['failures'])
    changed_edges = ''.join('<li>' + esc(edge['from'] + ' → ' + edge['to'] + ' · ' + edge['type']) + '</li>' for edge in report['graphDiff']['policyEdgeChanges']['added'])
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>정책 영향 검토</title>'
            '<style>body{font:16px/1.6 system-ui,sans-serif;max-width:900px;margin:3rem auto;padding:0 1rem;color:#292720}code{overflow-wrap:anywhere}li{margin:1rem 0}p{margin:.25rem 0;color:#514a40}</style><body><h1>정책 변경 영향 검토</h1><p>정책: <strong>' + esc(report['policyId']) + '</strong> · 검토 결정: pending</p>'
            '<p>이전 graph SHA-256: <code>' + esc(report['beforeGraphSha256']) + '</code></p><p>현재 graph SHA-256: <code>' + esc(report['currentGraphSha256']) + '</code></p>'
            '<h2>정책 변경 전</h2><p>' + esc(report['before'].get('detail', report['before'].get('title', ''))) + '</p><h2>정책 변경 후</h2><p>' + esc(report['current'].get('detail', report['current'].get('title', ''))) + '</p>'
            '<h2>그래프 전후 비교</h2><p>변경 노드 ' + esc(report['graphDiff']['counts']['nodes_modified']) + ', 추가 연결 ' + esc(report['graphDiff']['counts']['edges_added']) + ', 삭제 연결 ' + esc(report['graphDiff']['counts']['edges_removed']) + '</p><ul>' + changed_edges + '</ul>'
            '<h2>직접 연결된 화면 (' + str(len(report['directScreens'])) + ')</h2><ul>' + screens + '</ul><h2>검토할 테스트 (' + str(len(report['tests'])) + ')</h2><ul>' + tests + '</ul>'
            '<h2>취소·일정 변경 동작 (' + str(len(report['actions'])) + ')</h2><ul>' + actions + '</ul>'
            '<h2>업무 구현·검사 근거 해시</h2><ul>' + evidence + '</ul><h2>근거 추적성 변화</h2><ul>' + (freshness or '<li>이번 비교에서 상태 변화 없음</li>') + '</ul>'
            '<p>근거 묶음 SHA-256: <code>' + esc(report['businessEvidenceSha256']) + '</code></p>'
            '<h2>영향 ID의 그래프 freshness</h2><ul>' + (graph_freshness or '<li>변경 없음</li>') + '</ul>'
            '<h2>엄격 로컬 검사</h2><p>' + ('통과' if report['strictLocal']['passed'] else '실패') + '</p><ul>' + strict_failures + '</ul>'
            '<p>' + esc(report['freshnessBasis']) + '</p><h2>인수 조건</h2><ul>' + acceptance + '</ul>'
            '<p>' + esc(report['scopeRule']) + '</p><p>테스트 상태는 graph에 기록된 상태이며 이번 실행 결과를 뜻하지 않습니다.</p></body></html>')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--current', required=True, type=Path)
    parser.add_argument('--policy', default='REQ-006')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.before, args.current, args.policy)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'impact.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.out / 'index.html').write_text(render_html(report), encoding='utf-8')
    print(f"Wrote policy review for {report['policyId']}: {len(report['directScreens'])} screens, {len(report['tests'])} tests.")


if __name__ == '__main__':
    main()
