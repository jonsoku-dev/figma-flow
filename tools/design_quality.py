#!/usr/bin/env python3
"""Design quality gate for authored native review layouts.

Objective defects (contrast, off-canvas, text overlap/overflow, tiny text, control size/overlap, invisible or unreadable controls)
are errors and block review packaging. Heuristics (placeholder bars, missing roles, ornament
weight, no visual anchor, monotone centering, type scale, density) are warnings only.
Reads JSON and optional local font files; never writes to Figma or the layout.
"""
import argparse
import json
from pathlib import Path
import re
import sys

SCHEMA = 'figma-flow-design-quality-v1'
LAYOUT_SCHEMA = 'figma-flow-authored-native-layout-v1'
ROLES = {'background', 'surface', 'illustration', 'image', 'divider', 'ornament', 'frame'}
BLEED_ROLES = {'background', 'ornament', 'illustration', 'image'}
VISUAL_ROLES = {'illustration', 'image'}
CANVAS_SLACK = 4
OVERLAP_SHARE = .05
MIN_TEXT = 12
CONTROL_MIN_H = {'mobile': 44, 'desktop': 36}
CONTROL_MIN_W = 44
CONTROL_FILL_MIN = 1.25  # below this a button fill is indistinguishable from what it sits on
BAR_THICKNESS = 64
BAR_RATIO = 6
ORNAMENT_COUNT = 8
ORNAMENT_SHARE = .25
DENSITY_MIN = .12
CJK = re.compile('[ᄀ-ᇿ　-ヿ㄰-㆏㐀-鿿가-힯＀-￯]')

FIX = {
    'contrast': '글자색 또는 배경 역할의 HEX를 조정하거나 텍스트를 대비가 충분한 면 위로 옮기세요.',
    'off-canvas': '좌표와 크기를 프레임 안으로 줄이세요. 의도한 bleed라면 background·ornament·illustration·image 역할을 선언하세요.',
    'text-overlap': '텍스트 박스를 세로로 분리하거나 한쪽 문장을 줄이세요.',
    'text-overflow': '박스의 w/h를 늘리거나 줄을 바꾸거나 글자 크기를 한 단계 낮추세요.',
    'text-overflow-estimated': '글꼴 파일(fonts/sources.json)과 Pillow가 있는 환경에서 다시 실행하거나 박스에 여유를 두세요.',
    'tiny-text': '글자 크기를 12 이상으로 올리세요.',
    'control-size': '버튼 영역을 모바일 높이 44, 데스크톱 높이 36, 너비 44 이상으로 키우세요.',
    'control-text-overlap': '버튼 주변 텍스트를 옮기세요. 버튼 라벨은 컨트롤이 직접 그립니다.',
    'control-invisible': '버튼 fill을 놓인 배경과 구분되는 색상 역할로 바꾸세요.',
    'control-label-contrast': '버튼 ink와 fill의 대비를 4.5:1 이상(24px 이상은 3:1)으로 맞추세요.',
    'placeholder-bar': '막대를 지우거나 의미 있는 형태(타원 조명, 라운드 도형, 이미지)로 바꾸고, 진짜 구분선이면 role "divider"를 선언하세요.',
    'missing-role': 'background·surface·illustration·image·divider·ornament·frame 중 하나를 선언하세요. 고를 역할이 없으면 레이어가 필요한지 다시 보세요.',
    'ornament-heavy': '장식을 줄이고 구조를 이루는 도형은 frame·surface 역할로 선언하세요.',
    'no-visual-anchor': '진입 화면에 탐색용 이미지 자산, illustration 도형 구성(타원·라운드 도형) 또는 그라디언트를 추가하세요.',
    'all-centered': '텍스트 열을 한쪽으로 정렬하거나 시각적 중심과 비대칭으로 배치하세요.',
    'type-scale': '글자 크기를 3–5단계로 정리하세요.',
    'low-density': '시각적 중심을 키우거나 내용을 보강하세요.',
    'contrast-unknown': '렌더한 미리보기에서 대비를 직접 확인해 검토 메모에 적거나 텍스트 뒤에 불투명 surface를 까세요.',
}


def _rgb(hex_value):
    value = str(hex_value).lstrip('#')
    if len(value) != 6:
        raise ValueError('색상 HEX 형식 오류: ' + str(hex_value))
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(rgb):
    def channel(c):
        return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return .2126 * r + .7152 * g + .0722 * b


