#!/usr/bin/env python3
"""Project authoring adapter. Only supplied real SSR/DOM observations become layers."""
import argparse
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent
STATIC_ROOT = Path(os.environ.get("LH_STATIC_ROOT", str(APP / "staticfiles")))
STATES = [
    ('publichome', '수업 둘러보기', 'booking/session_list.html', [1,10], '/'),
    ('login', '로그인', 'registration/login.html', [2,10], '/accounts/login/'),
    ('signup', '회원가입', 'registration/signup.html', [2,10], '/accounts/signup/'),
    ('memberhome', '회원 수업 둘러보기', 'booking/session_list.html', [1,2,10], '/'),
    ('sessionavailable', '수업과 신청 인원', 'booking/session_detail.html', [1,3,4,8,10], None),
    ('review', '신청 내용 확인', 'booking/reserve_review.html', [3,4,8,10], None),
    ('confirmed', '예약 확정', 'booking/booking_detail.html', [3,5,6,7,10], None),
    ('waitlisted', '대기 등록', 'booking/booking_detail.html', [4,5,6,10], None),
    ('mybookings', '나의 예약', 'booking/my_bookings.html', [2,5,10], '/bookings/'),
    ('cancelconfirm', '취소 확인', 'booking/cancel.html', [6,8,10], None),
    ('cancelled', '취소된 예약', 'booking/booking_detail.html', [5,6,10], None),
    ('reschedule', '회차 변경', 'booking/reschedule.html', [7,8,10], None),
    ('conflict', '변경 충돌과 복구', 'booking/conflict.html', [7,8,10], None),
    ('notifications', '나의 알림', 'booking/notifications.html', [2,9,10], '/notifications/'),
    ('staffdashboard', '운영 현황', 'staff/dashboard.html', [2,9,10], '/staff/'),
    ('staffsessions', '운영 일정', 'staff/session_list.html', [2,9,10], '/staff/sessions/'),
    ('staffcreate', '회차 등록', 'staff/session_form.html', [2,8,9,10], '/staff/sessions/new/'),
    ('staffroster', '신청 명단', 'staff/session_detail.html', [2,4,9,10], None),
    ('staffedit', '회차 편집', 'staff/session_form.html', [2,8,9,10], None),
    ('staffaudit', '변경 기록', 'staff/audit.html', [2,9,10], '/staff/audit/'),
    ('403', '접근 권한 안내', '403.html', [2,10], None),
    ('404', '찾을 수 없는 화면', '404.html', [2,10], None),
]
REQS = [
    ('실제 수업·회차·공간·정원·가격 탐색', 'test_expired_session_detail_disables_reservation'),
    ('Django 인증과 소유자·운영자 권한', 'test_owner_and_staff_authorization_and_method_guards'),
    ('인원·총액 검토와 원자적 신청', 'test_final_seat_concurrent_confirmed_and_waitlisted'),
    ('명시적 대기 동의와 엄격한 FIFO 승급', 'test_fifo_does_not_skip_larger_group_with_free_seat'),
    ('자기 예약 상태와 예약 당시 단가 조회', 'test_reschedule_preserves_original_quote_and_discloses_target_policy'),
    ('정책 기한과 명시적 원자적 취소', 'test_idempotent_cancel_promotes_and_notifies_once'),
    ('실패 시 원래 예약을 보존하는 회차 변경', 'test_failed_reschedule_preserves_original_queue_audit_notifications'),
    ('revision·멱등·DB 제약과 충돌 복구', 'test_view_idempotency_reuse_and_stale_target_are_409'),
    ('회차·명단·실제 집계·알림·불변 감사', 'test_dashboard_uses_database_totals_and_admin_cannot_mutate'),
    ('실제 반응형 웹과 편집 가능한 Figma 전달', None),
]
PLATFORM = {'web':'Django 세션·CSRF·폼과 PostgreSQL 트랜잭션을 실제 실행한다.', 'figma':'관측한 시각 상태와 연결만 표시한다. 인증·비밀번호·폼 검증·SQL·좌석 확보·발송을 실행하지 않는다.'}

SCREEN_MEANING={
 'publichome':('공개 수업의 실제 일정·공간·인원·가격을 찾아 신청할 회차를 고른다.','수업 목록 → 회차 상세 → 로그인 또는 신청 검토. 빈 일정은 준비 중 안내를 읽는다.'),
 'login':('기존 회원이 Django 인증으로 자신의 예약과 알림에 접근한다.','계정과 암호 입력 → 서버 인증 → 원래 목적지 또는 수업 목록. 오류는 입력과 함께 표시한다.'),
 'signup':('권한을 스스로 부여할 수 없는 일반 회원 계정을 만든다.','회원명과 암호 정책 확인 → 서버 가입 → 회원 수업 목록. 중복·약한 암호는 서버 오류로 복구한다.'),
 'memberhome':('로그인한 회원이 현재 예약 가능한 실제 회차를 비교한다.','수업과 잔여석 확인 → 회차 상세. 나의 예약·알림으로 직접 이동할 수 있다.'),
 'sessionavailable':('실제 수업 시간·공간·정책·잔여석을 확인하고 참가 인원과 대기 동의를 정한다.','회차 정보 → 인원1~8명과 선택적 대기 동의 → 서버 검토. 비활성·지난 회차는 신청할 수 없다.'),
 'review':('서버가 검증한 인원과 현장 결제 총액을 최종 신청 전에 확인한다.','회차·인원·총액 확인 → 명시적 최종 신청 또는 다시 선택. 서버가 확정 또는 대기 상태를 결정한다.'),
 'confirmed':('실제 확정 예약의 일정·인원·예약 당시 금액과 관리 가능 여부를 확인한다.','확정 상세 → 나의 예약, 기한 내 취소 또는 같은 강좌의 다른 회차로 변경.'),
 'waitlisted':('좌석 확보와 구분되는 실제 대기 상태를 확인한다.','대기 상세 → 알림과 상세 재조회. FIFO 첫 그룹이 들어갈 수 있을 때만 서버가 승급한다.'),
 'mybookings':('현재 회원이 소유한 예약만 상태와 함께 다시 조회한다.','자기 예약 목록 → 공개 UUID 상세. 다른 회원의 UUID는404로 보호한다.'),
 'cancelconfirm':('예약을 되돌릴 수 없는 취소 전에 일정과 정책을 재확인한다.','현재 예약 확인 → 예약 유지 또는 명시적 취소. 취소는 좌석·대기열·감사·알림과 함께 기록한다.'),
 'cancelled':('취소된 실제 예약의 상태와 과거 금액을 다시 읽는다.','취소 상태 확인 → 자기 예약 또는 새 수업. 취소된 예약을 다시 활성화하지 않는다.'),
 'reschedule':('같은 강좌의 다른 회차와 대상 정책을 비교해 예약을 원자적으로 이동한다.','현재 예약 → 대상 회차 선택 → 변경. 목적지 확보 실패 시 기존 예약·대기열·감사를 보존한다.'),
 'conflict':('서버가 거절한 중복 내용·정원·revision 충돌을 이해하고 최신 상태로 복구한다.','실제 오류 메시지 확인 → 서버가 생성한 recovery_url로 GET 이동. 같은 POST를 다시 보내는 버튼은 없다.'),
 'notifications':('현재 회원의 실제 예약 알림만 읽고 개별 알림을 읽음 처리한다.','자기 알림 목록 → 관련 예약 또는 개별 읽음 POST. 외부 메일 발송 기능으로 표시하지 않는다.'),
 'staffdashboard':('운영자가 같은 DB의 예정 수업·정원·확정 인원·대기 인원을 집계한다.','실제 집계와 최근7일 신청 생성 건수 → 예정 명단 또는 새 일정. 취소 후에도 생성 건수에 포함한다.'),
 'staffsessions':('운영 권한으로 실제 회차의 시간·상태·인원을 관리한다.','전체 일정 → 회차 명단 또는 새 일정 등록. 표의 정보는 서버 페이지네이션으로 나눈다.'),
 'staffcreate':('운영자가 공간 정원과 중복 시간 제약을 지키는 실제 회차를 등록한다.','서버 SessionForm 입력 → 저장 → 회차 명단. 같은 Room의 겹치는 활성 시간은 DB가 거절한다.'),
 'staffroster':('운영자가 확정·대기 명단을 분리해 읽고 사유를 남겨 회차를 취소한다.','실제 회원명·인원·금액·번호 확인 → 회차 편집 또는 사유 필수 취소. 명단과 대기열은 별도 페이지로 나눈다.'),
 'staffedit':('운영자가 예약 이력이 있는 회차의 불변 조건과 새 가격의 적용 범위를 지켜 편집한다.','현재 조건 확인 → 허용된 필드 수정 → revision 검증 저장. 기존 예약의 단가는 바꾸지 않는다.'),
 'staffaudit':('변경 주체와 실제 before/after 기록을 읽기 전용으로 추적한다.','서버 감사 페이지 → 실제 action·시점·변경 사실. 수정 컨트롤은 제공하지 않는다.'),
 '403':('인증된 사용자가 운영 권한이 없음을 이해하고 공개 수업으로 복구한다.','접근 권한 안내 → 수업 목록. 권한 상승이나 운영 데이터 노출은 하지 않는다.'),
 '404':('없는 리소스 또는 소유하지 않은 예약을 노출하지 않고 수업 목록으로 복구한다.','찾을 수 없는 화면 안내 → 수업 목록. 리소스의 다른 소유자를 알려 주지 않는다.'),
}
WEB_BEHAVIOR={
 'logout':'웹은 CSRF POST로 Django 세션을 종료한다.',
 'login-submit':'웹은 서버 인증·시도 제한을 적용하고 성공 후 원래 목적지로 이동한다.',
 'signup-submit':'웹은 회원명·암호 정책을 검증하고 일반 회원만 생성한다.',
 'reserve-preview':'웹은 인원·회차 revision·이용 가능 여부를 검증한 검토 응답을 표시한다. 좌석은 아직 확보하지 않는다.',
 'reserve':'웹은 멱등 키와 회차 조건을 검증하고 한 트랜잭션에서 확정 또는 명시적 동의가 있는 대기 등록을 결정한다.',
 'confirm-cancel':'웹은 소유자·정책 기한·예약 revision을 검증하고 취소·FIFO 승급·감사·알림을 같은 트랜잭션으로 기록한다.',
 'confirm-reschedule':'웹은 같은 강좌의 대상 revision과 좌석을 검증하고 목적지를 확보한 뒤 원래 좌석을 해제한다. 실패 시 원래 예약을 보존한다.',
 'notification-read':'웹은 자신의 알림만 개별 멱등 키로 읽음 처리한다.',
 'session-save':'웹은 운영 권한·폼·revision·공간 시간 중복과 과거 예약 조건을 검증해 회차를 저장한다.',
 'session-cancel':'웹은 운영 권한·사유·revision을 확인하고 회차 취소와 신청자 알림을 함께 기록한다.',
 'browse-classes':'웹은 현재 문서의 실제 수업 일정 구역으로 이동한다.',
}


