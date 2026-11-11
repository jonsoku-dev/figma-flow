#!/usr/bin/env python3
"""Route catalog and evidence graphs for the regression program.

The catalog is the route inventory these exploratory apps share with their
graphs. It is not a product SSOT, a release, or proof that Figma ran.
"""
import json
from pathlib import Path

SEED = 20261111
ROOT = Path(__file__).resolve().parent
DESIGN_COMPONENTS = ['Button', 'Field', 'Table', 'Dialog', 'Tabs', 'Nav']
LONG_TEXT = {
    'ko': '한국어 제목 ' + ('가' * 40),
    'en': 'English label ' * 8,
    'ja': '日本語のボタン' * 6,
}


def _route(screen_id, path, title, label, targets, purpose, access=None, remote=None, region='table'):
    route = {
        'id': screen_id,
        'path': path,
        'title': title,
        'purpose': purpose,
        'region': region,
        'primary': {'id': 'ACT-' + screen_id.removeprefix('SCR-'), 'label': label, 'to': targets},
    }
    if access:
        route['access'] = access
    if remote:
        route['primary']['remote'] = remote
    return route


def _apps():
    studio = {'reader': 'denied', 'author': 'allowed', 'editor': 'allowed'}
    atlas = [
        _route('SCR-ATLAS-01', '/sign-in', 'Atlas 로그인', '작업 공간 열기', ['SCR-ATLAS-02'], '모의 역할로 작업 공간에 들어간다.', region='form'),
        _route('SCR-ATLAS-02', '/workspaces', '작업 공간 선택', 'Northwind 열기', ['SCR-ATLAS-03'], 'Northwind 작업 공간을 고른다.', region='cards'),
        _route('SCR-ATLAS-03', '/dashboard', '오늘의 검토', '승인 대기 열기', ['SCR-ATLAS-08'], '오늘 처리할 승인과 할 일을 밀도 높게 보여 준다.', region='table'),
        _route('SCR-ATLAS-04', '/projects', '프로젝트 목록', '프로젝트 열기', ['SCR-ATLAS-05'], '프로젝트 표를 정렬하고 좁힌다.', region='table'),
        _route('SCR-ATLAS-05', '/projects/:projectId', '프로젝트 상세', '보드로 이동', ['SCR-ATLAS-06'], '프로젝트의 할 일 수를 보여 준다.', region='table'),
        _route('SCR-ATLAS-06', '/projects/:projectId/board', '작업 보드', '할 일 열기', ['SCR-ATLAS-07'], '칸반이 아니라 상태 열로 할 일을 연다.', region='board'),
        _route('SCR-ATLAS-07', '/tasks/:taskId', '할 일 상세', '저장', ['STATE-ATLAS-07-SAVED', 'STATE-ATLAS-07-ERROR'], '저장 실패 뒤에도 초안을 유지한다.', remote='/api/atlas/tasks/save', region='form'),
        _route('SCR-ATLAS-08', '/approvals', '승인 목록', '요청 열기', ['SCR-ATLAS-09'], '대기 중인 승인 요청을 보여 준다.', region='table'),
        _route('SCR-ATLAS-09', '/approvals/:approvalId', '승인 상세', '승인', ['SCR-ATLAS-08'], '검토자가 요청을 승인하고 구성원은 읽기 전용이다.', region='form'),
        _route('SCR-ATLAS-10', '/members', '구성원', '초대', ['SCR-ATLAS-11'], '구성원과 현재 역할을 보여 준다.', region='table'),
        _route('SCR-ATLAS-11', '/members/invite', '구성원 초대', '초대 보내기', ['SCR-ATLAS-10'], '초대 대상을 입력한다. 메일은 보내지 않는다.', region='form'),
        _route('SCR-ATLAS-12', '/roles', '역할', '역할 열기', ['SCR-ATLAS-13'], '관리자만 역할 목록을 연다.', access={'member': 'denied', 'reviewer': 'denied', 'admin': 'allowed'}, region='table'),
        _route('SCR-ATLAS-13', '/roles/:roleId', '역할 상세', '역할 저장', ['SCR-ATLAS-12'], '관리자가 구성원의 역할을 바꾼다.', access={'member': 'denied', 'reviewer': 'denied', 'admin': 'allowed'}, region='form'),
        _route('SCR-ATLAS-14', '/settings', '작업 공간 설정', '표시 저장', ['STATE-ATLAS-14-SAVED'], '표시 밀도를 저장한다.', region='form'),
    ]
    morrow = [
        _route('SCR-MORROW-01', '/', '이번 주의 식탁', '컬렉션 보기', ['SCR-MORROW-02'], '주간 식탁 이야기를 연다.', region='prose'),
        _route('SCR-MORROW-02', '/collections/:slug', '주간 컬렉션', '상품 보기', ['SCR-MORROW-04'], '컬렉션 안의 상품으로 이동한다.', region='cards'),
        _route('SCR-MORROW-03', '/search', '상품 찾기', '상품 보기', ['SCR-MORROW-04'], '이름과 재료로 상품을 찾는다.', region='cards'),
        _route('SCR-MORROW-04', '/products/:productId', '식탁 상품', '장바구니에 담기', ['SCR-MORROW-07'], '가격과 재고를 보여 주고 담는다.', region='prose'),
        _route('SCR-MORROW-05', '/compare', '나란히 비교', '장바구니로 이동', ['SCR-MORROW-07'], '두 상품의 가격과 재고를 나란히 둔다.', region='table'),
        _route('SCR-MORROW-06', '/saved', '보관한 상품', '상품 보기', ['SCR-MORROW-04'], '새로고침 뒤에도 보관한 상품을 유지한다.', region='cards'),
        _route('SCR-MORROW-07', '/cart', '장바구니', '주문 시작', ['SCR-MORROW-08'], '담은 상품과 수량을 확인한다.', region='table'),
        _route('SCR-MORROW-08', '/checkout/contact', '주문자', '배송으로 이동', ['SCR-MORROW-09'], '주문자 이름을 받는다. 결제는 없다.', region='form'),
        _route('SCR-MORROW-09', '/checkout/delivery', '배송', '확인으로 이동', ['SCR-MORROW-10'], '배송 메모를 받고 이전 단계로 돌아갈 수 있다.', region='form'),
        _route('SCR-MORROW-10', '/checkout/review', '주문 확인', '주문 접수', ['SCR-MORROW-11'], '재고나 가격이 바뀌면 주문을 늘리지 않는다.', remote='/api/morrow/orders', region='form'),
        _route('SCR-MORROW-11', '/orders/complete/:orderId', '주문 완료', '주문 상세', ['SCR-MORROW-13'], '한 번 접수된 주문 번호를 보여 준다.', region='prose'),
        _route('SCR-MORROW-12', '/orders', '주문 목록', '주문 상세', ['SCR-MORROW-13'], '접수한 주문을 다시 연다.', region='table'),
        _route('SCR-MORROW-13', '/orders/:orderId', '주문 상세', '반품 신청', ['SCR-MORROW-14'], '주문 내용을 확인하고 반품으로 이동한다.', region='prose'),
        _route('SCR-MORROW-14', '/returns/new/:orderId', '반품 신청', '반품 제출', ['STATE-MORROW-14-KEPT', 'STATE-MORROW-14-DONE'], '반품 실패 뒤 입력한 사유를 유지한다.', remote='/api/morrow/returns', region='form'),
    ]
    paper = [
        _route('SCR-PAPER-01', '/', '읽는 사람의 첫 화면', '글 읽기', ['SCR-PAPER-03'], '발행된 글의 첫 문단만 보여 준다.', region='prose'),
        _route('SCR-PAPER-02', '/search', '글 찾기', '글 읽기', ['SCR-PAPER-03'], '제목과 본문에서 글을 찾는다.', region='prose'),
        _route('SCR-PAPER-03', '/articles/:slug', '글', '보관', ['SCR-PAPER-05'], '긴 글을 좁은 폭으로 읽는다.', region='prose'),
        _route('SCR-PAPER-04', '/collections/:collectionId', '책상 모음', '글 읽기', ['SCR-PAPER-03'], '모음에 들어 있는 글을 연다.', region='prose'),
        _route('SCR-PAPER-05', '/saved', '보관한 글', '글 읽기', ['SCR-PAPER-03'], '보관한 글을 다시 연다.', region='prose'),
        _route('SCR-PAPER-06', '/studio', '작업실', '초고 목록', ['SCR-PAPER-07'], '작성자와 편집자의 작업실이다.', access=studio, region='table'),
        _route('SCR-PAPER-07', '/studio/articles', '초고 목록', '새 글', ['SCR-PAPER-08'], '초고와 검토 상태를 보여 준다.', access=studio, region='table'),
        _route('SCR-PAPER-08', '/studio/articles/new', '새 글', '편집 시작', ['SCR-PAPER-09'], '새 초고를 만든다.', access=studio, region='form'),
        _route('SCR-PAPER-09', '/studio/articles/:articleId/edit', '글 편집', '검토 요청', ['SCR-PAPER-10'], '자동 저장이 실패해도 본문을 유지한다.', remote='/api/paper/drafts', access=studio, region='form'),
        _route('SCR-PAPER-10', '/studio/reviews', '검토 목록', '검토 열기', ['SCR-PAPER-11'], '검토 대기 글을 연다.', access={'reader': 'denied', 'author': 'denied', 'editor': 'allowed'}, region='table'),
        _route('SCR-PAPER-11', '/studio/reviews/:reviewId', '검토 상세', '가상 발행', ['SCR-PAPER-01', 'SCR-PAPER-12'], '편집자가 반려하거나 가상 발행한다. 공개 발행은 없다.', remote='/api/paper/publish', access={'reader': 'denied', 'author': 'readonly', 'editor': 'allowed'}, region='form'),
        _route('SCR-PAPER-12', '/studio/calendar', '발행 달력', '첫 화면으로', ['SCR-PAPER-01'], '가상 발행된 글만 달력에 올린다.', access=studio, region='table'),
    ]
    return {
        'atlas': {
            'id': 'atlas',
            'title': 'Atlas Workspace',
            'mount': '/atlas',
            'primaryInput': 'html',
            'roles': ['member', 'reviewer', 'admin'],
            'purpose': '업무·승인 관리',
            'html': {'title': '검토 대기 열두 건', 'gap': '12px'},
            'url': {'principle': 'atlas-check-answers', 'target': 'SCR-ATLAS-09'},
            'routes': atlas,
            'flows': [
                {'id': 'TC-F01', 'title': '할 일 저장과 복구', 'screens': ['SCR-ATLAS-04', 'SCR-ATLAS-05', 'SCR-ATLAS-06', 'SCR-ATLAS-07']},
                {'id': 'TC-F02', 'title': '승인과 역할 제한', 'screens': ['SCR-ATLAS-08', 'SCR-ATLAS-09', 'SCR-ATLAS-13']},
            ],
            'samples': {'projectId': 'north', 'taskId': 'task-0001', 'approvalId': 'apr-1', 'roleId': 'reviewer'},
        },
        'morrow': {
            'id': 'morrow',
            'title': 'Morrow Market',
            'mount': '/morrow',
            'primaryInput': 'url',
            'roles': ['guest', 'customer'],
            'purpose': '커머스·주문·반품',
            'html': {'title': '주간 식탁 여섯 가지', 'gap': '20px'},
            'url': {'principle': 'morrow-check-answers', 'target': 'SCR-MORROW-10'},
            'routes': morrow,
            'flows': [
                {'id': 'TC-F03', 'title': '주문 단계와 재고 충돌', 'screens': ['SCR-MORROW-04', 'SCR-MORROW-07', 'SCR-MORROW-08', 'SCR-MORROW-09', 'SCR-MORROW-10', 'SCR-MORROW-11']},
                {'id': 'TC-F04', 'title': '저장 목록과 반품', 'screens': ['SCR-MORROW-06', 'SCR-MORROW-13', 'SCR-MORROW-14']},
            ],
            'samples': {'slug': 'week', 'productId': 'linen', 'orderId': 'order-1'},
        },
        'paper': {
            'id': 'paper',
            'title': 'Paper Room',
            'mount': '/paper',
            'primaryInput': 'design-system',
            'roles': ['reader', 'author', 'editor'],
            'purpose': '독자·작성자·편집자 CMS',
            'html': {'title': '긴 초고의 첫 문단', 'gap': '28px'},
            'url': {'principle': 'paper-reading-measure', 'target': 'SCR-PAPER-03'},
            'routes': paper,
            'flows': [
                {'id': 'TC-F05', 'title': '작성·자동 저장·검토', 'screens': ['SCR-PAPER-08', 'SCR-PAPER-09', 'SCR-PAPER-10']},
                {'id': 'TC-F06', 'title': '역할별 검토·발행', 'screens': ['SCR-PAPER-11', 'SCR-PAPER-01', 'SCR-PAPER-12']},
            ],
            'samples': {'slug': 'desk-lamp', 'articleId': 'draft-1', 'collectionId': 'desk', 'reviewId': 'draft-1'},
        },
    }


