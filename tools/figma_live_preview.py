"""Read-only loopback comparison of native Figma measurements and the real local app."""
import json
import math
import mimetypes
import secrets
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from design_system import compile_design
from serve_ideas import snapshot_app

METRIC_PROPERTIES = {
    'padding': [('padding-' + side, 'padding' + side.title()) for side in ('top', 'right', 'bottom', 'left')],
    'border-radius': [('border-top-left-radius', 'topLeftRadius'), ('border-top-right-radius', 'topRightRadius'),
                      ('border-bottom-right-radius', 'bottomRightRadius'), ('border-bottom-left-radius', 'bottomLeftRadius')],
    'font-size': [('font-size', 'fontSize')],
}
COLOR_PROPERTIES = {'background': 'background-color', 'color': 'color', 'border-color': 'border-top-color'}
# shortcut: these semantic IDs map the review-cards example, extend when another app is admitted.
CARD_SELECTORS = {'list-search': '.search--default', 'review-card': '.review-card',
                  'review-reveal': '#reveal-button', 'review-retry': '#retry-button',
                  'review-complete': '#complete-button'}


def identity(node):
    return node.get('semantic_id') or node.get('declared_metadata', {}).get('semantic_id')


def walk(node):
    yield node
    for child in node.get('children', []):
        yield from walk(child)


def paint_color(node, field):
    paints = [paint for paint in node.get(field, []) if paint.get('visible', True)]
    if (node.get('visible') is False or node.get('opacity', 1) != 1 or len(paints) != 1
            or paints[0].get('type') != 'SOLID' or paints[0].get('blendMode', 'NORMAL') != 'NORMAL'):
        return None
    paint = paints[0]
    color = paint.get('color', {})
    values = [color.get(key) for key in ('r', 'g', 'b')] + [paint.get('opacity', 1)]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           or not 0 <= value <= 1 for value in values):
        return None
    return [round(value * 255) for value in values[:3]] + [values[3]]



