#!/usr/bin/env python3
"""Create an immutable offline Korean trace viewer from a graph and SSOT check JSON."""

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import graph
import ssot


STYLE = """
:root{color-scheme:dark;--bg:#10151b;--panel:#19212b;--line:#344252;--text:#eef3f7;--muted:#b8c5d2;--accent:#91dfce}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,sans-serif}header,main,footer{max-width:1440px;margin:auto;padding:24px}header{border-bottom:1px solid var(--line)}h1{font-size:clamp(26px,4vw,40px);margin:4px 0}h2{font-size:21px;margin:0 0 16px}h3{font-size:17px}p{margin:8px 0}.eyebrow{color:var(--accent);letter-spacing:.1em;font-size:12px}.muted,small{color:var(--muted)}main{display:grid;grid-template-columns:280px minmax(0,1fr);gap:24px}aside,section{min-width:0}.panel{padding:20px;background:var(--panel);border:1px solid var(--line);border-radius:12px;margin-bottom:20px}label{display:block;margin:12px 0 6px}select,input{width:100%;padding:10px;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;font:inherit}button{font:inherit;cursor:pointer;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--text);padding:6px 10px;text-align:left;overflow-wrap:anywhere}button:hover{border-color:var(--accent)}:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.nodes{list-style:none;padding:0;max-height:470px;overflow:auto}.nodes li{margin:8px 0}.nodes button{width:100%}.nodes button[aria-current=true]{border-color:var(--accent);background:#203c3a}.badge{display:inline-block;font-size:13px;padding:2px 8px;border:1px solid #66798c;border-radius:20px;margin:3px 5px 3px 0}.stale,.blocked{color:#ffd5a4;border-color:#d4a063}.unverified{color:#f0ccf4;border-color:#bb8cc0}.content-current,.verified{color:var(--accent);border-color:#68ab9b}.path{margin:14px 0;padding:12px;border:1px solid var(--line);border-radius:8px}.steps{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.edge{color:var(--accent);font-size:13px;overflow-wrap:anywhere}.relation{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg);padding:12px;border-radius:6px;font-size:13px}code{overflow-wrap:anywhere}ul{padding-left:22px}.detail-text{white-space:pre-wrap;overflow-wrap:anywhere}footer{font-size:13px;color:var(--muted)}details{margin-top:16px}summary{cursor:pointer}#detail-title{scroll-margin:20px}@media(max-width:760px){main{grid-template-columns:1fr;padding:16px;gap:0}header,footer{padding:20px}.nodes{max-height:220px}.panel{padding:16px}}@media(prefers-reduced-motion:no-preference){button{transition:border-color .12s}}
"""

