#!/usr/bin/env python3
"""Build an offline catalog from explicitly selected project manifests."""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import check_project


def preflight(manifest_path, out):
    """Reject output enclosing any known input, even inputs that do not exist yet."""
    manifest_path = Path(manifest_path).absolute()
    if manifest_path.resolve() == out.resolve() or out.resolve() in manifest_path.resolve().parents:
        raise ValueError('Output directory contains a selected manifest')
    try:
        manifest = check_project.ssot.read_json(manifest_path)
    except (OSError, UnicodeError, ValueError):
        return
    if not isinstance(manifest, dict):
        return
    # Check even malformed manifests before interpreting the input schema.
    check_project.reject_output_references(out, manifest_path, manifest, {}, {}, manifest_path, manifest_path)
    inputs = manifest.get('inputs')
    inputs = inputs if isinstance(inputs, dict) else {}
    def input_path(key):
        ref = inputs.get(key)
        value = ref.get('path') if isinstance(ref, dict) else None
        return manifest_path.parent / value if isinstance(value, str) else manifest_path.parent
    graph_path, bindings_path = input_path('graph'), input_path('bindings')
    def read(path):
        try:
            value = check_project.ssot.read_json(path)
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, UnicodeError):
            return {}
    check_project.reject_output_references(out, manifest_path, manifest, read(graph_path), read(bindings_path), graph_path, bindings_path)