APPS = _apps()


def catalog_document():
    return {
        'schema': 'figma-flow-regression-catalog-v1',
        'seed': SEED,
        'scope': 'exploratory',
        'channel': 'local-file-fixture',
        'longText': LONG_TEXT,
        'designSystem': {
            'importPath': '/design-system/runtime.js',
            'components': DESIGN_COMPONENTS,
            'token': '#0e6b4f',
            'package': '@figma-flow/regression-design-system@0.1.0',
        },
        'apps': APPS,
    }


def _node(node_id, node_type, title, status, source, detail=None, **extra):
    node = {'id': node_id, 'type': node_type, 'title': title, 'status': status, 'source': source}
    if detail:
        node['detail'] = detail
    node.update(extra)
    return node


def build_graph(app_id):
    app = APPS[app_id]
    key = app_id.upper()
    nodes, edges = [], []
    nodes.append(_node('CODE-' + key, 'code', app['title'] + ' 규칙', 'observed', 'app/rules.js', '로컬 모델. Figma 실행 증거가 아니다.'))
    nodes.append(_node('TEST-' + key, 'test', app['title'] + ' 모델 검사', 'planned', 'tests/test_regression_program_apps.cjs', 'Node 모델 검사. 브라우저·Figma 합격이 아니다.'))
    extra_states = {
        'STATE-ATLAS-07-SAVED': '할 일을 저장함',
        'STATE-ATLAS-07-ERROR': '할 일 저장 실패',
        'STATE-ATLAS-14-SAVED': '표시를 저장함',
        'STATE-MORROW-14-KEPT': '반품 입력을 유지함',
        'STATE-MORROW-14-DONE': '반품을 접수함',
    }
    for route in app['routes']:
        stem = route['id'].removeprefix('SCR-')
        requirement = 'REQ-' + stem
        acceptance = 'AC-' + stem
        state = 'STATE-' + stem
        nodes.append(_node(requirement, 'requirement', route['purpose'], 'observed', 'brief.md', route['path']))
        nodes.append(_node(route['id'], 'screen', route['title'], 'observed', 'app/rules.js', route['path']))
        nodes.append(_node(state, 'state', route['title'] + ' 내용', 'observed', 'app/rules.js'))
        nodes.append(_node(acceptance, 'acceptance', route['title'] + ' 경로 인수', 'planned', 'screen-spec.md', 'TC-W01'))
        for suffix, title in (('-LOADING', '로딩'), ('-EMPTY', '빈 결과'), ('-ERROR', '오류')):
            if route['region'] in {'table', 'cards', 'prose'}:
                nodes.append(_node(state + suffix, 'state', route['title'] + ' ' + title, 'observed', 'app/rules.js'))
                edges.append({'from': route['id'], 'to': state + suffix, 'type': 'has state'})
        action = dict(route['primary'])
        nodes.append(_node(action['id'], 'action', action['label'], 'observed', 'app/rules.js', route['path'], source_screen=route['id'], target_ids=list(action['to'])))
        edges.extend([
            {'from': requirement, 'to': route['id'], 'type': 'appears on'},
            {'from': requirement, 'to': acceptance, 'type': 'accepted by'},
            {'from': route['id'], 'to': state, 'type': 'has state'},
            {'from': route['id'], 'to': action['id'], 'type': 'triggers'},
            {'from': acceptance, 'to': 'TEST-' + key, 'type': 'checked by'},
            {'from': route['id'], 'to': 'CODE-' + key, 'type': 'implemented by'},
        ])
        for target in action['to']:
            if target in extra_states and not any(node['id'] == target for node in nodes):
                nodes.append(_node(target, 'state', extra_states[target], 'observed', 'app/rules.js'))
            edges.append({'from': action['id'], 'to': target, 'type': 'navigates to'})
    for flow in app['flows']:
        flow_requirement = 'REQ-' + flow['id']
        flow_acceptance = 'AC-' + flow['id']
        nodes.append(_node(flow_requirement, 'requirement', flow['title'], 'observed', 'brief.md', flow['id']))
        nodes.append(_node(flow_acceptance, 'acceptance', flow['title'] + ' 인수', 'planned', 'screen-spec.md', flow['id']))
        edges.append({'from': flow_requirement, 'to': flow_acceptance, 'type': 'accepted by'})
        edges.append({'from': flow_acceptance, 'to': 'TEST-' + key, 'type': 'checked by'})
        for screen_id in flow['screens']:
            edges.append({'from': flow_requirement, 'to': screen_id, 'type': 'appears on'})
    for target, title in extra_states.items():
        if target.startswith('STATE-' + key) and not any(node['id'] == target for node in nodes):
            nodes.append(_node(target, 'state', title, 'observed', 'app/rules.js'))
    references = {
        'atlas': ('REF-ATLAS-GOVUK', 'REQ-ATLAS-09', 'https://design-system.service.gov.uk/patterns/check-answers/'),
        'morrow': ('REF-MORROW-GOVUK', 'REQ-MORROW-10', 'https://design-system.service.gov.uk/patterns/check-answers/'),
        'paper': ('REF-PAPER-GOVUK', 'REQ-PAPER-03', 'https://design-system.service.gov.uk/patterns/check-answers/'),
    }
    reference_id, requirement_id, url = references[app_id]
    nodes.append(_node(reference_id, 'reference', '답변 확인 패턴 메모', 'observed', url, '텍스트 수집이며 브라우저 렌더가 아니다.'))
    edges.append({'from': reference_id, 'to': requirement_id, 'type': 'informs'})
    return {'version': 1, 'nodes': nodes, 'edges': edges}