SCRIPT = r"""
'use strict';
const data = JSON.parse(document.getElementById('trace-data').textContent);
const nodes = new Map(data.graph.nodes.map(node => [node.id, node]));
const outgoing = new Map(), incoming = new Map();
for (const id of nodes.keys()) { outgoing.set(id, []); incoming.set(id, []); }
for (const edge of data.graph.edges) { outgoing.get(edge.from).push(edge); incoming.get(edge.to).push(edge); }
const types = {requirement:'요구사항',screen:'화면',state:'상태',action:'동작',figma:'Figma',code:'코드',test:'테스트',acceptance:'인수 기준','design-token':'디자인 토큰',component:'컴포넌트'};
const explanation = data.change_explanation;
const changeKinds = {added:'추가됨',removed:'삭제됨','node-or-incident-graph-changed':'노드 또는 연결 정보 변경','evidence-changed':'증거 변경','prior-stale-unresolved':'이전 오래됨 상태가 미해결','direct-change':'직접 변경','authority-or-bindings-changed':'권위 또는 바인딩 변경','brief-changed':'요구사항 원문 변경','historic-only-unknown':'과거 기록만 남음 · 원인 알 수 없음'};
const edgePresence = {both:'이전·현재 연결','current-only':'현재에만 있는 연결','previous-only':'이전에만 있던 연결 · 현재 삭제됨'};
const statuses = {planned:'계획됨',observed:'관찰됨',verified:'검증됨',blocked:'차단됨',unverified:'미검증','content-current':'내용 일치',stale:'오래됨'};
let selected = null;
function el(tag, text, cls) { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (cls) item.className = cls; return item; }
function badge(value) { return el('span', (statuses[value] || value) + ' · ' + value, 'badge ' + value); }
function nodeButton(id) { const node = nodes.get(id), button = el('button', node.id + ' · ' + node.title); button.type = 'button'; button.addEventListener('click', () => showNode(id, true)); return button; }
function referenceText(ref) { return ref ? ref.path + ' · ' + ref.availability + ' · SHA-256: ' + (ref.sha256 || '없음') : '없음'; }
function appendChange(parent, label, change) {
  const row = el('div', undefined, 'path'); row.append(el('h3', label), el('p', '이전: ' + referenceText(change.previous), 'detail-text'), el('p', '현재: ' + referenceText(change.current), 'detail-text')); parent.append(row);
}
function changeNode(id) { return nodes.has(id) ? nodeButton(id) : el('span', id + ' · 현재 그래프에 없음'); }
function renderChangeSummary() {
  const box = document.getElementById('change-summary');
  if (!explanation) { box.append(el('p', '이 검사에는 변경 설명이 없습니다. 이전 형식의 검사 결과에서 변경 원인이나 전파 경로를 추정하지 않습니다.')); return; }
  box.append(el('p', '검사 결과가 기록한 변경 출발점과 의존성 전파입니다. 위 연결 경로 탐색과는 별개이며, 연결 자체는 변경 원인이 아닙니다.', 'muted'));
  box.append(el('p', '비교 기준 manifest SHA-256: ' + (explanation.baseline_manifest_sha256 || '없음 · 최초 검사'), 'detail-text'));
  box.append(el('p', '해시 차이와 선언된 의존성의 최단 경로 하나를 표시합니다. 의미 변화나 검증된 인과관계를 증명하지 않습니다. 이전부터 오래된 상태의 원인은 이 기준 기록만으로 복구할 수 없습니다.', 'muted'));
  const origins = Object.entries(explanation.direct_nodes);
  if (!origins.length) box.append(el('p', '기록된 직접 노드 변경 없음.'));
  for (const [id, origin] of origins) {
    const row = el('div', undefined, 'path'); row.append(changeNode(id), el('p', origin.categories.map(kind => changeKinds[kind] || kind).join(', ')));
    if (origin.historic_only) row.append(el('p', '과거 기록만 남아 실제 변경 원인을 알 수 없습니다.'));
    row.append(el('p', '노드 지문 이전: ' + (origin.previous_content_sha256 || '없음'), 'detail-text'), el('p', '노드 지문 현재: ' + (origin.current_content_sha256 || '없음'), 'detail-text'));
    for (const change of origin.evidence_changes) appendChange(row, '증거 경로: ' + change.path, change);
    box.append(row);
  }
  for (const change of explanation.changed_inputs) appendChange(box, '변경 입력: ' + change.key, change);
  for (const change of explanation.changed_authorities) appendChange(box, '변경 권위: ' + change.key, change);
}
function renderChangePath(box, id, evidence) {
  box.append(el('h3', '이 노드가 오래된 이유'));
  if (!explanation) { box.append(el('p', '이전 형식의 검사 결과에는 의존성 전파 설명이 없습니다. 이유를 추정하지 않습니다.')); return; }
  if (evidence.freshness !== 'stale') { box.append(el('p', '이 검사에서 오래됨으로 분류되지 않았습니다.')); return; }
  const forest = explanation.propagation, path = [], visited = new Set(); let current = id;
  while (forest[current] && !visited.has(current)) {
    visited.add(current); const step = forest[current];
    if (step.predecessor_id === null) {
      const row = el('div', undefined, 'path'), steps = el('div', undefined, 'steps');
      row.append(el('p', '변경 출발점: ' + step.root_id + ' · ' + (changeKinds[step.root_kind] || step.root_kind)));
      if (step.root_kind === 'historic-only-unknown') row.append(el('p', '과거 기록만 남아 원래 변경 원인은 알 수 없습니다.'));
      steps.append(changeNode(current));
      for (const edge of path.reverse()) steps.append(el('span', '— ' + edge.type + ' [' + (edgePresence[edge.presence] || edge.presence) + '] →', 'edge'), changeNode(edge.to));
      row.append(steps); box.append(row); return;
    }
    const edge = step.edge;
    if (!edge || edge.from !== step.predecessor_id || edge.to !== current) break;
    path.push(edge); current = step.predecessor_id;
  }
  box.append(el('p', '기록된 전파 경로가 없거나 불완전하여 원인을 알 수 없습니다.'));
}
function appendJSON(parent, title, value) { const details = el('details'); details.append(el('summary', title), el('pre', JSON.stringify(value, null, 2))); parent.append(details); }
function renderList() {
  const query = document.getElementById('search').value.toLocaleLowerCase(), list = document.getElementById('node-list'); list.replaceChildren();
  const matching = data.graph.nodes.filter(node => (node.id + ' ' + node.title + ' ' + node.type).toLocaleLowerCase().includes(query));
  document.getElementById('list-count').textContent = matching.length + '개 노드';
  for (const node of matching) { const item = el('li'), button = nodeButton(node.id); if (node.id === selected) button.setAttribute('aria-current', 'true'); item.append(button); list.append(item); }
  if (!matching.length) list.append(el('li', '검색 결과가 없습니다.'));
}
function showNode(id, focus = false) {
  selected = id; const node = nodes.get(id), evidence = data.check.nodes[id], box = document.getElementById('node-detail'); box.replaceChildren();
  const title = el('h2', node.id + ' · ' + node.title); title.id = 'detail-title'; title.tabIndex = -1; box.append(title);
  box.append(el('p', types[node.type] + ' · ' + node.type), badge(node.status), badge(evidence.freshness));
  if (node.detail) box.append(el('p', node.detail, 'detail-text'));
  box.append(el('h3', '출처와 최신성 근거'));
  box.append(el('p', node.source ? '그래프 출처: ' + node.source : '그래프 출처가 없습니다.', 'detail-text'));
  box.append(el('p', '변경 사유: ' + (evidence.reasons.length ? evidence.reasons.join(', ') : '보고된 변경 사유 없음'), 'detail-text'));
  if (!evidence.evidence.length) box.append(el('p', '연결된 증거가 없습니다.'));
  for (const ref of evidence.evidence) { const row = el('div', undefined, 'path'); row.append(el('p', ref.path, 'detail-text'), el('p', '가용성: ' + ref.availability), el('code', 'SHA-256: ' + (ref.sha256 || '없음'))); box.append(row); }
  renderChangePath(box, id, evidence);
  box.append(el('h3', '직접 연결 · 방향과 관계명'));
  const relations = [...incoming.get(id), ...outgoing.get(id).filter(edge => edge.to !== id)];
  if (!relations.length) box.append(el('p', '직접 연결이 없는 노드입니다.'));
  for (const edge of relations) { const row = el('div', undefined, 'relation'); row.append(nodeButton(edge.from), el('span', '— ' + edge.type + ' →', 'edge'), nodeButton(edge.to)); box.append(row); }
  renderList(); if (focus) title.focus();
}
function renderPaths() {
  const root = document.getElementById('requirement').value, box = document.getElementById('paths'); box.replaceChildren();
  if (!root) { box.append(el('p', '요구사항 노드가 없습니다. 전체 노드 탐색에서 연결을 확인하세요.')); return; }
  const previous = new Map([[root, null]]), queue = [root];
  for (let i = 0; i < queue.length; i++) for (const edge of outgoing.get(queue[i])) if (!previous.has(edge.to)) { previous.set(edge.to, edge); queue.push(edge.to); }
  box.append(el('p', '선택 요구사항에서 화살표 방향으로 도달하는 실제 경로입니다. 대상마다 최단 경로 하나를 표시하며, 모든 연결은 노드 상세에서 탐색할 수 있습니다.', 'muted'));
  for (const type of ['screen', 'code', 'test']) {
    box.append(el('h3', types[type] + ' 경로'));
    const targets = queue.filter(id => nodes.get(id).type === type);
    if (!targets.length) box.append(el('p', '도달 가능한 ' + types[type] + ' 노드가 없습니다.'));
    for (const target of targets) {
      const path = []; let current = target;
      while (current !== root) { const edge = previous.get(current); path.push(edge); current = edge.from; }
      path.reverse(); const row = el('div', undefined, 'path'), steps = el('div', undefined, 'steps'); steps.append(nodeButton(root));
      for (const edge of path) steps.append(el('span', '— ' + edge.type + ' →', 'edge'), nodeButton(edge.to));
      row.append(steps, badge(nodes.get(target).status), badge(data.check.nodes[target].freshness)); box.append(row);
    }
  }
}
const select = document.getElementById('requirement');
for (const node of data.graph.nodes.filter(node => node.type === 'requirement')) { const option = el('option', node.id + ' · ' + node.title); option.value = node.id; select.append(option); }
select.disabled = !select.options.length;
select.addEventListener('change', () => { renderPaths(); showNode(select.value); });
document.getElementById('search').addEventListener('input', renderList);
document.getElementById('summary').textContent = data.graph.nodes.length + '개 노드 · ' + data.graph.edges.length + '개 관계 · 요구사항 ' + select.options.length + '개';
document.getElementById('hash').textContent = data.graph_sha256;
appendJSON(document.getElementById('check-summary'), '입력·권위·검토 근거 보기', data.check_context);
if (data.warnings.length) { const list = el('ul'); for (const warning of data.warnings) list.append(el('li', warning)); document.getElementById('warnings').append(list); }
else document.getElementById('warnings').append(el('p', '구조 검증 경고 없음.'));
let initialNode = null;
if (location.hash.startsWith('#node=')) {
  try { const id = decodeURIComponent(location.hash.slice(6)); if (nodes.has(id)) initialNode = id; }
  catch (_) { /* Malformed fragments fall back to the ordinary starting node. */ }
}
if (initialNode && nodes.get(initialNode).type === 'requirement') select.value = initialNode;
renderChangeSummary();
renderPaths();
if (data.graph.nodes.length) showNode(initialNode || select.value || data.graph.nodes[0].id); else { document.getElementById('node-detail').append(el('p', '그래프에 노드가 없습니다.')); renderList(); }
"""