def write_json(path, value):
    content=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if not path.is_file() or path.read_text()!=content:path.write_text(content,encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(value):
    return re.sub(r'[^A-Za-z0-9_-]', '-', value)


class GalleryParser(HTMLParser):
    def __init__(self, state):
        super().__init__(convert_charrefs=False)
        self.state, self.depth, self.output, self.counter = state, 0, [], {}

    def handle_starttag(self, tag, attrs):
        if tag == 'body':
            self.depth = 1
            return
        if not self.depth:
            return
        attrs = dict(attrs)
        key = attrs.get('data-native-key')
        if key:
            base = self.state + '-' + safe(key)
            count = self.counter.get(base, 0) + 1
            self.counter[base] = count
            attrs['id'] = base if count == 1 else base + '-occurrence-' + str(count)
        elif attrs.get('id'):
            attrs['id'] = self.state + '-' + attrs['id']
        for name in ('href','for','aria-labelledby','aria-describedby'):
            if name not in attrs:
                continue
            val = attrs[name]
            if name == 'href':
                if val.startswith('#'):
                    attrs[name] = '#' + self.state + '-' + val[1:]
            else:
                attrs[name] = ' '.join(self.state + '-' + part for part in val.split())
        for name in ('src','href'):
            val = attrs.get(name, '')
            if val.startswith('/static/littlehands/'):
                attrs[name] = '../source_assets/littlehands/' + val.removeprefix('/static/littlehands/')
        if tag == 'form':
            attrs['inert'] = None
            attrs.pop('action',None)
        if tag == 'button':
            attrs['type'] = 'button'
        text = '<' + tag + ''.join(' ' + k + ('="' + html.escape(v, quote=True) + '"' if v is not None else '') for k,v in attrs.items()) + '>'
        self.output.append(text)

    def handle_endtag(self, tag):
        if tag == 'body':
            self.depth = 0
        elif self.depth:
            self.output.append('</' + tag + '>')

    def handle_data(self, data):
        if self.depth:
            self.output.append(data)

    def handle_entityref(self, name):
        if self.depth:
            self.output.append('&' + name + ';')

    def handle_charref(self, name):
        if self.depth:
            self.output.append('&#' + name + ';')


def color(value, palette, fallback=None):
    if value in ('transparent','rgba(0, 0, 0, 0)','none',None):
        return fallback
    if re.fullmatch(r'#[0-9a-fA-F]{6}',value):
        hex_value = value.lower()
    else:
        match = re.fullmatch(r'rgba?\(([^)]+)\)',value)
        if not match:
            raise ValueError('Unsupported measured color ' + str(value))
        values = [float(v.strip()) for v in match[1].split(',')]
        if len(values) == 4 and values[3] != 1:
            if values[3] == 0:
                return fallback
            raise ValueError('Translucent CSS paint needs explicit authoring: ' + value)
        hex_value = '#' + ''.join(f'{round(v):02x}' for v in values[:3])
    for key, val in palette.items():
        if val.lower() == hex_value:
            return key
    key = 'css-' + hex_value[1:]
    palette[key] = hex_value
    return key


def restore_transport_aliases(data, path):
    prior={}; resolutions=[]
    for text in data['texts']:
        style=text.get('style')
        if style=='[Circular]':
            if text['selector'] not in prior:
                raise ValueError('Unresolvable transport style alias: '+text['id'])
            original=prior[text['selector']]
            text['style']=json.loads(json.dumps(original['style']))
            resolutions.append({'key':text['id'],'actual_style_source':original['id'],'selector':text['selector'],'capture':path.name,'reason':'CUA transport serialized a repeated style object as [Circular]; exact same measured DOM selector, no inferred style.'})
        elif isinstance(style,dict):prior[text['selector']]=text
        else:raise ValueError('Unsupported actual text style representation: '+text['id'])
    data['_transport_alias_resolutions']=resolutions


def copy_static(route):
    if not route.startswith('/static/') or '..' in Path(route).parts:
        raise ValueError('Owned static route required: '+route)
    relative=Path(route.removeprefix('/static/'))
    source=STATIC_ROOT/relative
    if not source.is_file():
        canonical=APP/'static'/relative
        match=re.fullmatch(r'(.+)\.([0-9a-f]{12})\.([^.]+)',relative.name)
        if not canonical.is_file() and match:
            canonical=canonical.with_name(match[1]+'.'+match[3])
            if not canonical.is_file() or hashlib.md5(canonical.read_bytes()).hexdigest()[:12]!=match[2]:
                raise ValueError('Actual hashed static bytes required via --static-root: '+route)
        if not canonical.is_file():raise ValueError('Actual static bytes unavailable: '+route)
        source=canonical
    destination=ROOT/'source_assets'/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.is_file() or destination.read_bytes()!=source.read_bytes():shutil.copyfile(source,destination)
    if source.suffix in ('.woff2','.ttf'):
        license_path=source.parent/'OFL.txt'
        if not license_path.is_file():license_path=APP/'static/littlehands/fonts/OFL.txt'
        if not license_path.is_file():raise ValueError('Actual font license must accompany exported font bytes.')
        license_destination=destination.parent/'OFL.txt'
        if not license_destination.is_file() or license_destination.read_bytes()!=license_path.read_bytes():shutil.copyfile(license_path,license_destination)
    if source.suffix=='.css':
        for url in re.findall(r'url\([\"\']?([^\)\"\']+)',source.read_text()):
            if not urlsplit(url).scheme and not url.startswith('data:'):
                asset=(relative.parent/url).as_posix()
                copy_static('/static/'+asset)
    return destination


def load_captures():
    found = {}
    for path in sorted((ROOT/'captures').glob('*.json')):
        data = json.loads(path.read_text())
        if data.get('schema') != 'little-hands-browser-measurement-v1':
            continue
        sid = data['state']
        if sid not in {'state-'+row[0] for row in STATES}:
            raise ValueError('Unknown measured state: '+sid)
        vp = 'desktop' if data['viewport']['width'] == 1200 else 'mobile' if data['viewport']['width'] == 390 else None
        if vp is None:
            raise ValueError('Only actual1200/390 captures enter canonical layout: '+str(path))
        if (sid,vp) in found:
            raise ValueError('Duplicate state/viewport capture: '+sid+'/'+vp)
        if data.get('fonts_ready') != 'loaded':
            raise ValueError('Wait for actual fonts to load before capture: '+sid+'/'+vp)
        for collection in ('texts','controls','surfaces','images'):
            for item in data[collection]:
                if not item['id'].startswith(sid+'-') or len(item['box']) != 4 or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in item['box']):
                    raise ValueError('Invalid actual DOM geometry in '+str(path))
        if not data.get('html'):
            raise ValueError('Sanitized actual HTML required in '+str(path))
        restore_transport_aliases(data,path)
        found[sid,vp] = (data,path)
    return found


