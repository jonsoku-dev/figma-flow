#!/usr/bin/env python3
"""Query curated campaign evidence and build an offline Korean catalog."""
import argparse
from datetime import date
from html import escape
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'library/campaigns.json'


def load_library(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    def strings(value):
        return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)
    require(isinstance(data, dict) and type(data.get('version')) is int and data['version'] == 1, 'Expected version 1 library')
    require(isinstance(data.get('captured_on'), str), 'captured_on must be an ISO date')
    require(re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['captured_on']), 'captured_on must be YYYY-MM-DD')
    date.fromisoformat(data['captured_on'])
    for key in ('categories', 'sources', 'patterns'):
        require(isinstance(data.get(key), list), f'{key} must be an array')
        ids = []
        for row in data[key]:
            require(isinstance(row, dict), f'{key} entries must be objects')
            ident = row.get('id')
            require(isinstance(ident, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', ident), f'Invalid {key} ID')
            ids.append(ident)
        require(len(ids) == len(set(ids)), f'Duplicate {key} IDs')
    categories = {r['id'] for r in data['categories']}
    sources = {r['id']: r for r in data['sources']}
    for key, fields in (('categories', ('name',)), ('sources', ('title', 'url', 'type', 'evidence', 'observed')), ('patterns', ('title', 'category', 'observation', 'application', 'limits'))):
        for row in data[key]:
            for field in fields:
                require(isinstance(row.get(field), str) and bool(row[field].strip()), f'{key}.{field} must be nonempty text')
    for source in sources.values():
        url = urlsplit(source['url'])
        url.port
        require(url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password and not any(c.isspace() or ord(c) < 32 for c in source['url']), 'Source URL must be credential-free HTTPS')
        require(source.get('market') in ('KR', 'JP'), 'Source market must be KR or JP')
        require(strings(source.get('categories')) and set(source['categories']) <= categories, 'Unknown or missing source categories')
        if 'visual' in source:
            require(isinstance(source['visual'], list), 'visual must be an array')
            for visual in source['visual']:
                require(isinstance(visual, dict) and isinstance(visual.get('surface'), str) and bool(visual['surface'].strip()) and strings(visual.get('observations')), 'visual entries require surface text and observations array')
    for pattern in data['patterns']:
        require(pattern['category'] in categories, 'Unknown pattern category')
        require(strings(pattern.get('source_ids')) and set(pattern['source_ids']) <= sources.keys(), 'Unknown or missing pattern sources')
        require(strings(pattern.get('checks')), 'Pattern checks must be nonempty text array')
    return data


def select(data, category=None, market=None):
    if category is not None and category not in {c['id'] for c in data['categories']}:
        raise ValueError(f'Unknown category: {category}')
    sources = [s for s in data['sources'] if (not market or s['market'] == market) and (not category or category in s['categories'])]
    ids = {s['id'] for s in sources}
    by_id = {s['id']: s for s in sources}
    patterns = [{**p, 'source_ids': [s for s in p['source_ids'] if s in ids],
                 'cross_category_analogy_source_ids': [s for s in p['source_ids'] if s in ids and p['category'] not in by_id[s]['categories']]}
                for p in data['patterns'] if (not category or p['category'] == category) and ids.intersection(p['source_ids'])]
    return {**data, 'sources': sources, 'patterns': patterns}


def plan(data, category, market=None):
    chosen = select(data, category, market)
    sources = {s['id']: s for s in chosen['sources']}
    all_sources = {s['id']: s for s in data['sources']}
    originals = {p['id']: p for p in data['patterns']}
    return {'version': 1, 'captured_on': data['captured_on'], 'category': category, 'market': market,
            'status': 'untested', 'verification': 'manual',
            'synthesis_scope': '관측 문장은 원본 패턴의 전체 출처를 종합합니다. 시장·카테고리 필터는 evidence에 적용되며, 원본 종합의 전체 출처는 supporting_sources에 보존됩니다.',
            'limits': '출처 관측은 제품 검증 결과가 아닙니다. 각 검사를 실제 대상에서 수행하고 별도 증거를 기록하세요.',
            'patterns': [{'pattern_id': p['id'], 'title': p['title'], 'observation': p['observation'],
                          'synthesis_scope': {'filtered': False, 'category': p['category'],
                                              'source_ids': originals[p['id']]['source_ids'],
                                              'markets': sorted({all_sources[s]['market'] for s in originals[p['id']]['source_ids']})},
                          'supporting_sources': [{'source_id': sid, 'url': all_sources[sid]['url'], 'market': all_sources[sid]['market'],
                                                 'source_categories': all_sources[sid]['categories'],
                                                 'relationship': 'same_category_observation' if p['category'] in all_sources[sid]['categories'] else 'cross_category_analogy',
                                                 'evidence': all_sources[sid]['evidence'], 'observed': all_sources[sid]['observed']}
                                                for sid in originals[p['id']]['source_ids']],
                          'application': p['application'], 'limits': p['limits'],
                          'evidence': [{'source_id': sid, 'url': sources[sid]['url'], 'evidence': sources[sid]['evidence'], 'observed': sources[sid]['observed'], 'relationship': 'same_category_observation', 'source_categories': sources[sid]['categories']} for sid in p['source_ids']],
                          'checks': [{'check': check, 'status': 'untested', 'verification': 'manual'} for check in p['checks']]} for p in chosen['patterns']]}


def report(data):
    e = escape
    options = ''.join(f'<option value="{e(c["id"])}">{e(c["name"])}</option>' for c in data['categories'])
    cards = []
    for source in data['sources']:
        visual = ''.join(f'<details><summary>시각 관측 기록</summary><p>{e(v["surface"])}</p><ul>{"".join(f"<li>{e(o)}</li>" for o in v["observations"])}</ul></details>' for v in source.get('visual', []))
        cards.append(f'<article class="card" id="source-{e(source["id"])}" data-source="{e(source["id"])}"><span class="tag">{source["market"]} · {e(source["type"])}</span><h3>{e(source["title"])}</h3><p>{e(source["evidence"])}</p><p class="muted">관측: {e(source["observed"])}</p>{visual}<a href="{e(source["url"], quote=True)}" target="_blank" rel="noopener noreferrer">원문 열기 ↗</a><p class="muted">{e(source["url"])}</p></article>')
    patterns = []
    for p in data['patterns']:
        sources = {s['id']: s for s in data['sources']}
        links = ' · '.join(f'<a href="#source-{e(s)}">{e(s)}{" (타 카테고리 유추)" if p["category"] not in sources[s]["categories"] else " (동일 카테고리 관측)"}</a>' for s in p['source_ids'])
        patterns.append(f'<article class="card" data-pattern="{e(p["id"])}"><span class="tag">{e(p["category"])} · 수동 검증 전</span><h3>{e(p["title"])}</h3><p>{e(p["observation"])}</p><p><strong>적용</strong> {e(p["application"])}</p><ul>{"".join(f"<li>{e(c)}</li>" for c in p["checks"])}</ul><p class="muted">한계: {e(p["limits"])}</p><p>출처: {links}</p></article>')
    payload = {'library': data, 'plans': {f'{c["id"]}:{market or ""}': plan(data, c['id'], market) for c in data['categories'] for market in (None, 'KR', 'JP')}}
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'"><title>캠페인 근거 라이브러리 · Figma Flow</title><style>
:root{color-scheme:light;--ink:#172c30;--muted:#526c6d;--line:#c5d5d0;--accent:#176954}*{box-sizing:border-box}body{margin:0;background:#f4f5ef;color:var(--ink);font:16px/1.65 system-ui,sans-serif}header,main{max-width:1280px;margin:auto;padding:40px 28px}header{padding-top:64px}h1{font-size:clamp(2rem,5vw,3.6rem);letter-spacing:-.05em;line-height:1.15;max-width:900px}h2{font-size:1.6rem;margin-top:40px}h3{font-size:1.15rem}p{overflow-wrap:anywhere}.eyebrow{font-size:.8rem;letter-spacing:.18em;font-weight:750;color:var(--accent)}.intro{max-width:760px}.muted{color:var(--muted);font-size:.9rem}.filters{display:flex;flex-wrap:wrap;gap:18px;padding:24px;background:#e5ece3;border:1px solid var(--line);border-radius:16px}label{display:grid;gap:6px;font-weight:650;flex:1;min-width:180px}input,select,button{font:inherit;border:1px solid #829b91;border-radius:7px;padding:10px;background:#fff;color:var(--ink)}button{cursor:pointer;background:var(--accent);color:white}a{color:#125b49;text-underline-offset:3px}:focus-visible{outline:3px solid #d07827;outline-offset:4px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:18px}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:24px;min-width:0}.tag{font-size:.75rem;font-weight:700;color:var(--accent)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#172c30;color:#e5efe6;padding:24px;border-radius:12px;font:13px/1.7 ui-monospace,monospace;max-height:600px;overflow:auto}[hidden]{display:none!important}nav{display:flex;flex-wrap:wrap;gap:20px}@media(max-width:600px){header,main{padding:24px 18px}.filters,.card{padding:18px}}
</style></head><body><header><p class="eyebrow">FIGMA FLOW / RESEARCH LIBRARY</p><h1>모바일게임 캠페인 레퍼런스</h1><p class="intro">한국과 일본 캠페인의 공개 근거를 카테고리별로 찾아보세요. 출처의 관측과 적용 제안을 구분하고, 실제 제품에서 확인할 검사를 가져갈 수 있습니다.</p><p class="muted">자료 기준일: ''' + e(data['captured_on']) + ''' · 외부 자료를 새로 수집하지 않는 오프라인 카탈로그</p><nav aria-label="페이지 탐색"><a href="#sources">출처</a><a href="#patterns">도출 패턴</a><a href="#plans">검증 계획</a></nav></header><main><noscript><p>필터와 계획 선택은 JavaScript가 필요합니다. 아래 전체 출처와 패턴을 읽거나 CLI의 plan 명령을 사용하세요.</p></noscript><div class="filters"><label for="category">카테고리<select id="category"><option value="">전체 카테고리</option>''' + options + '''</select></label><label for="market">시장<select id="market"><option value="">KR + JP</option><option>KR</option><option>JP</option></select></label><label for="search">검색<input id="search" type="search" placeholder="제목, 근거, 적용 내용"></label></div><p id="count" role="status" aria-live="polite">전체 출처 ''' + str(len(data['sources'])) + '개 · 패턴 ' + str(len(data['patterns'])) + '''개</p><h2 id="sources">관측 출처</h2><div class="grid">''' + ''.join(cards) + '''</div><h2 id="patterns">도출 패턴</h2><p>다음 내용은 적용 제안입니다. 관측 근거만으로 성과나 동작을 검증하지 않습니다.</p><div class="grid">''' + ''.join(patterns) + '''</div><h2 id="plans">검증 계획</h2><p>카테고리와 시장을 선택하면 출처 URL과 구체적인 수동 검사 항목이 표시됩니다. 검색은 카드에만 적용됩니다. 관측 문장은 전체 출처의 종합이며, 계획의 supporting_sources에 전체 출처를 보존하고 evidence에는 선택한 범위의 근거만 담습니다. 모든 검사는 <strong>untested / manual</strong>로 시작합니다.</p><button id="download" type="button" disabled>계획 JSON 다운로드</button><pre id="plan" tabindex="0" aria-label="검증 계획 JSON">카테고리를 선택하세요.</pre></main><script id="catalog-data" type="application/json">''' + encoded + '''</script><script>
const payload=JSON.parse(document.getElementById('catalog-data').textContent),lib=payload.library;
const category=document.getElementById('category'),market=document.getElementById('market'),search=document.getElementById('search'),output=document.getElementById('plan'),download=document.getElementById('download');
let currentPlan=null;
function update(){
 const c=category.value,m=market.value,q=search.value.trim().toLocaleLowerCase();
 const sources=lib.sources.filter(s=>(!c||s.categories.includes(c))&&(!m||s.market===m));
 const ids=new Set(sources.map(s=>s.id));
 const patterns=lib.patterns.filter(p=>(!c||p.category===c)&&p.source_ids.some(id=>ids.has(id)));
 let sourceCount=0,patternCount=0;
 for(const s of lib.sources){const card=document.querySelector('[data-source="'+s.id+'"]');card.id='source-'+s.id;card.hidden=!ids.has(s.id)||(q&&!JSON.stringify(s).toLocaleLowerCase().includes(q));if(!card.hidden)sourceCount++;}
 for(const p of lib.patterns){const card=document.querySelector('[data-pattern="'+p.id+'"]');card.hidden=!patterns.includes(p)||(q&&!JSON.stringify(p).toLocaleLowerCase().includes(q));if(!card.hidden)patternCount++;for(const a of card.querySelectorAll('a')){const sid=a.getAttribute('href').slice(8);a.hidden=!ids.has(sid);}}
 document.getElementById('count').textContent='출처 '+sourceCount+'개 · 패턴 '+patternCount+'개'+(!sourceCount&&!patternCount?' · 일치하는 자료가 없습니다.':'');
 currentPlan=c?payload.plans[c+':'+m]:null;output.textContent=currentPlan?JSON.stringify(currentPlan,null,2):'카테고리를 선택하세요.';download.disabled=!currentPlan;
}
for(const control of [category,market,search])control.addEventListener('input',update);
document.querySelectorAll('[data-pattern] a').forEach(a=>a.addEventListener('click',()=>{search.value='';update();}));
download.addEventListener('click',()=>{if(!currentPlan)return;const url=URL.createObjectURL(new Blob([JSON.stringify(currentPlan,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='campaign-plan-'+category.value+'-'+(market.value||'all')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
update();
</script></body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('list', 'plan', 'report'):
        command = commands.add_parser(name)
        command.add_argument('--data', type=Path, default=argparse.SUPPRESS)
        if name == 'report':
            command.add_argument('--out', required=True, type=Path)
        else:
            command.add_argument('--category', required=name == 'plan')
            command.add_argument('--market', choices=('KR', 'JP'))
    args = parser.parse_args(argv)
    try:
        data = load_library(args.data)
        if args.command == 'report':
            if args.out.suffix.lower() != '.html':
                raise ValueError('Output must be a new .html file')
            rendered = report(data)
            with args.out.open('x', encoding='utf-8') as stream:
                stream.write(rendered)
            print(json.dumps({'output': str(args.out), 'sources': len(data['sources']), 'patterns': len(data['patterns'])}, ensure_ascii=False))
        else:
            result = plan(data, args.category, args.market) if args.command == 'plan' else select(data, args.category, args.market)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'campaign_library: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
