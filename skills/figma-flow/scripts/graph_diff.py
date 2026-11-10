#!/usr/bin/env python3
"""Read-only, byte-pinned graph comparison and static Korean HTML rendering."""

from collections import Counter
from html import escape
import json

import graph
import ssot


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}.")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}.")


def _validate_text(value):
    if isinstance(value, str):
        if graph._has_unpaired_surrogate(value):
            raise ValueError("JSON must not contain unpaired Unicode surrogates.")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_text(key)
            _validate_text(item)
    elif isinstance(value, list):
        for item in value:
            _validate_text(item)


def _read_graph(path):
    try:
        sha, content = ssot.read_local(path, capture=True)
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_invalid_constant)
        _canonical(value)  # Also rejects numeric overflow (for example, 1e999).
        _validate_text(value)
        errors, _ = graph.validate_graph(value, include_figma_warnings=False)
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid graph {path}: {exc}") from exc
    return value, sha


def _pin(document, sha, name):
    inputs = document.get("inputs") if isinstance(document, dict) else None
    ref = inputs.get("graph") if isinstance(inputs, dict) else None
    if not isinstance(ref, dict) or ref.get("availability") != "local-hashed" or ref.get("sha256") != sha:
        raise ValueError(f"{name} graph SHA-256 mismatch; supply the exact pinned graph bytes.")


def _field(node, field):
    return {"present": True, "value": node[field]} if field in node else {"present": False}


def compare_graphs(previous_path, current_path, manifest, check):
    """Compare exact pinned graph bytes by stable node ID and direct edge multiset.

    Object key and node/edge array order do not affect changes. Node field array
    order and JSON value types are significant; absent fields differ from null.
    Every edge field is significant; edge metadata changes are remove/add pairs.
    No commands, evidence reads, network calls, or inferred dependencies occur.
    """
    ssot.validate_manifest(manifest)
    previous, previous_sha = _read_graph(previous_path)
    current, current_sha = _read_graph(current_path)
    _pin(manifest, previous_sha, "Previous manifest")
    _pin(check, current_sha, "Current check")
    explanation = check.get("change_explanation")
    if explanation is not None and (not isinstance(explanation, dict)
            or explanation.get("baseline_manifest_sha256") != manifest["manifest_sha256"]):
        raise ValueError("Change explanation baseline manifest SHA-256 mismatch.")
    before = {node["id"]: node for node in previous["nodes"]}
    after = {node["id"]: node for node in current["nodes"]}
    modified = []
    for node_id in sorted(before.keys() & after.keys()):
        fields = []
        for field in sorted(before[node_id].keys() | after[node_id].keys()):
            old, new = _field(before[node_id], field), _field(after[node_id], field)
            if _canonical(old) != _canonical(new):
                fields.append({"field": field, "old": old, "new": new})
        if fields:
            modified.append({"id": node_id, "fields": fields})
    nodes = {"added": [after[key] for key in sorted(after.keys() - before.keys())],
             "removed": [before[key] for key in sorted(before.keys() - after.keys())],
             "modified": modified}
    old_edges = Counter(_canonical(edge) for edge in previous["edges"])
    new_edges = Counter(_canonical(edge) for edge in current["edges"])
    edges = {"added": [json.loads(edge) for edge in sorted((new_edges - old_edges).elements())],
             "removed": [json.loads(edge) for edge in sorted((old_edges - new_edges).elements())]}
    graph_fields = []
    for field in sorted((previous.keys() | current.keys()) - {"nodes", "edges"}):
        old, new = _field(previous, field), _field(current, field)
        if _canonical(old) != _canonical(new):
            graph_fields.append({"field": field, "old": old, "new": new})
    structural_change = bool(graph_fields or any(nodes.values()) or any(edges.values()))
    changed_ids = {node['id'] for items in nodes.values() for node in items}
    for edge in edges['added'] + edges['removed']:
        changed_ids.update((edge['from'], edge['to']))

    def neighborhood(value):
        incident = [edge for edge in value['edges'] if edge['from'] in changed_ids or edge['to'] in changed_ids]
        visible_ids = changed_ids | {endpoint for edge in incident for endpoint in (edge['from'], edge['to'])}
        return {'nodes': sorted((node for node in value['nodes'] if node['id'] in visible_ids), key=lambda node: node['id']),
                'edges': sorted(incident, key=_canonical)}

    return {"schema_version": 1,
            "comparison_contract": "stable-node-id; typed-json-field-values; missing-distinct-from-null; direct-full-edge-multiset; no-inference",
            "previous": {"sha256": previous_sha}, "current": {"sha256": current_sha},
            "nodes": nodes, "edges": edges, "graph_fields": graph_fields,
            "byte_changed": previous_sha != current_sha, "structural_changed": structural_change,
            "neighborhoods": {"previous": neighborhood(previous), "current": neighborhood(current)},
            "counts": {"graph_fields_modified": len(graph_fields),
                       "nodes_added": len(nodes["added"]), "nodes_removed": len(nodes["removed"]),
                       "nodes_modified": len(modified), "edges_added": len(edges["added"]),
                       "edges_removed": len(edges["removed"])}}