def native_metric(node, field, prop):
    if not node or node.get('visible') is False or node.get('opacity', 1) != 1:
        return None, field
    unavailable = node.get('unavailable_fields', {})
    if field in unavailable:
        return None, field
    actual_field = field
    if prop == 'border-radius' and field not in node:
        actual_field = 'cornerRadius'
    if actual_field in unavailable:
        return None, actual_field
    value = node.get(actual_field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None, actual_field
    return value, actual_field


def native_binding(node, field, token, variables):
    bindings = node.get('boundVariables', {})
    reference = bindings.get(field) if isinstance(bindings, dict) else None
    if field == 'fontSize' and node.get('type') == 'TEXT' and isinstance(reference, list):
        if len(reference) != 1:
            return {'status': 'ambiguous', 'field': field}
        reference = reference[0]
    if not isinstance(reference, dict) or reference.get('type') != 'VARIABLE_ALIAS':
        return {'status': 'missing', 'field': field}
    variable_id = reference.get('id')
    matches = [variable for variable in variables if variable.get('id') == variable_id]
    binding = {'status': 'unresolved', 'field': field, 'variable_id': variable_id}
    if len(matches) == 1 and identity(matches[0]):
        binding['semantic_id'] = identity(matches[0])
        binding['status'] = 'observed' if binding['semantic_id'] == token else 'mismatch'
    return binding


def comparison(project, readback, page_id, result):
    """Expected values come from native fields, never from generated CSS/token values."""
    if not isinstance(readback, dict):
        raise ValueError('Native readback must be an object.')
    pages = [page for page in readback.get('pages', []) if page.get('id') == page_id]
    if len(pages) != 1:
        raise ValueError('Select exactly one native page from this readback.')
    design = compile_design(json.loads((project / 'design.json').read_text()))
    native = {}
    for node in walk(pages[0]):
        native.setdefault(identity(node), []).append(node)
    roots = set(result.get('changed_tokens', []))
    affected = set(roots)
    while True:
        aliases = {key for key, value in design['tokens'].items() if value.get('alias') in affected}
        if aliases <= affected:
            break
        affected.update(aliases)
    admitted_screens = set(result.get('screens', [])) if result.get('status') == 'applied' and roots else set()
    screen_ids = [screen['id'] for screen in design['screens'] if screen['id'] in admitted_screens]
    checks, unknowns = [], []
    for screen in design['screens']:
        if screen['id'] not in screen_ids:
            continue
        elements = list(screen['elements'])
        if screen['id'] == 'SCR-CARDS-REVIEW':
            elements += [dict(id='review-retry', kind='component', component='button', variant='secondary', native_component=True),
                         dict(id='review-complete', kind='component', component='button', variant='primary', native_component=True)]
        for index, element in enumerate(elements):
            if element.get('kind') != 'component':
                continue
            eid = element.get('id', f"{screen['id']}/element:{index}")
            component_id = f"component:{element['component']}/{element['variant']}"
            components = native.get(component_id, [])
            props = (components[0].get('declared_metadata', {}).get('token_properties', {})
                     if len(components) == 1 else {})
            if not props:
                unknowns.append(f'{eid}: 네이티브 컴포넌트 토큰 메타데이터가 없거나 중복됩니다')
                continue
            nodes = components if element.get('native_component') else native.get(eid, [])
            for prop, token in props.items():
                if token not in affected:
                    continue
                if prop not in COLOR_PROPERTIES and prop not in METRIC_PROPERTIES:
                    unknowns.append(f'{eid}: {prop} ({token}) 측정 범위 밖입니다')
                    continue
                node = nodes[0] if len(nodes) == 1 else None
                container = node
                if node and prop in ('color', 'font-size'):
                    labels = [child for child in node.get('children', []) if child.get('type') == 'TEXT']
                    node = labels[0] if len(labels) == 1 else None
                selector = CARD_SELECTORS.get(eid)
                if not selector and screen['id'] == 'SCR-CARDS-LIST' and element['component'] == 'card':
                    selector = '.card--default'
                if not selector:
                    unknowns.append(f'{eid}: 연결된 실제 앱 요소가 없습니다')
                    continue
                common = {'screen': screen['id'], 'element': eid, 'selector': selector, 'token': token,
                          'text': element.get('text') if screen['id'] == 'SCR-CARDS-LIST' and element['component'] == 'card' else None,
                          'text_selector': ('input' if eid == 'list-search' else '#review-question' if eid == 'review-card' else '.card-title' if screen['id'] == 'SCR-CARDS-LIST' and element['component'] == 'card' else None) if prop in ('color', 'font-size') else None}
                if prop in COLOR_PROPERTIES:
                    value = paint_color(node, 'strokes' if prop == 'border-color' else 'fills') if node else None
                    if value is None:
                        unknowns.append(f'{eid}: {prop} 네이티브 색상이 없거나 지원하지 않는 paint입니다')
                        continue
                    checks.append(dict(common, property=COLOR_PROPERTIES[prop], expected=value,
                                       native_node=nodes[0]['id'], source='native-component-paint' if element.get('native_component') else 'native-instance-paint'))
                    continue
                for css_property, field in METRIC_PROPERTIES[prop]:
                    value, actual_field = native_metric(node, field, prop)
                    if container and (container.get('visible') is False or container.get('opacity', 1) != 1):
                        value = None
                    if value is None:
                        unknowns.append(f'{eid}: {css_property} 네이티브 수치가 없거나 혼합·숨김·미지원 값입니다')
                        continue
                    bindings = node.get('boundVariables', {})
                    binding_field = field if isinstance(bindings, dict) and field in bindings else actual_field
                    binding = native_binding(node, binding_field, token, readback.get('variables', []))
                    if binding['status'] != 'observed':
                        unknowns.append(f"{eid}: {css_property} 네이티브 토큰 바인딩 {binding['status']}")
                    checks.append(dict(common, property=css_property, kind='px', expected=value,
                                       native_field=actual_field, native_node=node['id'], binding=binding,
                                       source='native-component-metric' if element.get('native_component') else 'native-instance-metric'))
    if not checks:
        unknowns.append('이번 적용에서 비교 가능한 네이티브 측정값이 없습니다.')
    return {'page_id': page_id, 'status': result.get('status', 'unknown'), 'changed_tokens': sorted(roots),
            'screens': screen_ids, 'checks': checks, 'unknowns': sorted(set(unknowns)),
            'scope': '비교 범위: 컴포넌트 색상·패딩·모서리 반경·글자 크기. 다른 토큰 종류와 전체 시각적 일치 여부는 확인하지 않습니다.'}


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.headers.get('Host') not in self.server.preview_hosts:
            self.send_error(403)
            return
        try:
            path = unquote(urlsplit(self.path).path, errors='strict')
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        if '\\' in path or '\x00' in path or any(part in ('.', '..') for part in path.split('/')):
            self.send_error(404)
            return
        with self.server.preview_lock:
            state = self.server.preview_state
            revision = str(state['revision'])
            app_prefix = '/app/revision/' + revision + '/'
            before_prefix = '/before/revision/' + revision + '/'
            if (path.startswith('/app/') and not path.startswith(app_prefix)) or (path.startswith('/before/') and not path.startswith(before_prefix)):
                self.send_error(409, 'App revision changed; reload comparison')
                return
            if path == '/revision.json':
                data, content_type = json.dumps(state, ensure_ascii=False).encode(), 'application/json'
            elif path == '/':
                data, content_type = self.server.preview_html, 'text/html; charset=utf-8'
            elif path.startswith(('/app/', '/before/')):
                # The before snapshot has its own prefix, so a real app file under app/before/ stays reachable.
                if path.startswith(before_prefix):
                    data = self.server.preview_before_files.get('/' + path[len(before_prefix):])
                else:
                    data = self.server.preview_files.get('/' + path[len(app_prefix):])
                content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            else:
                data, content_type = None, None
        if data is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)