def prepare(graph_path, check_path):
    """Bind supplied freshness to exact graph bytes and canonical node fingerprints."""
    graph_hash, content = ssot.read_local(graph_path, capture=True)
    data = json.loads(content.decode("utf-8"))
    check = ssot.read_json(check_path)
    if not isinstance(check, dict) or type(check.get("version")) is not int or check["version"] != 1:
        raise ValueError("Invalid SSOT check version.")
    errors, warnings = graph.validate_graph(data, include_figma_warnings=check.get("scope") != "local-only")
    if errors:
        raise ValueError("Invalid graph: " + "; ".join(errors))
    inputs = check.get("inputs")
    graph_ref = inputs.get("graph") if isinstance(inputs, dict) else None
    if not isinstance(graph_ref, dict) or graph_ref.get("sha256") != graph_hash or graph_ref.get("availability") != "local-hashed":
        raise ValueError("SSOT check graph SHA-256 mismatch; regenerate check for this exact graph.")
    checked = check.get("nodes")
    if not isinstance(checked, dict) or set(checked) != {node["id"] for node in data["nodes"]}:
        raise ValueError("SSOT check node IDs mismatch.")
    fingerprints = ssot.graph_fingerprints(data)
    for node in data["nodes"]:
        item = checked[node["id"]]
        if not isinstance(item, dict) or item.get("type") != node["type"] or item.get("content_sha256") != fingerprints[node["id"]]:
            raise ValueError("SSOT check node fingerprint mismatch: " + node["id"])
        if item.get("freshness") not in ("stale", "unverified", "content-current"):
            raise ValueError("Invalid SSOT freshness: " + node["id"])
        if not isinstance(item.get("reasons"), list) or any(not isinstance(reason, str) for reason in item["reasons"]):
            raise ValueError("Invalid SSOT reasons: " + node["id"])
        refs = item.get("evidence")
        if not isinstance(refs, list) or any(not isinstance(ref, dict) or not isinstance(ref.get("path"), str)
                or ref.get("availability") not in ("local-hashed", "missing", "remote-unchecked")
                or (ref.get("sha256") is not None and not isinstance(ref["sha256"], str)) for ref in refs):
            raise ValueError("Invalid SSOT evidence: " + node["id"])
    explanation = check.get("change_explanation")
    if explanation is not None:
        validate_explanation(explanation)
    return {"graph": data, "graph_sha256": graph_hash, "check": {"nodes": checked}, "warnings": warnings,
            "change_explanation": check.get("change_explanation"),
            "check_context": {key: value for key, value in check.items() if key not in ("nodes", "change_explanation")}}


