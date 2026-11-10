#!/usr/bin/env python3
"""Package a local design for browser, SVG and Figma development-plugin use."""
import argparse
import json
from pathlib import Path
import subprocess
from shlex import quote as shell_quote
import sys
from html import escape
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent / 'skills/figma-flow/scripts'))
import ssot


def token_sheet(design):
    # The palette and its consumer list are projections of the same resolved model.
    uses = {name: [] for name in design['tokens']}
    consumers = {}
    for screen in design['screens']:
        for item in screen['elements']:
            if item['kind'] == 'component':
                consumers.setdefault((item['component'], item['variant']), set()).add(screen['id'])
    for component, definition in design['components'].items():
        for variant, styles in definition['variants'].items():
            for prop, path in styles.items():
                while path:
                    uses[path].append((component, variant, prop))
                    path = design['tokens'][path]['alias']
    cards = []
    for path, token in design['tokens'].items():
        sample = f'<i style="background:{escape(token["value"])}" aria-hidden="true"></i>' if token['type']=='color' else ''
        roles = sorted(set(uses[path]))
        rows = []
        for name, variant, prop in roles:
            screens = ', '.join(sorted(consumers.get((name,variant),()))) or '배치된 화면 없음'
            rows.append(f'<li>{escape(name)} / {escape(variant)} · {escape(prop)} → {escape(screens)}</li>')
        ref = f' · {escape(token["alias"])} 참조' if token['alias'] else ''
        cards.append(f'<details><summary>{sample}{escape(path)} · {escape(str(token["value"]))}</summary>'
                     f'<p>{escape(token["type"])}{ref}</p><ul>' + (''.join(rows) or '<li>이 디자인에 연결된 컴포넌트 없음</li>') + '</ul></details>')
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<link rel="icon" href="data:,"><title>토큰과 사용처</title><style>body{max-width:54rem;margin:3rem auto;padding:1rem;font:1rem/1.65 system-ui}'
            'details{padding:.7rem 0;border-bottom:1px solid #ccd0d9;overflow-wrap:anywhere}summary{cursor:pointer}summary:focus-visible{outline:3px solid #425cc7}'
            'i{display:inline-block;width:1rem;height:1rem;border:1px solid #777;border-radius:3px;margin-right:.5em}</style>'
            '<a href="index.html">디자인 전달</a><h1>토큰과 사용처</h1><p>토큰을 열면 해당 값을 사용하는 컴포넌트 속성과 화면을 확인할 수 있습니다.</p>'
            + ''.join(cards) + '</html>')


def landing(links, svgs, *, draft_only=False):
    if draft_only:
        items = ''.join(f'<li><a href="{quote(path)}">{escape(label)}</a></li>' for label, path in links)
        return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>탐색 시안</title><h1>탐색 시안</h1><p>후보를 비교하고 사람이 선택하기 전의 로컬 미리보기입니다.</p>'
                + '<ul>' + items + '</ul></html>')

    items = ''.join(f'<li><a href="{quote(path)}">{escape(label)}</a></li>' for label, path in links)
    assets = []
    for i, svg in enumerate(svgs):
        assets.append(f'<li><a href="preview/{quote(svg.name)}">{escape(svg.stem)}</a> '
                      f'<button type="button" data-copy="svg-{i}">SVG 복사</button>'
                      f'<textarea id="svg-{i}" aria-label="{escape(svg.stem)} SVG 원문" hidden readonly>'
                      f'{escape(svg.read_text(encoding="utf-8"))}</textarea></li>')
    return """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,"><title>디자인 전달</title><style>body{max-width:48rem;margin:3rem auto;padding:1rem;font:1rem/1.7 system-ui}li{margin:.5em 0;overflow-wrap:anywhere}a{color:#1849a5}button,textarea{font:inherit}textarea{width:100%;box-sizing:border-box}</style>
<h1>디자인 전달</h1><ul>""" + items + """</ul><h2>Figma로 가져오기</h2>
<p>화면별 SVG를 편집 가능한 Figma 캔버스에 끌어 놓거나 복사해 붙여 넣으세요.
변수와 컴포넌트 인스턴스까지 사용하려면 개발 플러그인 ZIP을 풀고 Figma Desktop에서 발급한 플러그인 ID로 빌드하세요.</p>
<p>Figma 전달은 아직 pending_native_handoff 상태입니다. 네이티브 주석·컴포넌트 사용·변수 바인딩을 가져온 뒤 읽기 JSON으로 --require-match 검증을 통과해야 완료됩니다. SVG 수동 내보내기는 로컬 미리보기입니다.</p>
<ul>""" + ''.join(assets) + """</ul><p role="status" id="status"></p>
<script>for(const b of document.querySelectorAll('[data-copy]'))b.addEventListener('click',async()=>{
const src=document.getElementById(b.dataset.copy),status=document.getElementById('status');
try{await navigator.clipboard.writeText(src.value);status.textContent='SVG를 복사했습니다. Figma 캔버스에 붙여 넣으세요.'}
catch{src.hidden=false;src.select();status.textContent='선택한 SVG 원문을 복사하세요.'}
});</script></html>"""