def render_diff(diff, *, has_trace=False):
    """Return a standalone static report; graph content is escaped text only."""
    trace_link = '<p><a href="trace.html">변경 영향 경로 보기</a></p>' if has_trace else ''

    def text(value):
        return escape(str(value), quote=True)

    def value(item):
        if not item["present"]:
            return '<span class="absent">필드 없음</span>'
        return '<pre>' + text(json.dumps(item["value"], ensure_ascii=False, sort_keys=True, indent=2)) + '</pre>'

    def table(rows):
        return ('<div class="scroll" role="region" aria-label="이전과 현재 값 비교" tabindex="0"><table>'
                '<thead><tr><th scope="col">필드</th><th scope="col">이전</th><th scope="col">현재</th></tr></thead>'
                '<tbody>' + ''.join('<tr><th scope="row">' + text(field) + '</th><td>' + value(old)
                                   + '</td><td>' + value(new) + '</td></tr>' for field, old, new in rows)
                + '</tbody></table></div>')

    added_ids = {node['id'] for node in diff['nodes']['added']}
    removed_ids = {node['id'] for node in diff['nodes']['removed']}
    modified_ids = {node['id'] for node in diff['nodes']['modified']}

    def diagram(side, label):
        neighborhood = diff['neighborhoods'][side]
        all_nodes, all_edges = neighborhood['nodes'], neighborhood['edges']
        preview_nodes = all_nodes[:24]
        by_id = {node['id']: node for node in preview_nodes}
        preview_edges = [edge for edge in all_edges if edge['from'] in by_id and edge['to'] in by_id][:40]
        heading = '<h3>' + label + '</h3>'
        if not all_nodes:
            return '<div>' + heading + '<p>변경 노드 또는 연결 이웃 없음</p></div>'

        def chip(node):
            node_id = node['id']
            status = '삭제' if node_id in removed_ids else '추가' if node_id in added_ids else '수정' if node_id in modified_ids else '유지'
            css = {'삭제': 'removed', '추가': 'added', '수정': 'modified', '유지': 'retained'}[status]
            return ('<span class="node-chip ' + css + '"><strong>' + text('[' + status + '] ' + node_id)
                    + '</strong><span>' + text(node['title']) + '</span></span>')

        parts = ['<h4>노드</h4><ul class="node-list">']
        parts.extend('<li>' + chip(node) + '</li>' for node in preview_nodes)
        parts.append('</ul><h4>방향 연결</h4>')
        changes = Counter(_canonical(edge) for edge in diff['edges']['removed' if side == 'previous' else 'added'])
        if preview_edges:
            parts.append('<ol class="relation-list">')
            for edge in preview_edges:
                key = _canonical(edge)
                changed = changes[key] > 0
                if changed:
                    changes[key] -= 1
                status = ('삭제' if side == 'previous' else '추가') if changed else '유지'
                css = ('removed' if side == 'previous' else 'added') if changed else 'retained'
                parts.append('<li class="relation-card ' + css + '"><div class="relation-endpoint"><span class="endpoint-label">출발</span>'
                             + chip(by_id[edge['from']]) + '</div><div class="relationship"><span class="direction" aria-hidden="true">↓</span><strong>'
                             + text('[' + status + ' 연결] ' + edge['type'])
                             + '</strong><span class="relation-route">' + text(edge['from'] + ' → ' + edge['to'])
                             + '</span></div><div class="relation-endpoint"><span class="endpoint-label">도착</span>'
                             + chip(by_id[edge['to']]) + '</div></li>')
            parts.append('</ol>')
        else:
            parts.append('<p>표시할 직접 연결 없음</p>')
        omitted_nodes, omitted_edges = len(all_nodes) - len(preview_nodes), len(all_edges) - len(preview_edges)
        note = ('<p class="detail">미리보기: 노드 ' + str(len(preview_nodes)) + '/' + str(len(all_nodes))
                + ', 연결 ' + str(len(preview_edges)) + '/' + str(len(all_edges))
                + '. 생략: 노드 ' + str(omitted_nodes) + ', 연결 ' + str(omitted_edges)
                + '. 표시한 ID·제목·관계는 줄바꿈하여 전체 값을 보여 줍니다. 전체 변경 값은 아래 표에 표시합니다.</p>')
        return '<div>' + heading + ''.join(parts) + note + '</div>'

    graph_fields = diff["graph_fields"]
    rows = [(item["field"], item["old"], item["new"]) for item in graph_fields]
    sections = ['<section><h2>그래프 공통 필드 변경 · ' + str(len(rows)) + '</h2>'
                + (table(rows) if rows else '<p>없음</p>') + '</section>']
    sections.insert(0, '<section><h2>변경 주변 연결 비교</h2><p>수정된 안정 ID와 그 ID에 직접 연결된 노드·연결을 표시합니다. 유지 연결도 포함합니다. 색상과 [추가]·[삭제]·[수정]·[유지] 표기로 구분합니다.</p><div class="diagrams">'
                    + diagram('previous', '이전 그래프') + diagram('current', '현재 그래프') + '</div></section>')
    for key, label in (("added", "추가 노드"), ("removed", "삭제 노드"), ("modified", "수정 노드")):
        items = []
        for node in diff["nodes"][key]:
            if key == "modified":
                rows = [(item["field"], item["old"], item["new"]) for item in node["fields"]]
            else:
                rows = [(field, _field(node, field) if key == "removed" else {"present": False},
                         _field(node, field) if key == "added" else {"present": False}) for field in sorted(node)]
            items.append('<article><h3>' + text(node["id"]) + '</h3>' + table(rows) + '</article>')
        sections.append('<section><h2>' + label + ' · ' + str(len(items)) + '</h2>'
                        + (''.join(items) or '<p>없음</p>') + '</section>')
    for key, label in (("added", "추가 연결"), ("removed", "삭제 연결")):
        items = []
        for edge in diff["edges"][key]:
            rows = [(field, _field(edge, field) if key == "removed" else {"present": False},
                     _field(edge, field) if key == "added" else {"present": False}) for field in sorted(edge)]
            items.append('<article><h3>' + text(edge["from"]) + ' → ' + text(edge["to"])
                         + ' · ' + text(edge["type"]) + '</h3>' + table(rows) + '</article>')
        sections.append('<section><h2>' + label + ' · ' + str(len(items)) + '</h2>'
                        + (''.join(items) or '<p>없음</p>') + '</section>')
    summary = ('<p>파일 바이트 변경: ' + ('있음' if diff['byte_changed'] else '없음')
               + ' · 구조 변경: ' + ('있음' if diff['structural_changed'] else '없음') + '</p>')
    if diff['byte_changed'] and not diff['structural_changed']:
        summary += '<p>파일 해시는 달라졌지만 비교 대상 필드와 직접 연결의 구조 변경은 없습니다. 객체 키·노드·연결 순서와 파일 형식 차이는 구조 변경으로 세지 않습니다.</p>'
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>그래프 변경 비교</title><style>
*{box-sizing:border-box}body{font:16px/1.6 system-ui,sans-serif;background:#f5f7fa;color:#162235;margin:0}
main{max-width:1120px;margin:auto;padding:24px}h1{font-size:2rem}h2{margin-top:2rem}h3{overflow-wrap:anywhere}
article,.hashes{padding:16px;background:white;border:1px solid #c6cfdb;border-radius:10px;margin:12px 0}
.hashes{display:grid;grid-template-columns:1fr 1fr;gap:16px}.hashes p{margin:0}code{overflow-wrap:anywhere}
.diagrams{display:grid;grid-template-columns:1fr 1fr;gap:16px}.diagrams>div{min-width:0}.detail{font-size:.875rem}
.node-list,.relation-list{list-style:none;padding:0;margin:0}.node-list{display:grid;gap:8px}.node-chip{display:flex;flex-direction:column;min-width:0;padding:10px 12px;background:#fff;border:1px solid #c6cfdb;border-left-width:4px;border-radius:6px;overflow-wrap:anywhere}.node-chip strong{font-size:.875rem}.node-chip span{white-space:pre-wrap}.relation-card{padding:12px;margin:12px 0;border:1px solid #c6cfdb;border-left-width:4px;border-radius:8px;background:#fff;overflow-wrap:anywhere}.relation-endpoint{display:grid;grid-template-columns:3rem minmax(0,1fr);align-items:start;gap:8px}.endpoint-label{padding-top:10px;color:#526176;font-size:.875rem}.relationship{display:flex;flex-direction:column;align-items:flex-start;padding:10px 0 10px 4rem;white-space:pre-wrap}.direction{font-size:1.5rem;line-height:1.2}.relation-route{font-size:.875rem;color:#526176}.added{border-left-color:#116b3d}.removed{border-left-color:#a61b29}.modified{border-left-color:#925900}.retained{border-left-color:#536780}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;table-layout:fixed;min-width:520px}
th,td{padding:12px;text-align:left;vertical-align:top;border:1px solid #c6cfdb;overflow-wrap:anywhere}thead{background:#eaf0f7}
th:first-child{width:22%}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.absent{color:#526176}
:focus-visible{outline:3px solid #125ccc;outline-offset:3px}@media(max-width:800px){.diagrams{grid-template-columns:1fr}}@media(max-width:600px){main{padding:12px}.hashes{grid-template-columns:1fr}}
</style></head><body><main><h1>그래프 변경 비교</h1>
<p>안정 ID로 노드 필드를 비교하고 직접 연결의 추가·삭제를 표시합니다. 중복 연결 수를 보존합니다. 의미나 영향은 추론하지 않습니다.</p>
''' + trace_link + summary + '''<div class="hashes"><div><h2>이전 SHA-256</h2><code>''' + text(diff["previous"]["sha256"]) + '''</code></div>
<div><h2>현재 SHA-256</h2><code>''' + text(diff["current"]["sha256"]) + '</code></div></div>' + ''.join(sections) + '</main></body></html>\n'
