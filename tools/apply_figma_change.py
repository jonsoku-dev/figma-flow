#!/usr/bin/env python3
"""Trace selected native Figma token changes to a local app. Default is plan-only."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import sys

import sync_figma_tokens as sync
import token_code_scope as code


def encode(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def save(path, data):
    path.write_text(encode(data), encoding='utf-8')


def html_report(impact, scope, receipt):
    esc = lambda s: escape(str(s), quote=True)
    def listing(items):
        rows = ''.join('<li>' + esc(value) + '</li>' for value in dict.fromkeys(items))
        return '<ul>' + rows + '</ul>' if rows else '<p>해당 없음</p>'
    colors = listing(f"{item['token']}　{item['before']} → {item['after']}" for item in impact['changes'])
    routes = []
    for screen in impact['screens']:
        routes.append('<h3>' + esc(screen['screen_id']) + '</h3>')
        for path in screen['paths']:
            routes.append('<p class="path">' + ' → '.join(esc(x) for x in [path['root'], path['token'], path['component']+'/'+path['variant'], screen['screen_id']]) + '</p>')
    overrides = listing(
        f"{item['source']}:{item['line']}　{item['selector']}　{item['property']} = {item['value']}"
        for item in scope['possible_overrides']
    )
    unknowns = listing(f"{item['source']}　{item['reason']}" for item in scope['unknowns'])
    rows = []
    for use in scope['observed_consumers']:
        rows.append('<tr>' + ''.join('<td>'+esc(v)+'</td>' for v in (
            ', '.join(use['screen_ids']) or ', '.join(use['candidate_screen_ids'])+' (후보)',
            use['source']+':'+str(use['line']), use['css_source']+':'+str(use['css_line']),
            use['class']+' / '+use['property'],', '.join(use['code_ids'])
        )) + '</tr>')
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
            '<title>토큰 변경 영향</title><style>body{max-width:62rem;margin:2rem auto;padding:1rem;font:1rem/1.65 system-ui;color:#182429}'
            'table{width:100%;border-collapse:collapse}th,td{padding:.6rem;text-align:left;border-bottom:1px solid #ccc;overflow-wrap:anywhere}'
            '.scroll{overflow:auto}.path{padding:.65rem;background:#eef3f2}a{color:#17556e}h3{font-size:1rem}</style>'
            '<h1>토큰 변경 영향</h1><p>페이지 '+esc(impact['page_id'])+' · <a href="result.json">실행 결과</a></p><h2>Figma 변수</h2>'+colors+
            '<h2>디자인 그래프 경로</h2>'+(''.join(routes) or '<p>해당 화면 없음</p>')+
            '<h2>실제 코드에 있는 사용처</h2><div class="scroll"><table><thead><tr><th>화면</th><th>사용 위치</th><th>스타일 위치</th><th>클래스 / 속성</th><th>코드 ID</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'+
            '<h2>변경 대상 파일</h2>'+listing(receipt['planned_files'])+
            '<h2>스타일을 덮어쓸 수 있는 규칙</h2>'+overrides+
            '<details><summary>브라우저 확인이 필요한 범위</summary>'+unknowns+listing(scope['gaps'])+'</details>'+
            '<p><a href="token-plan/impact.json">설계 근거</a> · <a href="code-scope.json">코드 사용처</a> · <a href="result.json">실행 기록</a></p></html>')


def run(project, resolved, before, after, page_id, output, apply=False, prior_sync=None):
    root = Path(project).resolve(strict=True)
    output = Path(output).absolute()
    if output.resolve() == root or root in output.resolve().parents:
        raise ValueError('Choose a fresh report directory outside the project.')
    design = code.within(root, 'design.json')
    graph = code.within(root, 'graph.json')
    bindings = code.within(root, 'bindings.json')
    inputs = {'design':design,'graph':graph,'bindings':bindings,'resolved':resolved,'before':before,'after':after}
    def pins():
        return {k:sync.read_json(p)[1] for k,p in inputs.items()}
    first = pins()
    prior = None
    if prior_sync is not None:
        previous = Path(prior_sync).resolve(strict=True)
        previous_run = sync.read_json(previous / 'result.json')[0]
        if previous_run.get('status') != 'applied' or previous_run.get('page_id') != page_id:
            raise ValueError('Prior run must be applied and belong to the selected page.')
        prior = previous / 'token-plan'
        if previous_run.get('token_report_sha256') != sync.read_json(prior / 'impact.json')[1]:
            raise ValueError('Prior token report digest differs from the applied result.')
    output.mkdir(exist_ok=False)
    receipt = {'status':'incomplete','applied':False,'page_id':page_id,'inputs':first,'planned_files':[]}
    try:
        directory = output / 'token-plan'
        if prior is None:
            impact = sync.sync_tokens(design,resolved,before,after,page_id,graph,directory)
        else:
            impact = sync.sync_tokens(design,resolved,before,after,page_id,graph,directory,prior_sync=prior)
        source, source_sha = sync.read_json(design)
        revised, _ = sync.read_json(directory / 'design.json')
        scope = code.analyze(root, source, revised)
        save(output/'code-scope.json', scope)
        if {item['root'] for s in impact['screens'] for item in s['paths']} - set(impact['changed_roots']):
            raise ValueError('Unexpected graph path origin')
        if set(scope['changed_tokens']) != set(impact['affected_tokens']):
            raise ValueError('Disagreement between graph and compiled token changes.')
        changes = list(scope['plan'])
        if impact['changes']:
            changes.append({'path':'design.json','content':encode(revised),'preimage_sha256':source_sha})
        receipt.update(planned_files=[i['path'] for i in changes],
                       declared_screens=[s['screen_id'] for s in impact['screens']],
                       observed_code_ids=sorted({node for use in scope['observed_consumers'] for node in use['code_ids']}),
                       token_report_sha256=sync.read_json(directory/'impact.json')[1])
        if pins() != first:
            raise ValueError('Inputs changed during planning. Inspect a fresh report.')
        receipt.update(expected_after={i['path']:hashlib.sha256(i['content'].encode()).hexdigest() for i in changes})
        # Render first so a reporting failure cannot occur between coordinated project writes.
        html = html_report(impact, scope, receipt)
        (output / 'impact.html').write_text(html, encoding='utf-8')
        if apply:
            code.apply_changes(root, changes)
        receipt.update(status='applied' if apply else 'planned',applied=apply)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        receipt['status']='failed'
        receipt['error']=str(error)
        raise
    finally:
        save(output/'result.json', receipt)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('project','resolved','before','after','out'):
        parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--page-id',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--prior-sync',type=Path)
    a=parser.parse_args()
    try:
        result=run(a.project,a.resolved,a.before,a.after,a.page_id,a.out,a.apply,a.prior_sync)
        print(json.dumps(result,ensure_ascii=False))
    except (OSError,ValueError,TypeError,KeyError,RuntimeError) as error:
        parser.exit(1,f'apply-figma-change: {error}\n')