def resolve_target(sid, control, captures, overrides):
    key = sid + '/' + control['id']
    if key in overrides:
        return overrides[key]
    href = control.get('href')
    if href and href.startswith('#'):
        return None
    if control.get('action') == 'logout':
        return 'publichome'
    if control.get('method') == 'POST' and control['tag'] == 'button':
        return {'login':'memberhome','signup':'memberhome','sessionavailable':'review','review':'confirmed','cancelconfirm':'cancelled','reschedule':None,'staffcreate':None,'staffedit':None}.get(sid.removeprefix('state-'))
    if not href or urlsplit(href).scheme or href.startswith('//'):
        return None
    path = urlsplit(href).path
    if path == '/':
        observed=[row[0] for (state,vp),row in captures.items() if state==sid]
        if observed:return 'memberhome' if any(control.get('native_key')=='nav-bookings' for data in observed for control in data['controls']) else 'publichome'
        return 'publichome' if sid in ('state-publichome','state-login','state-signup','state-403','state-404') else 'memberhome'
    fixed = {row[4]:row[0] for row in STATES if row[4] and row[4] != '/'}
    if path in fixed:
        return fixed[path]
    def represented(names):
        matches=[name for name in names if any(state=='state-'+name and data['route']==path for (state,vp),(data,record) in captures.items())]
        if len(matches)==1:return matches[0]
        if len(matches)>1 and sid.removeprefix('state-') in matches:return sid.removeprefix('state-')
        if len(matches)>1 and sid in ('state-cancelconfirm','state-reschedule'):return 'confirmed' if 'confirmed' in matches else None
        return None
    if re.fullmatch(r'/sessions/\d+/',path):
        return represented(['sessionavailable'])
    if re.fullmatch(r'/bookings/[^/]+/cancel/',path):
        return represented(['cancelconfirm'])
    if re.fullmatch(r'/bookings/[^/]+/reschedule/',path):
        return represented(['reschedule'])
    if re.fullmatch(r'/bookings/[^/]+/',path):
        return represented(['confirmed','waitlisted','cancelled'])
    if re.fullmatch(r'/staff/sessions/\d+/edit/',path):
        return represented(['staffedit'])
    if re.fullmatch(r'/staff/sessions/\d+/',path):
        return represented(['staffroster'])
    return None


def inline_label_records(data):
    records=[];skip=set()
    for index,text in enumerate(data['texts']):
        if index in skip:continue
        record=json.loads(json.dumps(text))
        match=re.fullmatch(r'\[data-native-key="([^"]+)"\]',text['selector'])
        if match and index+1<len(data['texts']):
            next_text=data['texts'][index+1]
            raw_label=re.search(r'<label\b[^>]*data-native-key="'+re.escape(match[1])+r'"[^>]*>(.*?)</label>',data['html'],re.S)
            literal=html.unescape(re.sub(r'<[^>]+>','',raw_label[1])) if raw_label else ''
            literal=' '.join(literal.split())
            fields=('fontFamily','fontWeight','fontSize','leading','letter_spacing','ink')
            if (next_text['value']=='*' and literal==text['value'].strip()+' *' and
                all(text['style'][key]==next_text['style'][key] for key in fields) and
                abs(text['box'][1]-next_text['box'][1])<.5 and
                abs(text['box'][0]+text['box'][2]-next_text['box'][0])<1):
                record.update(value=literal,raw_value=literal,box=[text['box'][0],text['box'][1],next_text['box'][0]+next_text['box'][2]-text['box'][0],text['box'][3]],merged_fragments=[text['id'],next_text['id']])
                skip.add(index+1)
        records.append(record)
    return records


def used_line_records(data):
    records=inline_label_records(data)
    by_selector={}
    for text in records:
        if text.get('text_context',{}).get('block_content'):
            by_selector.setdefault(text['selector'],[]).append(text)
    for selector,rows in by_selector.items():
        computed=rows[0]['style']['leading'];content=rows[0]['content_box']
        indices={round((row['box'][1]-content[1])/computed) for row in rows}
        count=len(indices)
        if indices!=set(range(count)) or abs(content[3]-count*computed)>1:continue
        used=content[3]/count
        for row in rows:
            index=round((row['box'][1]-content[1])/computed)
            row['native_line_metrics']={'computed_css_leading':computed,'observed_content_box':content,'observed_line_count':count,'derived_used_pitch':used}
            row['box'][1]=content[1]+index*used;row['box'][3]=used
            row['style']['leading']=used
    return records


def observed_native_text(text):
    style=text['style'];value=text.get('raw_value',text['value']);face='Bold' if style['fontWeight']>=600 else 'Regular';matches=[]
    for filename in ('native-font-calibration.json','native-font-calibration-v2.json'):
        path=ROOT/filename
        if not path.is_file():continue
        calibration=json.loads(path.read_text())
        if calibration.get('schema')!='littlehands-native-font-calibration-v1' or not calibration.get('source_evidence',{}).get('artifact_sha256'):
            raise ValueError('Pinned actual native text calibration required.')
        for row in calibration['texts']:
            font=row.get('fontName',{});weight=font.get('variationSettings',{}).get('wght',700 if font.get('style')=='Bold' else 400)
            if (row.get('type')=='TEXT' and row.get('characters')==value and font.get('family')==style['fontFamily'] and font.get('style')==face and weight==style['fontWeight'] and row.get('fontSize')==style['fontSize'] and row.get('lineHeight',{}).get('unit')=='PIXELS' and abs(row['lineHeight']['value']-style['leading'])<.001 and row.get('letterSpacing',{}).get('unit')=='PIXELS' and abs(row['letterSpacing']['value']-style['letter_spacing'])<.000001 and row.get('textAutoResize')=='WIDTH_AND_HEIGHT'):
                matches.append((row,calibration,path))
    if len(matches)>1:raise ValueError('Ambiguous actual text calibration: '+text['id'])
    if not matches:return None
    row,calibration,path=matches[0]
    if not all(isinstance(row.get(field),(int,float)) and math.isfinite(row[field]) and row[field]>0 for field in ('width','height')):
        raise ValueError('Positive actual native text calibration geometry required.')
    return {'file':path.name,'sha256':sha(path),'sanitized_getter_sha256':calibration['source_evidence']['artifact_sha256'],'raw_getter_sha256':calibration['source_evidence'].get('raw_getter_sha256'),'file_key':calibration['fileKey'],'page_id':calibration['pageId'],'node_id':row['id'],'width':row['width'],'height':row['height'],'scope':'Observed intrinsic TEXT allocation for this exact characters/family/style/weight/size/leading/tracking only; raw CSS box is retained.'}