def build(design, graph, out, plugin_id=None, *, selection_path=None, draft_only=False, batch_path=None, asset_receipts=None):
    from design_directions import guard_production
    from workflow import State, Event
    if draft_only and plugin_id:
        raise ValueError('A draft does not export an installable Figma plugin.')
    selected = None if draft_only else guard_production(selection_path, event=Event.HANDOFF_NATIVE,
                                                        product_graph=graph, batch_path=batch_path,
                                                        asset_receipts=asset_receipts)
    design, graph, out = (Path(p).absolute() for p in (design, graph, out))
    if any(out.resolve() in p.resolve().parents or out.resolve() == p.resolve() for p in (design, graph)):
        raise ValueError('Choose output separate from input files.')
    inputs = {key: {'path': str(p), 'sha256': ssot.read_local(p)[0]} for key, p in (('design', design), ('graph', graph))}
    if selected and inputs['graph']['sha256'] != selected['product_graph']['sha256']:
        raise ValueError('The product graph does not match the selected direction. Present the revised graph for review.')
    if design.resolve() == graph.resolve():
        raise ValueError('Design and product graph must be separate inputs.')
    out.mkdir(exist_ok=False)
    record = {'status': 'incomplete', 'inputs': inputs, 'steps': [], 'figma_mcp_calls': 0, 'live_figma_verified': False}

    if selected:
        record['design_selection'] = {key: selected[key] for key in (
            'candidate_id', 'candidate_sha256', 'selection_sha256', 'workflow_graph_sha256')}
        record['design_selection']['product_graph_sha256'] = selected['product_graph']['sha256']
        record['workflow_state'] = State.GENERATION.value if asset_receipts else State.SELECTED.value
        record['admitted_native_event'] = Event.HANDOFF_NATIVE.value
    def step(name, *args):
        proc = subprocess.run([sys.executable, '-B', str(TOOLS / name), *map(str, args)],
                              capture_output=True, text=True)
        record['steps'].append({'tool': name, 'exit': proc.returncode})
        if proc.returncode:
            raise ValueError(f'{name}: {proc.stderr.strip() or proc.stdout.strip()}')

    try:
        preview = out / 'preview'
        step('design_system.py', '--input', design, '--out', preview)
        step('design_graph.py', '--graph', graph, '--design', design, '--out', out / 'design-graph.json')
        coverage = ssot.read_json(out / 'design-graph.json')['design_system']
        if any(coverage['inputs'][key]['sha256'] != value['sha256'] for key, value in inputs.items()):
            raise ValueError('Design graph was derived from unexpected input bytes.')
        sha, _ = ssot.read_local(preview / 'resolved.json')
        (out / 'tokens.html').write_text(token_sheet(ssot.read_json(preview / 'resolved.json')), encoding='utf-8')
        links = [('토큰과 사용처', 'tokens.html'), ('스타일 시안', 'preview/styled.html'), ('와이어프레임', 'preview/wireframe.html'),
                 ('CSS 변수', 'preview/tokens.css'), ('재사용 컴포넌트 CSS', 'preview/components.css'), ('토큰·컴포넌트 추적 그래프', 'design-graph.json')]
        if draft_only:
            (out / 'index.html').write_text(landing(links, [], draft_only=True), encoding='utf-8')
            record.update(status='exploratory', draft_only=True, production_eligible=False, resolved_sha256=sha)
            return record
        from figma_bridge import compile_plugin
        bridge_step = {'tool': 'figma_bridge.py', 'exit': 1}
        record['steps'].append(bridge_step)
        compiled = compile_plugin(preview / 'resolved.json', sha, out / 'figma-plugin', plugin_id,
                                  selection_path=selection_path, product_graph=graph,
                                  batch_path=batch_path, asset_receipts=asset_receipts)
        record['warnings'] = compiled['warnings']
        bridge_step['exit'] = 0
        if ssot.read_json(out / 'figma-plugin/reviewed-payload.json')['source_sha256'] != sha:
            raise ValueError('Bridge payload does not match the compiled tokens.')
        if any(ssot.read_local(data['path'])[0] != data['sha256'] for data in inputs.values()):
            raise ValueError('Source changed during export. Run again in a new directory.')
        with ZipFile(out / 'figma-plugin.zip', 'x', compression=ZIP_DEFLATED) as archive:
            for p in sorted((out / 'figma-plugin').iterdir()):
                if p.is_file():
                    archive.write(p, p.name)
        links.extend([('Figma 개발 플러그인 ZIP', 'figma-plugin.zip'), ('생성된 네이티브 기대 계약', 'figma-plugin/expected-native-handoff.json')])
        links.append(('개발 플러그인 사용법', 'figma-plugin/README.md'))
        (out / 'index.html').write_text(landing(links, sorted(preview.glob('*.svg'))), encoding='utf-8')
        record.update(status='pending_native_handoff', design_completion='pending_design_review', resolved_sha256=sha,
                      native_handoff_contract='figma-plugin/expected-native-handoff.json',
                      native_handoff_command=f'python3 tools/native_handoff.py --readback READBACK.json --contract {shell_quote(str(out / "figma-plugin/expected-native-handoff.json"))} --out NEW_HANDOFF_DIRECTORY',
                      acceptance_command='python3 tools/figma_bridge.py --inspect-readback READBACK.json --input preview/resolved.json --expected figma-plugin/expected-native-handoff.json --require-match',
                      limitation='Local artifacts generated; native Figma import requires a separate editor run.')
    except (OSError,ValueError) as exc:
        record['error']=str(exc)
        raise
    finally:
        (out/'bundle.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('design','graph','out'):
        parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--selection', type=Path, help='Verified human choice receipt for the exact product graph')
    parser.add_argument('--batch', type=Path, help='Selected and frozen batch when the brief needs generated assets')
    parser.add_argument('--asset-receipts', type=Path, help='Actual returned generated files for that batch')
    parser.add_argument('--draft-only', action='store_true', help='Export exploratory local previews only; no Figma import bundle')
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument('--plugin-id', help='numeric ID assigned by Figma for your development plugin')
    identity.add_argument('--id-from', type=Path, help='manifest.json of your dedicated local Figma development plugin')
    args=parser.parse_args()
    try:
        plugin_id = args.plugin_id
        if args.id_from:
            template = ssot.read_json(args.id_from)
            plugin_id = template.get('id') if isinstance(template, dict) else None
            if not isinstance(plugin_id, str) or not plugin_id.isascii() or not plugin_id.isdigit():
                raise ValueError('The supplied Figma manifest must contain its assigned numeric id.')
        result=build(args.design,args.graph,args.out,plugin_id,selection_path=args.selection,draft_only=args.draft_only,
                     batch_path=args.batch,asset_receipts=args.asset_receipts)
        print(f"Local design bundle ready: {args.out / 'index.html'}")
    except (OSError,ValueError,TypeError) as exc:
        parser.exit(1,f'Error: {exc}\n')