def validate_explanation(value):
    """Reject malformed optional explanations; never infer them from graph navigation."""
    def require(condition):
        if not condition:
            raise ValueError("Invalid SSOT change explanation.")

    def changes(items, key):
        require(isinstance(items, list))
        for item in items:
            require(isinstance(item, dict) and isinstance(item.get(key), str))
            for side in ("previous", "current"):
                ref = item.get(side)
                require(ref is None or (isinstance(ref, dict) and isinstance(ref.get("path"), str)
                        and isinstance(ref.get("availability"), str)
                        and (ref.get("sha256") is None or isinstance(ref["sha256"], str))))

    require(isinstance(value, dict) and type(value.get("version")) is int and value["version"] == 1)
    require(isinstance(value.get("direct_nodes"), dict) and isinstance(value.get("propagation"), dict))
    for origin in value["direct_nodes"].values():
        require(isinstance(origin, dict) and isinstance(origin.get("categories"), list)
                and all(isinstance(kind, str) for kind in origin["categories"]))
        changes(origin.get("evidence_changes"), "path")
    changes(value.get("changed_inputs"), "key")
    changes(value.get("changed_authorities"), "key")
    for step in value["propagation"].values():
        require(isinstance(step, dict) and isinstance(step.get("root_id"), str)
                and isinstance(step.get("root_kind"), str)
                and (step.get("predecessor_id") is None or isinstance(step["predecessor_id"], str)))
        edge = step.get("edge")
        require(edge is None or (isinstance(edge, dict) and all(
            isinstance(edge.get(key), str) for key in ("from", "to", "type", "presence"))))