def authored_controls(data):
    controls=[]
    for original in data['controls']:
        control=dict(original)
        if '\n' in control['label']:
            path=ROOT/'control-line-observation.json'
            if not path.is_file():raise ValueError('Actual one-row control proof required: '+control['id'])
            proof=json.loads(path.read_text());font=proof.get('font',{});style=control['style']
            runs=proof.get('runs',[]);rects=[run['rects'][0] for run in runs if len(run.get('rects',[]))==1]
            actual_html=re.search(r'<a\b[^>]*data-native-key="hero-browse"[^>]*>.*?</a>',data['html'],re.S)
            css=re.findall(r'href="(/static/[^"]+\.css)"',data['html'])
            one_row=len(rects)==len(runs)>1 and max(row['y'] for row in rects)-min(row['y'] for row in rects)<.5 and max(row['y']+row['height'] for row in rects)-min(row['y']+row['height'] for row in rects)<.5
            font_matches=(font.get('family','').split(',')[0].strip()==style['fontFamily'] and float(font.get('weight',0))==style['fontWeight'] and float(font.get('size','0px').removesuffix('px'))==style['fontSize'] and abs(float(font.get('leading','0px').removesuffix('px'))-style['leading'])<.000001 and (0 if font.get('letterSpacing')=='normal' else float(font.get('letterSpacing','0px').removesuffix('px')))==style['letter_spacing'])
            confirmed=(proof.get('schema')=='littlehands-control-line-observation-v1' and proof.get('environment')=='staging' and proof.get('display')=='inline-flex' and proof.get('flexDirection')=='row' and proof.get('alignItems')=='center' and control.get('native_key')=='hero-browse' and control['label']==proof.get('innerText') and actual_html and actual_html[0]==proof.get('html') and not re.search(r'<br\b',actual_html[0],re.I) and css==proof.get('css') and one_row and all(run.get('whiteSpace')=='normal' for run in runs) and ''.join(run['text'] for run in runs)==proof.get('textContent') and font_matches and abs(control['box'][2]-proof['box']['width'])<.001 and abs(control['box'][3]-proof['box']['height'])<.001)
            if not confirmed:raise ValueError('Unproven native control line break: '+control['id'])
            control['raw_label']=control['label'];control['label']=proof['textContent']
            control['label_normalization']={'file':path.name,'sha256':sha(path),'source_css':css,'observed_runs':runs,'scope':'Only this exact observed inline-flex row converts serialized innerText newline to actual textContent; original capture label is preserved.'}
        controls.append(control)
    return controls


