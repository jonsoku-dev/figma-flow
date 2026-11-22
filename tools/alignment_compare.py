#!/usr/bin/env python3
"""Build a standalone Korean before/after review from two browser alignment reports."""
import argparse
import base64
import html
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


def escape(value):
    return html.escape(str(value), quote=True)


def location(url):
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or parts.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Expected a local screen URL.')
    return (parts.scheme, parts.netloc), (parts.path or '/', parts.query, parts.fragment)


def comparable(before, after, same_screen):
    if before.get('schemaVersion') != 1 or after.get('schemaVersion') != 1:
        raise ValueError('Unsupported report schema.')
    for key in ('rulesSha256', 'browser', 'pageKey'):
        if not before.get(key) or before[key] != after.get(key):
            raise ValueError(f'Comparison requires the same {key}.')
    old_sizes = [(v['width'], v['height']) for v in before['viewports']]
    new_sizes = [(v['width'], v['height']) for v in after['viewports']]
    if not old_sizes or len(old_sizes) != len(set(old_sizes)) or sorted(old_sizes) != sorted(new_sizes):
        raise ValueError('Comparison requires the same unique viewport sizes.')
    new_by_size = dict(zip(new_sizes, after['viewports']))
    pairs = []
    for old, size in zip(before['viewports'], old_sizes):
        new = new_by_size[size]
        for a, b in ((before['url'], after['url']), (old['finalUrl'], new['finalUrl'])):
            origin_a, path_a = location(a)
            origin_b, path_b = location(b)
            if path_a != path_b or (origin_a != origin_b and not same_screen):
                raise ValueError('Different pages. For a known equivalent local server on a new port, use --same-screen.')
        if [g['id'] for g in old['groups']] != [g['id'] for g in new['groups']]:
            raise ValueError('Reports have different groups.')
        pairs.append((old, new))
    return pairs


def png(folder, width, variant):
    if type(width) is not int or width <= 0:
        raise ValueError('Invalid viewport width.')
    path = folder / f'width-{width}-{variant}.png'
    if path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Invalid screenshot file.')
    data = path.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG screenshot.')
    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')


def metrics(group):
    targets = group['targets']
    measured = [r.get('deviation', r.get('delta')) for r in targets if r.get('status') in ('pass', 'drift')]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in measured):
        raise ValueError('Expected a finite deviation for every measured target.')
    value = f'{max(map(abs, measured)):g} px' if measured else '—'
    if not targets or len(measured) != len(targets):
        state = '미확인'
    else:
        state = '편차 있음' if any(r['status'] == 'drift' for r in targets) else '통과'
    identities = [(r['selector'], r.get('occurrenceIndex'), r.get('count')) for r in targets]
    return state, value, identities


def observations(group):
    def cell(row):
        if row is None:
            return '—'
        if row.get('status') == 'unverified':
            return '미확인 · ' + escape(row.get('reason', ''))
        return f'{row.get("deviation", row["delta"]):+g} px'
    return {(row['selector'], row.get('occurrenceIndex')): cell(row) for row in group['targets']}


def target_details(old, new):
    a, b = observations(old), observations(new)
    rows = []
    for selector, index in dict.fromkeys([*a, *b]):
        key = (selector, index)
        occurrence = '' if index is None else f' [{index + 1}]'
        rows.append(f'<tr><th scope="row"><code>{escape(selector)}{occurrence}</code></th>'
                    f'<td>{a.get(key, "—")}</td><td>{b.get(key, "—")}</td></tr>')
    return (f'<details><summary>{escape(new["id"])} · 대상별 편차</summary><p><code>{escape(new.get("anchor", ""))}</code></p>'
            '<table><thead><tr><th>대상</th><th>수정 전</th><th>수정 후</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></details>')


def review(before_file, after_file, output, same_screen=False):
    before, after = [json.loads(p.read_bytes()) for p in (before_file, after_file)]
    sections = []
    for old, new in comparable(before, after, same_screen):
        width = new['width']
        figures = []
        for label, folder in (('수정 전', before_file.parent), ('수정 후', after_file.parent)):
            guide = png(folder, width, 'guide-overlay')
            clean = png(folder, width, 'clean')
            figures.append(f'<figure><figcaption>{label}</figcaption><img src="{guide}" alt="{label} 기준선">'
                           f'<details><summary>기준선 없는 화면</summary><img src="{clean}" alt="{label} 원본"></details></figure>')
        rows = []
        details = []
        for a, b in zip(old['groups'], new['groups']):
            details.append(target_details(a, b))
            status_a, delta_a, ids_a = metrics(a)
            status_b, delta_b, ids_b = metrics(b)
            notes = ' · 대상 수 변경' if ids_a != ids_b else ''
            rows.append(f'<tr><th scope="row">{escape(b["id"])}</th><td>{status_a} · {delta_a}</td>'
                        f'<td>{status_b} · {delta_b}{notes}</td></tr>')
        notes = []
        for label, view in (('수정 전', old), ('수정 후', new)):
            if view.get('overflow'):
                notes.append(label + ' · 수평 넘침')
            if view.get('captureClipped'):
                notes.append(label + ' · 캡처 범위 제한')
        notice = '<p>' + ' / '.join(notes) + '</p>' if notes else ''
        sections.append(f'<section><h2>{width} × {new["height"]} px</h2>{notice}<div class="pair">{"".join(figures)}</div>'
                        f'<table><caption>그룹별 최대 절대 편차</caption><thead><tr><th>기준선</th><th>수정 전</th><th>수정 후</th></tr>'
                        f'</thead><tbody>{"".join(rows)}</tbody></table>{"".join(details)}</section>')
    body = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>화면 정렬 비교</title><style>*{box-sizing:border-box}body{font:15px/1.55 system-ui,sans-serif;color:#222c39;background:#fafbfc;margin:0}
main{max-width:1080px;margin:auto;padding:clamp(16px,3vw,36px)}h1,h2,figure{margin:0}h1{font-size:28px}h2{font-size:18px}
section{margin:20px 0 36px;padding-top:16px;border-top:1px solid #ccd1da}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
figcaption,caption,summary{padding:6px 0}img{display:block;max-width:100%;height:auto}table{width:100%;border-collapse:collapse;margin:18px 0 0}
caption{text-align:left;font-weight:650}th,td{text-align:left;border-bottom:1px solid #d9dfe6;padding:6px 4px;overflow-wrap:anywhere}summary{cursor:pointer}
@media(max-width:640px){.pair{grid-template-columns:1fr}}</style><main><h1>화면 정렬 비교</h1>''' + ''.join(sections) + '</main></html>'
    # Publish only the finished report. An existing review is never replaced.
    with tempfile.NamedTemporaryFile(dir=output.parent, mode='w', encoding='utf-8', delete=False) as tmp:
        staged = Path(tmp.name)
        try:
            tmp.write(body)
            tmp.flush()
            os.link(staged, output)
        finally:
            staged.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--same-screen', action='store_true', help='Confirm equivalent local origins when ephemeral ports differ.')
    args = parser.parse_args()
    try:
        review(args.before, args.after, args.out, args.same_screen)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'alignment-compare: {exc}\n')
    print(args.out)


if __name__ == '__main__':
    main()
