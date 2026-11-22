"""Produce a portable, non-mutating review of candidate evidence. No browser is needed."""
from report_appearance import graphic, report_css
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
    layout = graphic('directionSheet')
    card_width = layout['cardWidth']
    sheet = Image.new('RGB', (card_width * len(candidates), layout['height']), layout['paper'])
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
            thumb.thumbnail(tuple(layout[viewport]['embed']), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            thumb.save(buffer, 'JPEG', quality=layout['thumbnailQuality'], optimize=True)
            url = 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode()
            images.append('<figure><figcaption>' + ('첫 화면' if viewport == 'desktop' else '모바일') +
                          '</figcaption><img alt="' + title + '" src="' + url + '"></figure>')
            thumb.thumbnail(tuple(layout[viewport]['sheet']), Image.Resampling.LANCZOS)
            x = index * card_width + (card_width - thumb.width) // 2
            sheet.paste(thumb, (x, layout[viewport]['top']))
        drawing.text((index * card_width + layout['labelX'], layout['labelY']), card['id'], fill=layout['ink'], font_size=layout['labelSize'])
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
    direct = data.get('mode') == 'direct'
    heading = '디자인 방향 검토' if direct else '디자인 시안 비교'
    instruction = ('지정한 한 방향의 첫 화면과 모바일 구도를 검토합니다. 후보 선택은 요구하지 않습니다. 현재 산출물 검토와 실제 사용자 지시 근거를 확인한 뒤 진행합니다.' if direct else
                   '같은 내용의 첫 화면과 모바일 구도를 비교하고, 원하는 후보의 ID를 알려주세요. 이미지는 이 파일에 포함돼 있습니다.')
    html = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>''' + heading + '''</title>
<style>''' + report_css("directions") + '''</style>
<h1>''' + heading + '</h1><p>' + instruction + '''</p><p>현재 단계 <code>''' + escape(state.name) + '</code></p><main class="cards">' + ''.join(cards) + '</main></html>'
    comparison = BytesIO()
    sheet.save(comparison, 'JPEG', quality=layout['sheetQuality'], optimize=True)
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