def build(projects, out, ideas=()):
    out = Path(out).absolute()
    labels = [label for label, _ in projects] + [label for label, _ in ideas]
    if any(not label.strip() for label in labels) or len(labels) != len(set(labels)):
        raise ValueError('Project labels must be nonempty and unique')
    for _, manifest in projects:
        preflight(manifest, out)
    drafts = []
    for label, value in ideas:
        path = Path(value).absolute()
        if path.resolve() == out.resolve() or out.resolve() in path.resolve().parents:
            raise ValueError('Output directory contains a selected graph')
        try:
            digest, raw = check_project.ssot.read_local(path, capture=True)
            data = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeError, ValueError) as exc:
            drafts.append((label, None, None, str(exc)))
            continue
        if isinstance(data, dict):
            check_project.reject_output_references(out, path, {}, data, {}, path, path)
        drafts.append((label, data, digest, None))
    out.mkdir(exist_ok=False)
    (out / 'projects').mkdir()
    entries = []
    exits = []
    for index, (label, manifest_path) in enumerate(projects, 1):
        child = out / 'projects' / f'{index:03d}'
        item = {'label': label, 'status': 'invalid', 'stale_count': None, 'nodes': [], 'edges': [], 'trace': None}
        try:
            result = check_project.check_project(Path(manifest_path), child, intent='inspect')
            summary = check_project.ssot.read_json(child / 'summary.json')
            item['status'] = summary['status']
            item['error'] = summary.get('trace_error') or ('; '.join(summary['strict_local']['errors']) if summary['strict_local']['errors'] else None)
            if (child / 'trace.html').is_file():
                manifest = check_project.ssot.read_json(Path(manifest_path))
                graph_path = Path(manifest_path).absolute().parent / manifest['inputs']['graph']['path']
                payload = check_project.trace_report.prepare(graph_path, child / 'check.json')
                if payload['graph_sha256'] != summary['graph_sha256']:
                    raise ValueError('Graph changed after project check')
                item['nodes'] = [{**node, 'freshness': payload['check']['nodes'][node['id']]['freshness']}
                                 for node in payload['graph']['nodes']]
                item['edges'] = payload['graph']['edges']
                item['stale_count'] = sum(node['freshness'] == 'stale' for node in item['nodes'])
                item['trace'] = f'projects/{index:03d}/trace.html'
            exits.append(result)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
            item.update(status='invalid', error=str(exc), stale_count=None, nodes=[], edges=[], trace=None)
            exits.append(1)
        entries.append(item)
    for label, data, digest, read_error in drafts:
        item = {'label': label, 'status': 'draft', 'stale_count': None, 'nodes': [], 'edges': [], 'trace': None}
        try:
            if read_error is not None:
                raise ValueError(read_error)
            # Reject non-JSON numbers here so one malformed draft cannot break other entries.
            json.dumps(data, allow_nan=False)
            errors, warnings = check_project.graph.validate_graph(data, include_figma_warnings=False)
            if errors:
                raise ValueError('; '.join(errors))
            item['nodes'] = [{**node, 'freshness': 'unverified'} for node in data['nodes']]
            item['edges'] = data['edges']
            item['warnings'] = warnings
            item['graph_sha256'] = digest
            exits.append(0)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
            item.update(status='invalid', error=str(exc))
            exits.append(1)
        entries.append(item)
    catalog = {'version': 1, 'projects': entries}
    (out / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    (out / 'index.html').write_text(render(catalog), encoding='utf-8')
    return 1 if 1 in exits else 2 if 2 in exits else 0


SCRIPT = r"""
'use strict';
const catalog = JSON.parse(document.getElementById('catalog-data').textContent);
const buildElement = document.getElementById('build-data');
const build = buildElement ? JSON.parse(buildElement.textContent) : null;
const project = document.getElementById('project'), kind = document.getElementById('kind'), search = document.getElementById('search'), results = document.getElementById('results');
const names = {requirement:'기능 · 요구사항',screen:'화면',code:'코드',test:'테스트',acceptance:'인수 기준',state:'상태',action:'동작',figma:'Figma'};
const status = {draft:'기획 초안 · 구현/증거 미검증',current:'내용 일치',invalid:'검사 오류','stale-or-unavailable':'변경 또는 확인 불가',stale:'오래됨','content-current':'내용 일치',unverified:'미검증'};
function el(tag, text, cls) { const x = document.createElement(tag); if (text !== undefined) x.textContent = text; if (cls) x.className = cls; return x; }
function label(node) { return (names[node.type] || node.type) + ' ' + node.id + ' · ' + node.title; }
for (const p of catalog.projects) {
  p.byId = new Map(p.nodes.map(n => [n.id, n]));
  p.adjacent = new Map(p.nodes.map(n => [n.id, []]));
  for (const edge of p.edges) {
    if (p.adjacent.has(edge.from)) p.adjacent.get(edge.from).push(edge);
    if (edge.to !== edge.from && p.adjacent.has(edge.to)) p.adjacent.get(edge.to).push(edge);
  }
}
let selected = null;
for (let i = 0; i < catalog.projects.length; i++) { const option = el('option', catalog.projects[i].label); option.value = String(i); project.append(option); if (build && catalog.projects[i].label === build.idea && catalog.projects[i].status === 'draft') project.value = String(i); }
function draw() {
  results.replaceChildren(); let count = 0;
  const query = search.value.trim().toLocaleLowerCase();
  catalog.projects.forEach((p, index) => {
    if (project.value !== 'all' && project.value !== String(index)) return;
    const byId = p.byId;
    const candidates = p.nodes.filter(n => ['requirement','screen'].includes(n.type) && (kind.value === 'all' || n.type === kind.value));
    function textMatches(n) { return (p.label + ' ' + n.id + ' ' + n.title).toLocaleLowerCase().includes(query); }
    function linkedMatches(n) {
      if (!query) return [];
      return p.adjacent.get(n.id).filter(e => e.type === 'appears on').map(e => {
        const from = byId.get(e.from), to = byId.get(e.to);
        if (!from || !to || from.type !== 'requirement' || to.type !== 'screen') return null;
        return byId.get(e.from === n.id ? e.to : e.from);
      }).filter(other => other && textMatches(other));
    }
    const matches = candidates.filter(n => (!selected || (selected.project === index && selected.id === n.id)) && (textMatches(n) || linkedMatches(n).length));
    const projectMatches = p.label.toLocaleLowerCase().includes(query);
    if (!matches.length && !(kind.value === 'all' && projectMatches)) return;
    const section = el('section', undefined, 'project-card');
    section.append(el('h2', p.label), el('p', (status[p.status] || p.status) + (p.stale_count === null ? ' · 최신성 미검사' : ' · 오래된 노드 ' + p.stale_count + '개'), 'meta'));
    if (build && p.status === 'draft' && p.label === build.idea) {
      const button = el('button', '앱 만들기'); button.type = 'button'; button.hidden = !!build.reviewed;
      const message = el('p', '선택한 초안으로 화면 명세, 앱, 테스트를 생성합니다.', 'meta');
      message.setAttribute('role', 'status');
      const preview = el('a', '완성된 앱 열기'); preview.hidden = true; preview.target = '_blank'; preview.rel = 'noopener noreferrer';
      async function refresh() {
        try {
          const response = await fetch('/api/status', {headers:{'X-Build-Token':build.token}, cache:'no-store'});
          if (!response.ok) throw new Error('상태를 확인할 수 없습니다');
          const job = await response.json();
          button.disabled = job.state !== 'ready';
          message.textContent = job.message;
          if (job.state === 'succeeded' && /^http:\/\/127\.0\.0\.1:\d+\/$/.test(job.preview_url || '')) { preview.href = job.preview_url; preview.hidden = false; }
          if (job.state === 'running') setTimeout(refresh, 1000);
        } catch (error) { button.disabled = true; message.textContent = String(error); }
      }
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const response = await fetch('/api/build', {method:'POST', headers:{'X-Build-Token':build.token}});
          if (!response.ok) throw new Error('생성을 시작할 수 없습니다');
          await refresh();
        } catch (error) { message.textContent = String(error); }
      });
      section.append(button, message, preview); refresh();
    }
    if (p.error) section.append(el('p', '검사 오류: ' + p.error));
    if (p.trace) { const a = el('a', '이 프로젝트의 상세 추적 보기'); a.href = p.trace; section.append(a); }
    if (!matches.length) section.append(el('p', p.nodes.length ? '조건에 맞는 항목이 없습니다.' : '탐색할 그래프가 없습니다.'));
    for (const n of matches) {
      count++; const card = el('article', undefined, 'node-card');
      card.append(el('h3', label(n)), el('p', '상태: ' + (status[n.freshness] || n.freshness), 'meta'));
      if (p.trace) { const a = el('a', '이 항목의 상세 추적 보기'); a.href = p.trace + '#node=' + encodeURIComponent(n.id); card.append(a); }
      if (query && !textMatches(n)) card.append(el('p', '연결된 검색 결과: ' + linkedMatches(n).map(label).join(', '), 'meta'));
      const edges = p.adjacent.get(n.id);
      const list = el('ul');
      for (const edge of edges) {
        const from = byId.get(edge.from), to = byId.get(edge.to);
        if (from && to) {
          const row = el('li', label(from) + ' — ' + edge.type + ' → ' + label(to));
          if (edge.type === 'appears on' && from.type === 'requirement' && to.type === 'screen') {
            const other = n.id === from.id ? to : from;
            const button = el('button', label(other) + ' 보기');
            button.type = 'button';
            button.addEventListener('click', () => {
              project.value = String(index); kind.value = other.type; search.value = '';
              selected = {project: index, id: other.id}; draw();
              const heading = results.querySelector('h3'); if (heading) { heading.tabIndex = -1; heading.focus(); }
            });
            row.append(' ', button);
          }
          list.append(row);
        }
      }
      card.append(el('h4', '직접 연결'), edges.length ? list : el('p', '직접 연결 없음'));
      section.append(card);
    }
    results.append(section);
  });
  document.getElementById('count').textContent = count + '개 항목';
  if (!results.children.length) results.append(el('p', '검색 결과가 없습니다.'));
}
for (const control of [project, kind, search]) control.addEventListener(control === search ? 'input' : 'change', () => { selected = null; draw(); });
draw();
"""
STYLE = """*{box-sizing:border-box}body{margin:0;background:#f4f5f1;color:#17282b;font:16px/1.6 system-ui,sans-serif}header,main,footer{max-width:1200px;margin:auto;padding:24px}h1{font-size:clamp(28px,5vw,44px);margin:0}h2,h3,h4{line-height:1.3;overflow-wrap:anywhere}h3{font-size:18px}h4{margin-bottom:8px}.filters{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px}label{display:block;font-weight:600}button{font:inherit;cursor:pointer;padding:5px 8px;color:#07576d;background:white;border:1px solid #829798;border-radius:6px}input,select{display:block;width:100%;font:inherit;padding:10px;border:1px solid #829798;border-radius:6px;background:white;color:#17282b}.project-card{background:white;border:1px solid #c4d1cd;border-radius:12px;padding:20px;margin:18px 0}.node-card{border-top:1px solid #d6dfdb;padding:8px 0;overflow-wrap:anywhere}.meta{color:#36585a}a{color:#07576d}li{margin:6px 0}:focus-visible{outline:3px solid #006a6f;outline-offset:3px}@media(max-width:700px){header,main,footer{padding:16px}.filters{grid-template-columns:1fr}}"""


def render(catalog, build=None):
    encoded = json.dumps(catalog, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    build_json = json.dumps(build, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-''' + digest + ''''; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'"><title>아이디어 프로젝트 탐색</title><style>''' + STYLE + '''</style></head><body><header><h1>아이디어 프로젝트 탐색</h1><p>선택한 프로젝트의 기능과 화면을 비교하고 실제 선언된 연결을 살펴봅니다.</p><p>내용 일치는 검사 시점의 파일 일치이며 테스트 성공이나 현재 외부 상태를 뜻하지 않습니다.</p></header><main><div class="filters"><label>검색<input id="search" type="search" placeholder="프로젝트, 기능, 화면 또는 ID"></label><label>프로젝트<select id="project"><option value="all">전체 프로젝트</option></select></label><label>항목<select id="kind"><option value="all">전체 항목</option><option value="requirement">기능 · 요구사항</option><option value="screen">화면</option></select></label></div><p id="count" role="status"></p><div id="results"></div></main><footer>''' + ('로컬 생성 모드' if build else '읽기 전용 · 생성 모드 실행: python3 tools/serve_ideas.py --catalog 카탈로그 --idea 초안이름 --graph 그래프.json --brief 기획서.md --out 새폴더') + '''</footer><noscript>탐색에는 JavaScript가 필요합니다.</noscript><script id="catalog-data" type="application/json">''' + encoded + '''</script><script id="build-data" type="application/json">''' + build_json + '''</script><script>''' + SCRIPT + '''</script></body></html>\n'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', nargs=2, action='append', default=[], metavar=('LABEL', 'MANIFEST'))
    parser.add_argument('--idea', nargs=2, action='append', default=[], metavar=('LABEL', 'GRAPH_JSON'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.project and not args.idea:
            raise ValueError('At least one --project or --idea is required')
        result = build(args.project, args.out, args.idea)
        print(f'Report: {args.out / "index.html"}')
        return result
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