def layout_for(data, palette, styles, assets, mappings):
    layers, products = [], {}
    for surface in data['surfaces']:
        x,y,w,h = surface['box']
        if w <= 0 or h <= 0:
            continue
        s = surface['style']
        fill = color(s['fill'],palette)
        borders=s.get('borders',[{'width':s['stroke_width'],'color':s['stroke']}] * 4)
        uniform=len({(row['width'],row['color']) for row in borders})==1
        stroke = color(s['stroke'],palette) if s['stroke_width'] and uniform else None
        if not fill and not stroke and not any(row['width'] for row in borders):
            continue
        layer = dict(id=surface['id'],kind='rect',x=x,y=y,w=w,h=h,fill=fill or 'paper',radius=min(s['radius'],w/2,h/2),role='surface')
        if stroke:
            layer.update(stroke=stroke,stroke_width=s['stroke_width'])
        if s.get('boxShadow','none') != 'none':
            raise ValueError('Measured box-shadow requires explicit mapping: '+surface['id'])
        if fill or stroke:layers.append(layer)
        if not uniform:
            for side,border in enumerate(borders):
                bw=border['width']
                if not bw:continue
                edgebox=([x,y,w,bw],[x+w-bw,y,bw,h],[x,y+h-bw,w,bw],[x,y,bw,h])[side]
                layers.append(dict(id=surface['id']+'-edge-'+str(side),kind='rect',**dict(zip(('x','y','w','h'),edgebox)),fill=color(border['color'],palette),role='divider'))
        mappings.append({'key':layer['id'],'selector':surface['selector'],'kind':'surface','semantic':surface.get('semantic')})
    for image in data['images']:
        x,y,w,h = image['box']
        source = copy_static(image['src'])
        if image['style']['objectFit']=='cover' and image['style']['objectPosition'] not in ('50% 50%','center','center center'):
            raise ValueError('Measured noncenter image crop needs explicit authoring: '+image['id'])
        if image['style']['radius'] != 0:
            raise ValueError('Image radius needs supported authoring: '+image['id'])
        asset = 'image-'+sha(source)[:16]
        assets[asset] = {'path':source.relative_to(ROOT).as_posix(),'sha256':sha(source),'reference':False}
        layers.append(dict(id=image['id'],kind='image',x=x,y=y,w=w,h=h,asset=asset,fit='FILL' if image['style']['objectFit']=='cover' else 'FIT',role='image'))
        mappings.append({'key':image['id'],'selector':image['selector'],'kind':'image','alt':image['alt'],'original_src':image['src'],'object_position':image['style']['objectPosition']})
    for text in used_line_records(data):
        x,y,w,h = text['box']; s = text['style']
        value=text.get('raw_value',text['value'])
        if text.get('text_context',{}).get('block_content'):w=math.ceil(w)
        calibration=observed_native_text(text)
        if calibration:w=max(w,calibration['width']);h=max(h,calibration['height'])
        if not text['value'].strip() or w <= 0 or h <= 0:
            continue
        if s['fontFamily'] != 'Hahmlet':
            raise ValueError('Measured fallback font needs review: '+text['id']+' '+s['fontFamily'])
        layers.append(dict(id=text['id'],kind='text',x=x,y=y,w=w,h=h,value=value,size=s['fontSize'],leading=s['leading'],letter_spacing=s['letter_spacing'],max_lines=1,ink=color(s['ink'],palette),font='display' if s['fontWeight']>=600 else 'body',align=s['align'] if s['align'] in ('left','center','right','justified') else 'left'))
        mappings.append({'key':text['id'],'selector':text['selector'],'kind':'text','literal':value,'allocation':text.get('text_context',{}).get('allocation','legacy observed fragment'),'actual_content_box':text.get('content_box'),'merged_fragments':text.get('merged_fragments',[]),'native_line_metrics':text.get('native_line_metrics'),'native_text_calibration':calibration})
    for control in authored_controls(data):
        if control['tag'] not in ('a','button'):
            if control['label'] and control['type'] not in ('checkbox','radio'):
                x,y,w,h=control['box']; s=control['style']; t,r,b,l=s['padding']
                layers.append(dict(id=control['id']+'-value',kind='text',x=x+l,y=y+(h-s['leading'])/2,w=max(1,w-l-r),h=s['leading'],value=control['label'],size=s['fontSize'],leading=s['leading'],letter_spacing=s['letter_spacing'],max_lines=1,ink=color(s['ink'],palette),font='body',align='left'))
            continue
        s = control['style']; x,y,w,h=control['box']
        fields=('fontFamily','fontWeight','fontSize','ink')
        if any(any(run[field]!=s[field] for field in fields) for run in control.get('label_styles',[])):
            raise ValueError('Mixed-style label needs explicit native component authoring: '+control['id'])
        if not control['label']:
            raise ValueError('Visible action without label: '+control['id'])
        if s['fontFamily'] != 'Hahmlet':
            raise ValueError('Measured control fallback font needs review: '+control['id'])
        calibration=observed_native_text({'id':control['id'],'value':control['label'],'style':s})
        native_box=list(control['box'])
        if control.get('native_key')=='brand' and calibration:
            border=s.get('borders',[{'width':s['stroke_width']}] * 4)
            native_box[2]=max(w,calibration['width']+s['padding'][1]+s['padding'][3]+border[1]['width']+border[3]['width'])
        fill = color(s['fill'],palette)
        t,r,b,l = s['padding']
        style = {'fill':fill,'ink':color(s['ink'],palette),'radius':s['radius'],'fontSize':s['fontSize'],'font':'display' if s['fontWeight']>=600 else 'body','leading':s['leading'],'letter_spacing':s['letter_spacing'],'paddingX':l,'paddingY':t,'minHeight':h,'maxWidth':native_box[2]}
        if s['stroke_width']:
            style.update(stroke=color(s['stroke'],palette),stroke_width=s['stroke_width'])
        shadow=s.get('boxShadow','none')
        if shadow!='none':
            match=re.fullmatch(r'(rgba?\([^)]+\)) 0px -([\d.]+)px 0px 0px inset',shadow)
            if not match:raise ValueError('Measured control shadow requires explicit mapping: '+control['id']+' '+shadow)
            thickness=float(match[2])
            layers.append(dict(id=control['id']+'-current-underline',kind='rect',x=x,y=y+h-thickness,w=w,h=thickness,fill=color(match[1],palette),role='divider'))
        variant = 'Control-'+safe(control['id'])
        styles[variant] = style
        products[control['id']] = {'box':native_box,'variant':variant,'label':control['label']}
        mappings.append({'key':control['id'],'selector':control['selector'],'kind':'control','native_key':control.get('native_key'),'label':control['label'],'disabled':control.get('disabled',False),'raw_label':control.get('raw_label',control['label']),'raw_css_box':control['box'],'native_box':native_box,'native_allocation_delta':{'width':native_box[2]-w,'height':0},'native_text_calibration':calibration,'label_normalization':control.get('label_normalization')})
    targets = {layer['id']:layer for layer in layers}
    targets.update({key:dict(zip(('x','y','w','h'),button['box'])) for key,button in products.items()})
    groups=[]
    measured=data.get('containers',[])
    by_selector={row['selector']:row for row in measured}
    declarations={}
    owners={}
    for key in targets:
        candidates=[row for row in measured if any(key==member or key.startswith(member+'-edge-') or key==member+'-value' or key==member+'-current-underline' for member in row.get('members',[]))]
        if candidates:owners[key]=candidates[-1]['selector']
    active=set(owners.values())
    for selector in list(active):
        row=by_selector[selector]
        while row.get('parent_selector') in by_selector:
            active.add(row['parent_selector']);row=by_selector[row['parent_selector']]
    for row in measured:
        if row['selector'] not in active:continue
        parent=by_selector.get(row.get('parent_selector'))
        while parent and parent['selector'] not in active:parent=by_selector.get(parent.get('parent_selector'))
        x,y,w,h=row['box']
        declarations[row['selector']]={'key':row['id'],'kind':'frame','box':[x-(parent['box'][0] if parent else 0),y-(parent['box'][1] if parent else 0),w,h],'clip':row.get('css',{}).get('overflow_x') in ('auto','scroll','hidden') or row.get('css',{}).get('overflow_y') in ('auto','scroll','hidden'),'children':[]}
        if declarations[row['selector']]['clip']:
            member_keys=row.get('members',[])
            descendants=[layer for key,layer in targets.items() if any(key==member or key.startswith(member+'-edge-') or key==member+'-value' or key==member+'-current-underline' for member in member_keys)]
            horizontal=row.get('css',{}).get('overflow_x') in ('auto','scroll') and any(layer['x']<x-.5 or layer['x']+layer['w']>x+w+.5 for layer in descendants)
            vertical=row.get('css',{}).get('overflow_y') in ('auto','scroll') and any(layer['y']<y-.5 or layer['y']+layer['h']>y+h+.5 for layer in descendants)
            declarations[row['selector']]['scroll']='both' if horizontal and vertical else 'horizontal' if horizontal else 'vertical' if vertical else 'none'
        if parent:declarations[row['selector']]['parent']=parent['id']
    for key,selector in owners.items():declarations[selector]['children'].append(key)
    for row in measured:
        if row['selector'] not in declarations:continue
        parent=row.get('parent_selector')
        if parent in declarations:declarations[parent]['children'].append(row['id'])
    absolute_boxes={**{key:[layer[field] for field in ('x','y','w','h')] for key,layer in targets.items()},**{row['id']:row['box'] for row in measured}}
    for row in measured:
        declaration=declarations.get(row['selector'])
        if not declaration or not declaration['children']:continue
        css=row.get('css',{})
        if 'actions' in str(row.get('classes','')).split() and css.get('display')=='flex' and css.get('flex_direction') in ('row','column'):
            vertical=css['flex_direction']=='column'
            children=sorted(declaration['children'],key=lambda key:absolute_boxes[key][1 if vertical else 0])
            boxes=[absolute_boxes[key] for key in children]
            same_cross=all(abs(box[0 if vertical else 1]-boxes[0][0 if vertical else 1])<=.5 for box in boxes)
            gaps=[boxes[i+1][1 if vertical else 0]-boxes[i][1 if vertical else 0]-boxes[i][3 if vertical else 2] for i in range(len(boxes)-1)]
            linear=same_cross and all(abs(gap-css['gap'])<=.5 for gap in gaps) and not any(key in {item['id'] for item in measured} for key in children)
            if linear:
                declaration.update(kind='auto-layout',children=children,layout={'direction':'VERTICAL' if vertical else 'HORIZONTAL','padding':[0,0,0,0],'gap':css['gap'],'width':'hug','height':'hug'})
                declaration.pop('box');declaration.pop('clip');declaration.pop('scroll',None)
            mappings.append({'key':row['id'],'selector':row['selector'],'kind':declaration['kind'],'css_box':row['box'],'flow':'actual child geometry is a linear flex sequence' if linear else 'Frame retained because wrapped, aligned, or spaced geometry is not a supported linear flow'})
        else:mappings.append({'key':row['id'],'selector':row['selector'],'kind':'frame','css_box':row['box']})
        groups.append(declaration)
    return {'width':data['viewport']['width'],'height':data['document']['height'],'bg':color(data['body_background'],palette,'paper'),'layers':layers,'control_boxes':{},'product_buttons':products,'containers':groups}


def share_control_styles(styles, state_layouts, nodes, palette_options):
    shared={viewport:{} for viewport in styles};renamed={};identities={}
    for old in sorted({variant for variants in styles.values() for variant in variants}):
        profiles={viewport:{key:value for key,value in variants[old].items() if key!='maxWidth'} if old in variants else None for viewport,variants in sorted(styles.items())}
        identity=json.dumps(profiles,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
        representative=next(profile for profile in profiles.values() if profile is not None)
        family='Solid' if representative.get('fill') is not None else 'Outline' if representative.get('stroke') and representative.get('stroke_width',0)>0 else 'Text'
        variant=family+'-'+hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]
        if variant in identities and identities[variant]!=identity:raise ValueError('Shared control style hash collision.')
        identities[variant]=identity;renamed[old]=variant
        for viewport,variants in styles.items():
            if old not in variants:continue
            current=variants[old]
            if variant not in shared[viewport]:shared[viewport][variant]=json.loads(json.dumps(current))
            else:shared[viewport][variant]['maxWidth']=max(shared[viewport][variant]['maxWidth'],current['maxWidth'])
    for viewport,states in state_layouts.items():
        for layout in states.values():
            for button in layout['product_buttons'].values():button['variant']=renamed[button['variant']]
    for node in nodes:
        if node['type']=='action':
            node['annotation']['visual_variant']=renamed[node['annotation']['visual_variant']]
            node['component_id']='component-'+node['annotation']['visual_variant']
    for sample in palette_options:
        sample['variant']=renamed[sample['variant']]
        sample['component']='component-'+sample['variant']
    return shared,renamed


def snapshot_html(captured_html):
    content=captured_html.replace('="/static/','="../source_assets/')
    content=re.sub(r'<meta\b(?=[^>]*\bcharset\s*=)[^>]*>','',content,flags=re.I)
    content,count=re.subn(r'<head\b[^>]*>',lambda match:match[0]+'<meta charset="utf-8">',content,count=1,flags=re.I)
    if count!=1 or content.encode('utf-8').find(b'<meta charset="utf-8">')>=1024:
        raise ValueError('Actual captured head must permit an early UTF-8 declaration.')
    if not re.search(r'<meta\b[^>]*name=[\"\']viewport[\"\']',content,re.I):
        content=content.replace('<meta charset="utf-8">','<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',1)
    return content


