"""Produce a portable, non-mutating review of candidate evidence. No browser is needed."""
import base64
import hashlib
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
from annotation_contract import derive_notes
from design_foundations import derive_foundations
from workflow import State


def _read(record):
    path = Path(record['path'])
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular pinned review input required')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('Review input changed: ' + record['path'])
    return data


def _write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def _render(data, out):
    """Validate pinned inputs, then write the human-facing HTML and image together."""
    out = Path(out)
    state = State(data['workflow_state'])
    candidates = data['candidates']
    sheet = Image.new('RGB', (460 * len(candidates), 750), '#ece9e0')
    drawing = ImageDraw.Draw(sheet)
    cards = []
    for index, card in enumerate(candidates):
        title = escape(card['id'] + ' · ' + card['title'])
        images = []
        for viewport in ('desktop', 'mobile'):
            preview = next(item for item in card['previews'] if item['viewport'] == viewport)
            with Image.open(BytesIO(_read(preview['file']))) as src:
                if src.size != (preview['width'], preview['height']):
                    raise ValueError('Review viewport size changed: ' + card['id'])
                thumb = src.convert('RGB')
            thumb.thumbnail((900, 600) if viewport == 'desktop' else (390, 900), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            thumb.save(buffer, 'JPEG', quality=89, optimize=True)
            url = 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode()
            images.append('<figure><figcaption>' + ('첫 화면' if viewport == 'desktop' else '모바일') +
                          '</figcaption><img alt="' + title + '" src="' + url + '"></figure>')
            thumb.thumbnail((430, 270) if viewport == 'desktop' else (190, 415), Image.Resampling.LANCZOS)
            x = index * 460 + (460 - thumb.width) // 2
            sheet.paste(thumb, (x, 45 if viewport == 'desktop' else 320))
        drawing.text((index * 460 + 16, 13), card['id'], fill='#102b36', font_size=21)
        graph = json.loads(_read(card['product_graph']))
        notes = derive_notes(graph)
        foundations = derive_foundations(graph)
        note_rows = []
        for note in notes:
            meaning = [note[key] for key in ('purpose','journey','behavior','result','failure') if note.get(key)]
            note_rows.append('<li><b>' + escape(note['id']) + '</b> ' + escape(' '.join(meaning)) + '</li>')
        roles = ''.join('<tr><td>' + escape(str(role.get('token', ''))) + '</td><td>' +
                        escape(str(role.get('value', ''))) + '</td></tr>' for role in foundations['roles'])
        samples = ''.join('<li>' + escape(' · '.join(str(sample.get(key, '')) for key in ('label','action','state'))) +
                          '</li>' for sample in foundations['palette']['samples'])
        source = escape(os.path.relpath(card['source']['path'], out), quote=True)
        cards.append('<article><h2>' + title + '</h2><p>' + escape(card['composition']) + '</p>' +
                     '<div class="shots">' + ''.join(images) + '</div><p>' + escape(card['typography']) + '</p><p>' +
                     escape(card['interaction']) + '</p><details><summary>계획 주석 · 컴포넌트 팔레트 · 토큰</summary><ul>' +
                     ''.join(note_rows) + '</ul><h3>제안 컴포넌트</h3><ul>' + samples +
                     '</ul><h3>제안 토큰</h3><table><tbody>' + roles +
                     '</tbody></table><p>이 내용은 탐색 시안의 제안입니다. Figma 네이티브 관측을 나타내지 않습니다.</p></details>' +
                     '<a href="' + source + '">프로젝트 원본에서 동작 보기</a></article>')
    html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>디자인 시안 비교</title>
<style>*{box-sizing:border-box}body{margin:auto;max-width:1640px;padding:clamp(18px,3vw,52px);background:#f3f0e9;color:#183036;font:17px/1.65 system-ui,sans-serif}h1,h2,h3{line-height:1.3}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:24px}.shots{display:grid;grid-template-columns:2fr 1fr;align-items:start;gap:6px}img{display:block;height:auto;width:100%}figure{margin:0}figcaption{font-size:14px}article{border-top:1px solid #6b7978}details{margin:1em 0}summary{cursor:pointer;font-weight:600}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #c9c8bf;padding:.4em;overflow-wrap:anywhere}a{color:#315465}code{overflow-wrap:anywhere}</style>
<h1>디자인 시안 비교</h1><p>같은 내용의 첫 화면과 모바일 구도를 비교하고, 원하는 후보의 ID를 알려주세요. 이미지는 이 파일에 포함돼 있습니다.</p><p>현재 단계 <code>''' + escape(state.name) + '</code></p><main class="cards">' + ''.join(cards) + '</main></html>'
    comparison = BytesIO()
    sheet.save(comparison, 'JPEG', quality=91, optimize=True)
    return html, comparison.getvalue()


def render_surface(data, out):
    """Recompute the HTML for a pinned draft revision without changing any files."""
    return _render(data, Path(out))[0]


def write_surface(data, out):
    out = Path(out)
    html, image = _render(data, out)
    _write(out/'direction-comparison.jpg', image)
    _write(out/'review.html', html.encode())
    return {'review_page': str(out/'review.html'), 'comparison_image': str(out/'direction-comparison.jpg')}