def start_preview(project, port=0):
    project = Path(project).absolute()
    files = snapshot_app(project)
    server = ThreadingHTTPServer(('127.0.0.1', port), PreviewHandler)
    server.daemon_threads = True
    server.project = project
    server.host = '127.0.0.1:' + str(server.server_port)
    server.preview_hosts = {server.host, 'localhost:' + str(server.server_port)}
    server.preview_epoch = secrets.token_hex(16)
    server.preview_lock = threading.Lock()
    server.preview_files = files
    server.preview_before_files = {}
    server.preview_html = Path(__file__).with_suffix('.html').read_bytes()
    server.preview_state = {'epoch': server.preview_epoch, 'revision': 0, 'before_available': False, 'before_checks': [], 'before_unknowns': ['적용 전 스냅샷이 제공되지 않았습니다.'], 'checks': [], 'screens': [], 'unknowns': ['페어링된 Figma 읽기 결과를 기다리고 있습니다.']}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def update_preview(server, readback, page_id, result, previous=None):
    state = comparison(server.project, readback, page_id, result)
    files = snapshot_app(server.project)
    before_files = {}
    state.update(before_available=False, before_checks=[], before_unknowns=['적용 전 스냅샷이 제공되지 않았습니다.'])
    if previous is not None:
        previous_readback, captured_files = previous
        if (not isinstance(captured_files, dict) or '/index.html' not in captured_files
                or any(not isinstance(path, str) or not path.startswith('/')
                       or any(part in ('', '.', '..') for part in path[1:].split('/'))
                       or '\\' in path or '\x00' in path or not isinstance(content, bytes)
                       for path, content in captured_files.items())):
            raise ValueError('Before app must be a regular snapshot_app file mapping.')
        try:
            before = comparison(server.project, previous_readback, page_id, result)
        except ValueError:
            state['before_unknowns'] = ['적용 전 네이티브 페이지를 확인할 수 없습니다.']
        else:
            before_files = dict(captured_files)
            state.update(before_available=True, before_checks=before['checks'], before_unknowns=before['unknowns'])
    # Asset URLs include the revision so a racing update never mixes styles across revisions.
    with server.preview_lock:
        state['epoch'] = server.preview_epoch
        state['revision'] = server.preview_state['revision'] + 1
        server.preview_files = files
        server.preview_before_files = before_files
        server.preview_state = state
    return state