def render(payload, *, has_graph_diff=False):
    comparison = '<p><a href="graph-diff.html" style="color:var(--accent)">이전·현재 그래프 비교</a></p>' if has_graph_diff else ""
    # Script raw-text parsing treats even JSON strings containing </script> as markup.
    encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-""" + script_hash + """'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>요구사항 추적 뷰어</title><style>""" + STYLE + """</style></head><body>
<header><div class="eyebrow">FIGMA FLOW · OFFLINE TRACE</div><h1>요구사항에서 검증까지</h1><p id="summary" class="muted"></p>""" + comparison + """<p>그래프 상태는 작성자의 선언입니다. 최신성은 제공된 SSOT 검사 시점의 내용 일치만 뜻하며, 테스트 성공·진실성·현재 Figma 상태를 증명하지 않습니다.</p></header>
<main><aside><div class="panel"><h2>추적 시작점</h2><label for="requirement">요구사항 선택</label><select id="requirement"></select><label for="search">전체 노드 검색</label><input id="search" type="search" placeholder="ID, 제목, 노드 유형"><p id="list-count" role="status" class="muted"></p><ul id="node-list" class="nodes" aria-label="전체 노드"></ul></div><details class="panel" id="warnings"><summary>그래프 구조 경고</summary></details></aside>
<div><section class="panel" aria-labelledby="paths-title"><h2 id="paths-title">연결 경로</h2><div id="paths"></div></section><section class="panel" id="change-summary" aria-labelledby="change-title"><h2 id="change-title">무엇이 바뀌었고 왜 다시 확인해야 하나요?</h2></section><section class="panel" id="node-detail" aria-label="선택 노드 상세"></section><section class="panel" id="check-summary"><h2>검사 입력 근거</h2><p>입력 그래프의 바이트 SHA-256과 모든 노드 지문을 대조했습니다. 이 페이지는 생성 후 파일 변경을 감지하지 않습니다. 최신 상태는 SSOT 검사를 다시 실행해 새 보고서를 만드세요.</p><p>그래프 SHA-256: <code id="hash"></code></p></section></div></main>
<footer>독립 실행 · 읽기 전용 · 네트워크 요청 없음. 출처와 URL은 텍스트로만 표시하며 자동으로 열거나 가져오지 않습니다.</footer>
<noscript>추적 탐색에는 JavaScript가 필요합니다. 네트워크 연결은 필요하지 않습니다.</noscript>
<script id="trace-data" type="application/json">""" + encoded + """</script><script>""" + SCRIPT + """</script></body></html>\n"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph")
    parser.add_argument("--check", required=True, help="JSON output from ssot.py check")
    parser.add_argument("--out", required=True, help="New HTML file; existing files are never replaced")
    args = parser.parse_args(argv)
    try:
        payload = prepare(Path(args.graph), Path(args.check))
        graph._write_exclusive(Path(args.out), render(payload))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"report": str(args.out), "graph_sha256": payload["graph_sha256"],
                      "nodes": len(payload["graph"]["nodes"]), "edges": len(payload["graph"]["edges"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