def contrast_ratio(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + .05) / (lb + .05)


def _box(layer):
    return float(layer['x']), float(layer['y']), float(layer['w']), float(layer['h'])


def _intersection(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


def _covers(layer, px, py):
    x, y, w, h = _box(layer)
    if layer['kind'] == 'ellipse':
        rx, ry = w / 2, h / 2
        return rx > 0 and ry > 0 and ((px - x - rx) / rx) ** 2 + ((py - y - ry) / ry) ** 2 <= 1
    return x <= px <= x + w and y <= py <= y + h


class _Fonts:
    """Resolve candidate font roles to local files via <layout_dir>/fonts/sources.json."""

    def __init__(self, layout_dir):
        self.dir = Path(layout_dir) if layout_dir else None
        self.sources = {}
        self.cache = {}
        if self.dir and (self.dir / 'fonts/sources.json').is_file():
            try:
                self.sources = json.loads((self.dir / 'fonts/sources.json').read_text())
            except (OSError, ValueError):
                self.sources = {}

    def get(self, family, size):
        record = self.sources.get(family) if isinstance(self.sources, dict) else None
        if not isinstance(record, dict) or not record.get('file'):
            return None
        key = (family, size)
        if key not in self.cache:
            self.cache[key] = None
            try:
                from PIL import ImageFont
                path = (self.dir / record['file']).resolve()
                if path.is_file():
                    font = ImageFont.truetype(str(path), max(1, round(size)))
                    try:
                        axes = font.get_variation_axes()
                        font.set_variation_by_axes([400 if a.get('name') in (b'Weight', 'Weight') else a.get('default', 0) for a in axes])
                    except (OSError, AttributeError, ValueError):
                        pass
                    self.cache[key] = font
            except (ImportError, OSError, ValueError):
                self.cache[key] = None
        return self.cache[key]


def _wrap_lines(value, width, measure):
    lines = 0
    longest = 0.0
    for paragraph in str(value).split('\n'):
        line = ''
        for word in re.findall(r'\S+\s*', paragraph) or ['']:
            if measure((line + word).rstrip()) <= width:
                line += word
                continue
            if line.strip():
                lines += 1
                longest = max(longest, measure(line.rstrip()))
                line = ''
            for char in word:
                if line and measure((line + char).rstrip()) > width:
                    lines += 1
                    longest = max(longest, measure(line.rstrip()))
                    line = ''
                line += char
        lines += 1
        longest = max(longest, measure(line.rstrip()))
    return lines, longest


def _estimate(text, size):
    return sum((1.0 if CJK.match(ch) else .56) * size for ch in text)


class _State:
    def __init__(self, report, candidate, viewport, state_id, state, colors, fonts, entry, strict_fonts, variants=None):
        self.report, self.candidate, self.viewport, self.state_id = report, candidate, viewport, state_id
        self.variants = variants or {}
        self.state, self.colors, self.fonts, self.entry = state, colors, fonts, entry
        self.width, self.height = float(state['width']), float(state['height'])
        self.layers = [l for l in state.get('layers', []) if isinstance(l, dict)]
        self.texts = [l for l in self.layers if l.get('kind') == 'text']
        self.shapes = [l for l in self.layers if l.get('kind') != 'text']
        self.metrics = {'text_measurement': 'none'}
        self.strict_fonts = strict_fonts

    def add(self, severity, code, layer, message):
        self.report[severity + 's'].append({'code': code, 'severity': severity, 'candidate': self.candidate['id'],
                                            'viewport': self.viewport, 'state': self.state_id, 'layer': layer,
                                            'message': message, 'fix': FIX[code]})

    def color(self, name):
        if name not in self.colors:
            raise ValueError('선언되지 않은 색상 역할: %s/%s' % (self.candidate['id'], name))
        return _rgb(self.colors[name])

    def run(self):
        self.contrast()
        self.canvas()
        self.text_boxes()
        self.controls()
        self.bars_and_roles()
        self.composition()
        return self.metrics

    # -- objective checks -------------------------------------------------
    def background_under(self, index, px, py):
        """Composite every shape below layer `index` covering (px, py); None if an image/gradient decides it."""
        stack = []
        for layer in reversed(self.layers[:index]):
            if layer.get('kind') == 'text' or not _covers(layer, px, py):
                continue
            if layer.get('kind') in ('image', 'gradient'):
                return None
            if layer.get('kind') not in ('rect', 'ellipse'):
                continue
            opacity = float(layer.get('opacity', 1))
            stack.append((self.color(layer['fill']), opacity))
            if opacity >= 1:
                break
        else:
            stack.append((self.color(self.state['bg']), 1.0))
        base = stack[-1][0]  # always opaque: the break above or the state background
        for rgb, opacity in reversed(stack[:-1]):
            base = tuple(o * opacity + b * (1 - opacity) for o, b in zip(rgb, base))
        return base

    def contrast(self):
        worst = None
        for index, layer in enumerate(self.layers):
            if layer.get('kind') != 'text' or not str(layer.get('value', '')).strip():
                continue
            x, y, w, h = _box(layer)
            bg = self.background_under(index, x + w / 2, y + h / 2)
            if bg is None:
                self.add('warning', 'contrast-unknown', layer['id'], '이미지·그라디언트 위의 텍스트라 대비를 자동으로 판정할 수 없습니다.')
                continue
            ratio = contrast_ratio(self.color(layer['ink']), bg)
            worst = ratio if worst is None else min(worst, ratio)
            need = 3.0 if float(layer.get('size', 0)) >= 24 else 4.5
            if ratio < need:
                self.add('error', 'contrast', layer['id'], '텍스트와 배경의 대비가 %.2f:1로 기준 %.1f:1보다 낮습니다.' % (ratio, need))
        self.metrics['min_contrast'] = round(worst, 2) if worst is not None else None

    def canvas(self):
        for layer in self.layers:
            if not all(k in layer for k in ('x', 'y', 'w', 'h')):
                continue
            x, y, w, h = _box(layer)
            outside = max(-x, -y, x + w - self.width, y + h - self.height)
            if outside > CANVAS_SLACK:
                bleed = layer.get('kind') != 'text' and layer.get('role') in BLEED_ROLES
                self.add('warning' if bleed else 'error', 'off-canvas', layer['id'],
                         '레이어가 프레임 밖으로 %gpx 나갑니다.' % round(outside, 1))

    def text_boxes(self):
        for i, a in enumerate(self.texts):
            for b in self.texts[i + 1:]:
                ba, bb = _box(a), _box(b)
                smaller = min(ba[2] * ba[3], bb[2] * bb[3])
                if smaller > 0 and _intersection(ba, bb) > OVERLAP_SHARE * smaller:
                    self.add('error', 'text-overlap', b['id'], '텍스트 "%s"와 "%s"의 박스가 겹칩니다.' % (a['id'], b['id']))
        measured = estimated = 0
        for layer in self.texts:
            size = float(layer.get('size', 0))
            if size < MIN_TEXT:
                self.add('error', 'tiny-text', layer['id'], '글자 크기 %g가 최소 %d보다 작습니다.' % (size, MIN_TEXT))
            value = str(layer.get('value', ''))
            if not value.strip() or size <= 0:
                continue
            font_role = self.candidate.get('fonts', {}).get(layer.get('font', 'body'), {})
            font = self.fonts.get(font_role.get('family'), size)
            if font is not None:
                measure = font.getlength
                measured += 1
            else:
                def measure(text, size=size):
                    return _estimate(text, size)
                estimated += 1
            x, y, w, h = _box(layer)
            leading = float(layer.get('leading') or size * 1.2)
            lines, longest = _wrap_lines(value, w + .5, measure)
            if lines * leading > h + 1 or longest > w + .5:
                if font is not None:
                    self.add('error', 'text-overflow', layer['id'], '텍스트가 %d줄(%gpx)로 박스 높이 %gpx를 넘습니다.' % (lines, lines * leading, h))
                else:
                    self.add('warning', 'text-overflow-estimated', layer['id'], '추정 폭으로 %d줄(%gpx)이 되어 박스 높이 %gpx를 넘을 수 있습니다.' % (lines, lines * leading, h))
        self.metrics['text_measurement'] = 'measured' if measured and not estimated else 'estimated' if estimated and not measured else 'mixed' if measured else 'none'

    def controls(self):
        min_h = CONTROL_MIN_H.get(self.viewport, 44)
        for control_id, box in (self.state.get('control_boxes') or {}).items():
            if not (isinstance(box, list) and len(box) == 4):
                continue
            bx = tuple(float(v) for v in box)
            if bx[3] < min_h or bx[2] < CONTROL_MIN_W:
                self.add('error', 'control-size', control_id, '버튼 영역 %gx%g가 최소 %dx%d보다 작습니다.' % (bx[2], bx[3], CONTROL_MIN_W, min_h))
            for layer in self.texts:
                if _intersection(bx, _box(layer)) > 0:
                    self.add('error', 'control-text-overlap', control_id, '버튼 영역이 텍스트 "%s"와 겹칩니다.' % layer['id'])
            self.control_colors(control_id, bx)

    def control_colors(self, control_id, bx):
        """A button must read against its own label and against what it sits on.

        The variant a control uses lives in the annotations; without them only a
        defect shared by every declared variant is certain enough to block.
        """
        styles = (self.candidate.get('control_styles') or {}).get(self.viewport) or {}
        known = styles.get(self.variants.get(control_id))
        rows = [known] if isinstance(known, dict) else [s for s in styles.values() if isinstance(s, dict)]
        rows = [s for s in rows if s.get('fill') in self.colors and s.get('ink') in self.colors]
        if not rows:
            return
        bg = self.background_under(len(self.layers), bx[0] + bx[2] / 2, bx[1] + bx[3] / 2)
        labels, fills = [], []
        for style in rows:
            fill = self.color(style['fill'])
            need = 3.0 if float(style.get('fontSize') or 0) >= 24 else 4.5
            labels.append((contrast_ratio(self.color(style['ink']), fill), need))
            if bg is not None:
                fills.append(contrast_ratio(fill, bg))
        if all(ratio < need for ratio, need in labels):
            ratio, need = max(labels)
            self.add('error', 'control-label-contrast', control_id, '버튼 글자와 버튼 색의 대비가 %.2f:1로 기준 %.1f:1보다 낮습니다.' % (ratio, need))
        if fills and all(ratio < CONTROL_FILL_MIN for ratio in fills):
            self.add('error', 'control-invisible', control_id, '버튼 색이 놓인 배경과 %.2f:1로 거의 같아 버튼이 보이지 않습니다.' % max(fills))

    # -- heuristic warnings -----------------------------------------------
    def bars_and_roles(self):
        frame_area = self.width * self.height
        ornament_count = 0
        ornament_area = 0.0
        blockers = [_box(l) for l in self.layers if l.get('kind') in ('text', 'image')]
        for layer in self.shapes:
            role = layer.get('role')
            if role is None:
                self.add('warning', 'missing-role', layer['id'], '도형 레이어에 role이 없습니다.')
            elif role not in ROLES:
                self.add('warning', 'missing-role', layer['id'], '알 수 없는 role "%s"입니다.' % role)
            if role in (None, 'ornament') and all(k in layer for k in ('w', 'h')):
                x, y, w, h = _box(layer)
                ornament_count += 1
                ornament_area += max(w, 0) * max(h, 0)
                thin, long = min(w, h), max(w, h)
                if (layer.get('kind') == 'rect' and thin > 0 and thin <= BAR_THICKNESS and long / thin >= BAR_RATIO
                        and not any(_intersection((x, y, w, h), b) > 0 for b in blockers)):
                    self.add('warning', 'placeholder-bar', layer['id'],
                             '%gx%g 단색 막대가 의미 없이 놓여 placeholder처럼 보입니다.' % (w, h))
        if ornament_count > ORNAMENT_COUNT or (frame_area and ornament_area / frame_area > ORNAMENT_SHARE):
            self.add('warning', 'ornament-heavy', None, '역할 없는·장식 도형이 %d개, 프레임의 %d%%를 차지합니다.'
                     % (ornament_count, round(100 * ornament_area / frame_area) if frame_area else 0))
        self.metrics['ornament_count'] = ornament_count
        self.metrics['ornament_share'] = round(ornament_area / frame_area, 3) if frame_area else 0

    def composition(self):
        visual = [l for l in self.shapes if l.get('kind') in ('image', 'gradient', 'ellipse') or l.get('role') in VISUAL_ROLES]
        if self.entry and not visual:
            self.add('warning', 'no-visual-anchor', None, '진입 화면에 이미지·일러스트·타원·그라디언트 같은 시각적 중심이 없습니다.')
        texts = [l for l in self.texts if str(l.get('value', '')).strip()]
        if len(texts) >= 3 and all(l.get('align') == 'center' for l in texts):
            centers = [float(l['x']) + float(l['w']) / 2 for l in texts]
            if max(centers) - min(centers) <= 2:
                self.add('warning', 'all-centered', None, '텍스트 %d개가 모두 같은 축에 가운데 정렬되어 있습니다.' % len(texts))
        sizes = sorted({float(l.get('size', 0)) for l in texts})
        if texts and (len(sizes) <= 2 or len(sizes) > 6):
            self.add('warning', 'type-scale', None, '서로 다른 글자 크기가 %d개입니다(권장 3–5).' % len(sizes))
        frame_area = self.width * self.height
        area = sum(_box(l)[2] * _box(l)[3] for l in texts + visual)
        density = min(area / frame_area, 1) if frame_area else 0
        if density < DENSITY_MIN:
            self.add('warning', 'low-density', None, '텍스트와 시각 요소가 프레임의 %d%%만 차지합니다.' % round(100 * density))
        self.metrics.update(type_sizes=[round(s, 2) for s in sizes], density=round(density, 3), visual_layers=len(visual))


def _candidates(layout):
    rows = layout.get('candidates')
    if isinstance(rows, dict):
        rows = [dict(row, id=row.get('id', key)) for key, row in rows.items()]
    if not isinstance(rows, list) or not rows:
        raise ValueError('authored native layout에 candidates가 없습니다.')
    return rows


def _variants(candidate, layout_dir):
    """control id -> visual variant, read from the annotations beside the candidate graph when present."""
    path = (candidate.get('graph') or {}).get('path')
    if not layout_dir or not isinstance(path, str):
        return {}
    try:
        notes = json.loads((Path(layout_dir) / path).with_name('annotations.json').read_text())
    except (OSError, ValueError):
        return {}
    result = {}
    for note in notes if isinstance(notes, list) else []:
        if isinstance(note, dict) and isinstance(note.get('visual_variant'), str):
            for control_id in [note.get('control_id')] + list(note.get('control_ids') or []):
                if isinstance(control_id, str):
                    result[control_id] = note['visual_variant']
    return result


def evaluate(layout, layout_dir=None, strict=False):
    if not isinstance(layout, dict) or layout.get('schema') != LAYOUT_SCHEMA:
        raise ValueError('schema %s의 authored native layout이 필요합니다.' % LAYOUT_SCHEMA)
    report = {'schema': SCHEMA, 'passed': False, 'strict': bool(strict), 'errors': [], 'warnings': [], 'metrics': {}}
    fonts = _Fonts(layout_dir)
    for candidate in _candidates(layout):
        colors = candidate.get('colors') or {}
        variants = _variants(candidate, layout_dir)
        for viewport, states in (candidate.get('state_layouts') or {}).items():
            for index, (state_id, state) in enumerate(states.items()):
                checker = _State(report, candidate, viewport, state_id, state, colors, fonts, index == 0, strict, variants)
                report['metrics']['%s/%s/%s' % (candidate['id'], viewport, state_id)] = checker.run()
    report['passed'] = not report['errors'] and not (strict and report['warnings'])
    report['summary'] = summarize(report)
    return report


def summarize(report):
    def count(items):
        result = {}
        for item in items:
            result[item['code']] = result.get(item['code'], 0) + 1
        return result
    return {'errors': len(report['errors']), 'warnings': len(report['warnings']),
            'error_codes': count(report['errors']), 'warning_codes': count(report['warnings'])}


def run(path, strict=False):
    path = Path(path)
    return evaluate(json.loads(path.read_text()), layout_dir=path.parent, strict=strict)


def manifest_layout(manifest):
    """The immutable native layout a direction review manifest pins."""
    import design_directions
    data = design_directions.validate_draft(Path(manifest), require_native_review=False)['data']
    record = data.get('native_layout') or data.get('native_target', {}).get('layout')
    if not record:
        raise ValueError('검토 매니페스트에 authored native layout이 고정되어 있지 않습니다.')
    return design_directions.current(record, Path(data['project_root']).resolve()).resolve()


def blocking_summary(report, report_path):
    codes = ', '.join('%s %d' % item for item in sorted(report['summary']['error_codes'].items()))
    return '디자인 품질 관문 오류 %d건(%s) — 고치기 전에는 검토 패키지를 만들지 않습니다. 보고서: %s' % (
        report['summary']['errors'], codes, report_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--strict', action='store_true', help='경고도 실패로 처리')
    args = parser.parse_args(argv)
    try:
        report = run(args.layout, strict=args.strict)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text, end='')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