def build():
    captures=load_captures()
    unverified_ua_internals=[{'state':sid,'viewport':vp,'selector':control['selector'],'type':control['type'],'checked':control.get('checked'),'box':control['box'],'reason':'UA-native mark paint is not exposed by measured CSS; no mark is invented by the adapter.'} for (sid,vp),(data,path) in captures.items() for control in data['controls'] if control.get('type') in ('checkbox','radio') and control['style']['fill'] in ('rgba(0, 0, 0, 0)','transparent') and not control['style']['stroke_width']]
    stylesheet_epochs=sorted({route for data,path in captures.values() for route in re.findall(r'href="(/static/[^"]+\.css)"',data['html'])})
    metadata_pending=[{'state':sid,'viewport':vp,'capture':path.name} for (sid,vp),(data,path) in captures.items() if any(not {'element_box','content_box','glyph_box','raw_value','text_context'}<=set(text) for text in data['texts'])]
    manifest_path=STATIC_ROOT/'staticfiles.json'
    current_stylesheet=None
    if manifest_path.is_file():
        manifest=json.loads(manifest_path.read_text())
        name=manifest.get('paths',{}).get('littlehands/app.css')
        if name:current_stylesheet='/static/'+name
    stylesheet_current=len(stylesheet_epochs)==1 and (current_stylesheet is None or stylesheet_epochs==[current_stylesheet])
    if len(captures)==len(STATES)*2 and (metadata_pending or not stylesheet_current):
        write_json(ROOT/'source-status.json',{'schema':'little-hands-design-source-status-v1','status':'blocked-final-source-epoch','actual_captures':len(captures),'unverified_ua_internals':unverified_ua_internals,'metadata_pending':metadata_pending,'stylesheet_epochs':stylesheet_epochs,'current_manifest_stylesheet':current_stylesheet,'native_handoff':'pending','visual_quality':'unverified','approval':'not-recorded'})
        raise ValueError('Final source requires fresh measured content boxes and one actual current stylesheet epoch; preserve old captures as business observations and refresh design captures.')
    stylesheet='../../static/littlehands/app.css'
    for data,path in captures.values():
        for route in re.findall(r'href="(/static/[^"]+\.css)"',data['html']):
            stylesheet='../'+copy_static(route).relative_to(ROOT).as_posix()
        if stylesheet!='../../static/littlehands/app.css':break
    snapshot_dir=ROOT/'snapshots';snapshot_dir.mkdir(exist_ok=True)
    snapshots=[]
    for (sid,vp),(data,path) in captures.items():
        name=sid.removeprefix('state-')+'-'+vp+'.html'
        content=snapshot_html(data['html'])
        destination=snapshot_dir/name
        if not destination.is_file() or destination.read_text(encoding='utf-8')!=content:destination.write_text(content,encoding='utf-8')
        snapshots.append({'state':sid,'viewport':vp,'css_viewport':data['viewport'],'route':data['route'],'path':'snapshots/'+name,'capture':path.relative_to(ROOT).as_posix(),'capture_sha256':sha(path),'html_sha256':sha(destination),'scope':'The actual captured sanitized DOM with only local static URL rewriting and the original UTF-8 and viewport metadata restored; forms are inert. Visual review source only, not a new business action or acceptance observation.'})
    write_json(snapshot_dir/'index.json',{'schema':'little-hands-actual-visual-snapshots-v1','snapshots':snapshots})
    (ROOT/'visual-review.html').write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>작은손 실제 화면별 시각 검토</title><link rel="stylesheet" href="'+stylesheet.removeprefix('../')+'"></head><body><main class="page"><div class="wrap"><h1>실제 화면별 시각 검토</h1><p>각 링크는 해당 상태·뷰포트의 실제 캡처 DOM 하나를 엽니다. 폼은 inert이며 데이터 변경을 실행하지 않습니다. 실제 업무 흐름의 실행 증거와 구분합니다.</p><table class="data-table"><thead><tr><th scope="col">상태</th><th scope="col">데스크톱1200×900 CSS</th><th scope="col">모바일390×960 CSS</th></tr></thead><tbody>'+''.join('<tr><th scope="row">'+html.escape(title)+'</th>'+''.join('<td><a href="snapshots/'+name+'-'+vp+'.html">'+vp+'</a></td>' for vp in ('desktop','mobile'))+'</tr>' for name,title,template,requirements,route in STATES)+'</tbody></table></div></main></body></html>')
    overrides_path=ROOT/'prototype-targets.json'
    overrides=json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    palette=dict(json.loads((ROOT/'tokens.json').read_text())['colors'])
    nodes=[]; edges=[]
    def node(nid,kind,title,**extra):
        nodes.append(dict(id=nid,type=kind,title=title,status='observed' if kind in ('requirement','screen','code') else 'unverified',**extra))
    def edge(a,b,kind):
        row={'from':a,'to':b,'type':kind}
        if row not in edges:edges.append(row)
    for i,(title,test) in enumerate(REQS,1):
        rid=f'REQ-{i:03d}'; aid=f'AC-{i:03d}'; tid=f'TEST-{i:03d}'
        node(rid,'requirement',title,source='brief.md#요구사항-열-가지',detail='에이전트 제품 해석. 현재 구현 사실과 실제 인수 결과를 구분한다.')
        node(aid,'acceptance',title+' 인수',source='../ARCHITECTURE.md',detail='실제 DB/브라우저/Figma 근거를 부모가 연결하기 전까지 미검증.')
        node(tid,'test',test or '실제 데스크톱·모바일·키보드·Figma 직접 조작과 getter 검증',source='../booking/tests/test_booking.py#'+test if test else 'README.md#실제-검증',detail='소스에 존재하는 검사 또는 계획된 실제 검증. 실행 결과는 여기서 생성하지 않는다.')
        edge(rid,aid,'accepted by'); edge(aid,tid,'checked by')
    if (ROOT/'native-font-calibration.json').is_file():
        node('reference-native-font-calibration','reference','실제 Hahmlet 네이티브 여섯 문자열의 할당 측정',source='native-font-calibration.json',detail='부모가 실제 Figma에서 만든 TEXT 여섯 개를 일반 인증 getter로 읽은 보정 근거다. 정확히 일치하는 문자열·서체·크기·행간·자간의 할당에만 쓰며 앱 전체 네이티브 전달이나 글꼴 바이너리 동일성을 증명하지 않는다.')
        edge('reference-native-font-calibration','REQ-010','informs')
    for ref,filename,title in [('reference-native-font-calibration-v2','native-font-calibration-v2.json','추가 일곱 네이티브 문자열의 실제 할당 측정'),('reference-control-line-observation','control-line-observation.json','실제 한 줄 flex 조작 문구의 DOM 관측')]:
        if (ROOT/filename).is_file():
            node(ref,'reference',title,source=filename,detail='정확히 일치하는 원문·서체·레이아웃 증거에만 쓰는 제한된 보정 근거다. 원본 CSS 상자와 캡처를 보존하며 전체 네이티브 인수 성공을 의미하지 않는다.')
            edge(ref,'REQ-010','informs')
    state_layouts={'desktop':{},'mobile':{}}; styles={'desktop':{},'mobile':{}}; assets={}; mappings=[]; bindings=[]; seen_actions={}; palette_options=[]
    prototype_states=[]
    gallery=['<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>작은손 커피공방 실제 화면 소스</title><link rel="stylesheet" href="'+stylesheet+'"></head><body><aside class="wrap"><h1>작은손 커피공방 실제 화면 소스</h1><p>실제 Django 응답의 읽기 전용 디자인 소스입니다. 폼 제출과 업무 처리는 실제 서비스에서만 실행합니다.</p></aside>']
    for name,title,template,requirements,route in STATES:
        sid='state-'+name; screen='screen-'+name; code='code-'+name
        node(screen,'screen',title,source='../templates/'+template,annotation={'summary':title+' 화면의 목적과 동작','purpose':SCREEN_MEANING[name][0],'journey':SCREEN_MEANING[name][1],'failure':'폼 오류·권한·409는 서버가 결정한다. Figma는 관측한 상태만 보여 준다.','platform_scope':'웹: '+PLATFORM['web']+' Figma: '+PLATFORM['figma']})
        node(sid,'state',title+' 표시',source='../templates/'+template)
        node(code,'code',template,source='../templates/'+template,detail='현재 소스 읽기만 확인. 실제 실행 인수는 별도 근거가 필요하다.')
        edge(screen,sid,'has state'); edge(screen,code,'implemented by')
        for req in requirements:
            edge(f'REQ-{req:03d}',screen,'appears on'); edge(code,f'TEST-{req:03d}','checked by')
        prototype_states.append({'id':sid,'screen':screen,'view':name,'title':title,'body':PLATFORM['figma']})
        desktop=captures.get((sid,'desktop'))
        if desktop:
            parser=GalleryParser(sid); parser.feed(desktop[0]['html'])
            gallery.append('<section id="'+screen+'" data-source-state="'+sid+'"><h2>'+html.escape(title)+'</h2>'+''.join(parser.output)+'</section>')
        for vp in ('desktop','mobile'):
            if (sid,vp) not in captures:continue
            data,path=captures[sid,vp]
            local_mappings=[]
            layout=layout_for(data,palette,styles[vp],assets,local_mappings)
            state_layouts[vp][sid]=layout
            mappings.extend({'state':sid,'viewport':vp,'measurement':path.relative_to(ROOT).as_posix(),**row} for row in local_mappings)
            for control in authored_controls(data):
                if control['tag'] not in ('a','button'):continue
                aid='action-'+control['id']; target=resolve_target(sid,control,captures,overrides)
                target_sid='state-'+target if target else None
                if target_sid==sid:target_sid=None
                if target_sid and target_sid not in {'state-'+row[0] for row in STATES}:
                    raise ValueError('Unknown prototype target: '+target_sid)
                if aid not in seen_actions:
                    node(aid,'action',control['label'],source='../templates/'+template,source_screen=screen,source_state=sid,web_action=control.get('action') or 'navigate',target_ids=[target_sid] if target_sid else [],annotation={'control_id':control['id'],'summary':control['label']+' 조작과 결과','purpose':title+'에서 다음 행동을 선택하는 조작','behavior':WEB_BEHAVIOR.get(control.get('action'),'웹은 표시된 실제 링크의 GET 경로 또는 문서 앵커로 이동한다.')+' '+('Figma는 관측된 다음 시각 상태로만 이동한다.' if target_sid else 'Figma에서는 실제 컴포넌트와 설명을 유지하고 reaction은 없다.'),'result':('Figma에서는 '+target+' 화면 예시를 표시한다. 실제 결과는 서버 응답으로 결정한다.' if target_sid else '웹에서만 해당 동작을 실행한다.'),'failure':'권한·입력·정원·revision 검증은 웹 서버가 담당한다.','functional_states':[sid]+([target_sid] if target_sid else []),'visual_variant':layout['product_buttons'][control['id']]['variant'],'platform_scope':'웹: '+PLATFORM['web']+' Figma: '+PLATFORM['figma'],'web_method':control.get('method') or 'GET','web_href':control.get('href') or control.get('form_action') or data['route'],'source_selector':control['selector']})
                    seen_actions[aid]=target_sid
                    if vp=='desktop' and target_sid:palette_options.append({'label':control['label'],'component':'component-'+control['id'],'variant':layout['product_buttons'][control['id']]['variant'],'action':aid,'state':target_sid,'useCases':[control['label']+'의 실제 화면 조작']})
                    edge(screen,aid,'triggers'); edge(aid,code,'implemented by')
                    if target_sid:edge(aid,target_sid,'navigates to')
                elif seen_actions[aid]!=target_sid:raise ValueError('Viewport action target differs: '+aid)
                if target_sid:
                    layout['control_boxes'][control['id']]=layout['product_buttons'].pop(control['id'])['box']
                    bindings.append({'action':aid,'source_state':sid,'target_state':target_sid,'viewport':vp,'control_id':control['id']})
                else:
                    layout['product_buttons'][control['id']]['specification_id']=aid
    previous_styles={viewport:len(variants) for viewport,variants in styles.items()}
    styles,variant_families=share_control_styles(styles,state_layouts,nodes,palette_options)
    for variant in sorted(set(variant_families.values())):
        node('component-'+variant,'component','공유 조작 스타일 '+variant,source='native-layout.json#control_styles/'+variant,detail='문구·행동·목적지·상태 ID와 무관한 데스크톱/모바일 시각 스타일 쌍이다. 각 인스턴스의 실제 상자와 TEXT 문구·명세·연결은 별도로 보존한다.')
    for current in nodes:
        if current['type']=='action':edge(current['id'],current['component_id'],'uses component')
    for mapping in mappings:
        if mapping.get('kind')=='control':mapping['shared_variant']=variant_families['Control-'+safe(mapping['key'])]
    write_json(ROOT/'control-reuse.json',{'schema':'little-hands-shared-control-profiles-v1','scope':'Authored main declarations from exact paired visual profiles, not an actual Figma main/instance readback. Only maxWidth is excluded from identity; each main cap is the maximum observed width in that profile/viewport.','previous_styles':previous_styles,'shared_styles':{viewport:len(variants) for viewport,variants in styles.items()},'shared_component_definitions':len(set(variant_families.values())),'instance_families':variant_families})
    gallery.append('</body></html>')
    (ROOT/'app/index.html').write_text('\n'.join(gallery))
    samples=[]
    for option in palette_options:
        if option['label'] not in {row['label'] for row in samples}:samples.append(option)
        if len(samples)==2:break
    used_colors=set()
    for vp,states in state_layouts.items():
        for sid,layout in states.items():
            used_colors.add(layout['bg'])
            for layer in layout['layers']:
                used_colors.update(layer[key] for key in ('fill','ink','stroke') if key in layer)
        for style in styles[vp].values():used_colors.update(style[key] for key in ('fill','ink','stroke') if key in style and style[key] is not None)
    colors={key:value for key,value in palette.items() if key in used_colors}
    type_bindings=[]; family_bindings=[]; radius_bindings=[]; padding_bindings=[]
    for vp,states in state_layouts.items():
        for sid,layout in states.items():
            for layer in layout['layers']:
                if layer['kind']=='text' and layer['size']==15:
                    type_bindings.append({'key':f'littlehands.{vp}.{sid}.'+layer['id'],'field':'fontSize'})
                    family_bindings.append({'key':f'littlehands.{vp}.{sid}.'+layer['id'],'field':'fontFamily'})
            for cid,button in layout['product_buttons'].items():
                st=styles[vp][button['variant']]
                if st['radius']==0:radius_bindings.append({'key':f'littlehands.{vp}.{sid}.'+cid,'field':'cornerRadius'})
                if st['paddingX']==22:padding_bindings.extend({'key':f'littlehands.{vp}.{sid}.'+cid,'field':field} for field in ('paddingLeft','paddingRight'))
    for vp,variants in styles.items():
        for variant,style in variants.items():
            if style['radius']==0:radius_bindings.append({'key':f'littlehands.{vp}.component.'+variant,'field':'cornerRadius'})
            if style['paddingX']==22:padding_bindings.extend({'key':f'littlehands.{vp}.component.'+variant,'field':field} for field in ('paddingLeft','paddingRight'))
    foundations={'version':1,'roles':[{'name':key+' color','kind':'color','token':'color/'+key,'alias':'palette/'+key,'value':value} for key,value in colors.items()],'palette':{'samples':samples}}
    foundations['roles'].extend([{'name':'Reading size','kind':'typography','token':'type/body','alias':'size/body','value':'15px','source_values':['15px'],'native':{'type':'FLOAT','value':15,'bindings':type_bindings}},{'name':'Reading family','kind':'typography','token':'type/family/body','alias':'font/family/body','value':'Hahmlet','source_values':['Hahmlet'],'native':{'type':'STRING','value':'Hahmlet','bindings':family_bindings}},{'name':'Primary horizontal padding','kind':'spacing','token':'space/control','alias':'padding/control','value':'22px','source_values':['22px'],'native':{'type':'FLOAT','value':22,'bindings':padding_bindings}},{'name':'Control radius','kind':'radius','token':'radius/control','alias':'radius/base','value':'0px','source_values':['0px'],'native':{'type':'FLOAT','value':0,'bindings':radius_bindings}}])
    primary={'publichome':'browse-classes','memberhome':'browse-classes','login':'login-submit','signup':'signup-submit','sessionavailable':'reserve-preview','review':'reserve','confirmed':'reschedule','waitlisted':'bookings','mybookings':'booking-detail','cancelconfirm':'confirm-cancel','cancelled':'sessions','reschedule':'confirm-reschedule','conflict':'conflict-recover','notifications':'notification-read','staffdashboard':'session-create','staffsessions':'session-create','staffcreate':'session-save','staffroster':'session-edit','staffedit':'session-save','staffaudit':'staff-dashboard','403':'sessions','404':'sessions'}
    for current in nodes:
        if current['type']=='screen':
            actions=[n for n in nodes if n['type']=='action' and n.get('source_screen')==current['id']]
            chosen=next((n for n in actions if n.get('web_action')==primary[current['id'].removeprefix('screen-')]),actions[0] if actions else None)
            if chosen:current['annotation']['first_action']=chosen['id']
    graph={'version':1,'stage':'draft','scope':'Real Django production application; actual captured SSR geometry, acceptance/native execution pending.','nodes':nodes,'edges':edges,'design_foundations':foundations,'draft_prototype':{'entry_state':'state-publichome','entry_states':['state-publichome','state-mybookings','state-staffdashboard','state-conflict','state-waitlisted','state-403','state-404'],'viewports':[{'id':'desktop','width':1200,'height':900},{'id':'mobile','width':390,'height':960}],'states':prototype_states,'bindings':bindings}}
    write_json(ROOT/'graph.json',graph)
    candidate={'id':'littlehands','graph':{'path':'graph.json','sha256':sha(ROOT/'graph.json')},'colors':colors,'fonts':{'display':{'family':'Hahmlet','style':'Bold'},'body':{'family':'Hahmlet','style':'Regular'}},'layouts':{vp:states['state-publichome'] for vp,states in state_layouts.items() if 'state-publichome' in states},'state_layouts':state_layouts,'control_styles':styles}
    for vp in ('desktop','mobile'):
        preview=ROOT/'previews'/('littlehands-'+vp+'.jpg')
        if preview.is_file():assets['reference-'+vp]={'path':preview.relative_to(ROOT).as_posix(),'sha256':sha(preview),'reference':True}
    write_json(ROOT/'input-pins.json',{'schema':'little-hands-design-input-pins-v1','source':[{'path':'../'+path.relative_to(APP).as_posix(),'sha256':sha(path)} for path in [APP/'ARCHITECTURE.md',APP/'booking/views.py',APP/'booking/services.py',APP/'static/littlehands/app.css',APP/'static/littlehands/app.js',*sorted((APP/'templates').rglob('*.html'))]],'captures':[{'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)} for data,path in captures.values()]})
    write_json(ROOT/'native-layout.json',{'schema':'figma-flow-authored-native-layout-v1','scope':'exploratory-only','production_admitted':False,'content':{'path':'content.json','sha256':sha(ROOT/'content.json')},'assets':assets,'candidates':[candidate]})
    write_json(ROOT/'dom-map.json',{'schema':'little-hands-source-dom-map-v1','controls_and_layers':mappings,'transport_alias_resolutions':[row for data,path in captures.values() for row in data.get('_transport_alias_resolutions',[])],'scope':'Original actual DOM selectors map to state-prefixed source/native keys. No runtime/native verification claim.'})
    missing=[{'state':'state-'+row[0],'viewport':vp} for row in STATES for vp in ('desktop','mobile') if ('state-'+row[0],vp) not in captures]
    write_json(ROOT/'source-status.json',{'schema':'little-hands-design-source-status-v1','actual_captures':len(captures),'unverified_ua_internals':unverified_ua_internals,'metadata_pending':metadata_pending,'stylesheet_epochs':stylesheet_epochs,'current_manifest_stylesheet':current_stylesheet,'source_epoch_current':stylesheet_current,'pending_measurements':missing,'pending_previews':[p for p in ('previews/littlehands-desktop.jpg','previews/littlehands-mobile.jpg') if not (ROOT/p).is_file()],'native_handoff':'pending','visual_quality':'unverified','approval':'not-recorded','graph_acceptance':'unverified'})
    tools_dir=ROOT.parents[2]/'tools'
    if str(tools_dir) not in sys.path:sys.path.insert(0,str(tools_dir))
    from specification_contract import derive_specifications,render_screen_spec
    write_json(ROOT/'specifications.json',{'schema':'figma-flow-specification-export-v1','source_graph':{'path':'graph.json','sha256':sha(ROOT/'graph.json')},'specifications':derive_specifications(graph,source_graph_sha256=sha(ROOT/'graph.json'))})
    (ROOT/'screen-spec.md').write_text(render_screen_spec(graph,source_graph_sha256=sha(ROOT/'graph.json')))
    notes_html=[]
    for current in nodes:
        if current['type'] not in ('screen','action'):continue
        meaning=current['annotation']; target=meaning.get('control_id',current['id'])
        notes_html.append('<article><a href="index.html#'+target+'">'+html.escape(current['title'])+'</a>'+''.join('<p>'+html.escape(field+': '+value)+'</p>' for field,value in meaning.items() if isinstance(value,str))+'</article>')
    foundation_html=''.join('<p>'+html.escape(' · '.join(str(role[key]) for key in ('name','kind','token','value')))+'</p>' for role in foundations['roles'])+''.join('<p>'+html.escape(' · '.join(str(sample[key]) for key in ('label','component','variant','action','state'))+' · '+' · '.join(sample['useCases']))+'</p>' for sample in samples)
    (ROOT/'app/inspect.html').write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>작은손 단일안 검토</title><link rel="stylesheet" href="'+stylesheet+'"></head><body><main class="page"><div class="wrap"><h1>작은손 커피공방</h1><p>실제 Django 화면을 전달하는 단일 제안입니다. 사용자의 아트 선택·실제 시각 비평·네이티브 인수는 아직 기록하지 않았습니다.</p><p><a href="index.html">실제 화면 소스</a> · <a href="../screen-spec.md">화면 명세</a> · <a href="../source-status.json">누락된 실제 근거</a></p><h2>서체와 색상</h2><p>Hahmlet Regular400 · 본문과 조작</p><h2>Hahmlet Bold700 · 제목</h2>'+''.join('<p style="border-left:24px solid '+value+';padding-left:16px">'+html.escape(key+' '+value)+'</p>' for key,value in colors.items())+'<h2>조작 표본</h2>'+''.join('<p>'+html.escape(sample['label'])+' · '+html.escape(sample['variant'])+'</p>' for sample in samples)+'<p>계획된 디자인 소스와 주석이며 네이티브 검증 결과가 아님.</p>'+''.join(notes_html)+foundation_html+'<h2>실제 캡처</h2><img src="../previews/littlehands-desktop.jpg" alt="실제 데스크톱 화면"><img src="../previews/littlehands-mobile.jpg" alt="실제 모바일 화면"><p>사진은 붉은 바탕 위 흰 커피잔과 긴 그림자입니다. 통계·일정·이름·예약 상태는 실제 SSR 데이터에서만 가져옵니다.</p></div></main></body></html>')
    print(json.dumps({'actual_captures':len(captures),'pending_measurements':len(missing),'actions':len(seen_actions),'geometry':'actual DOM only','design_completion':'not-claimed'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static-root',type=Path,help='Actual Django collected static root; referenced bytes are copied with their hashed tree.')
    args=parser.parse_args()
    if args.static_root:STATIC_ROOT=args.static_root.resolve()
    build()