def screen_spec(app_id):
    app = APPS[app_id]
    lines = [
        '# ' + app['title'] + ' 화면 명세',
        '',
        '이 문서는 카탈로그의 화면 ID를 풀어 쓴 것이다. 그래프가 관계의 기준이고, 이 파일은 Figma 증거가 아니다.',
        '',
    ]
    for route in app['routes']:
        stem = route['id'].removeprefix('SCR-')
        lines.extend([
            '## ' + route['id'] + ' ' + route['title'],
            '',
            '- 경로: `' + route['path'] + '`',
            '- 요구: `REQ-' + stem + '` ' + route['purpose'],
            '- 주 행동: `' + route['primary']['id'] + '` ' + route['primary']['label'],
            '- 인수: `AC-' + stem + '` (TC-W01, 모델 검사 전 상태는 planned)',
            '- 구현: `app/rules.js`',
            '',
        ])
    lines.append('## 핵심 흐름')
    lines.append('')
    for flow in app['flows']:
        lines.append('- `' + flow['id'] + '` ' + flow['title'] + ': ' + ', '.join(flow['screens']))
    lines.append('')
    return '\n'.join(lines)


def bindings(app_id):
    key = app_id.upper()
    return {
        'version': 1,
        'authorities': {'intent': 'brief.md', 'implementation': 'app/rules.js'},
        'dependency_edge_types': ['depends-on'],
        'evidence': {'CODE-' + key: ['app/rules.js']},
    }


def write_outputs():
    document = catalog_document()
    (ROOT / 'catalog.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for app_id in APPS:
        folder = ROOT / app_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'graph.json').write_text(json.dumps(build_graph(app_id), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (folder / 'screen-spec.md').write_text(screen_spec(app_id), encoding='utf-8')
        (folder / 'bindings.json').write_text(json.dumps(bindings(app_id), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    write_outputs()
