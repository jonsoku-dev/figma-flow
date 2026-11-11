#!/usr/bin/env python3
"""Admit visible exploratory directions and exact human selection before production.

No hooks, GUI automation, shell evaluation, default choice or automatic approval.
Known managed transcript records are recognized locally, not cryptographic identity proof.
"""
import hashlib
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import parse_qs, urlsplit

import workflow
from workflow import State, Event, Guard, VerifiedFact


class SelectionRequired(ValueError):
    def __init__(self, message, state=None):
        super().__init__(message)
        self.state = state
        self.required_boundary = State.WAIT_SELECTION


def assert_workflow_sync():
    import sync_workflow
    if sync_workflow.check() or digest(workflow.load_graph()) != workflow.graph_hash():
        raise ValueError('Canonical workflow/generated consumers drift; run sync_workflow.py and restart the command')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def pin(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000_000:
        raise ValueError('Regular bounded input required: ' + str(path))
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def current(record, base=None):
    if not isinstance(record, dict) or not isinstance(record.get('path'), str):
        raise ValueError('Current path/hash record required')
    path = Path(record['path'])
    if not path.is_absolute():
        if base is None:
            raise ValueError('Relative record needs its declared source base')
        path = Path(base) / path
    if pin(path)['sha256'] != record.get('sha256'):
        raise ValueError('Stale/missing input hash: ' + str(path))
    return path.absolute()


def status(manifest_path, selection_path=None):
    """Read-only explanation of a direction review: state, input freshness, next events. Never writes or selects."""
    import sync_workflow
    data = json.loads(Path(manifest_path).read_text())
    if data.get('schema') != 'figma-flow-design-directions-v1':
        raise ValueError('Not a direction review manifest')
    base = data.get('project_root')
    inputs = []

    def check(role, record, candidate=None):
        if not isinstance(record, dict) or not isinstance(record.get('path'), str):
            return
        path = Path(record['path'])
        if not path.is_absolute() and base:
            path = Path(base) / path
        try:
            state = 'current' if pin(path)['sha256'] == record.get('sha256') else 'stale'
        except (OSError, ValueError):
            state = 'missing'
        inputs.append({'role': role, 'candidate_id': candidate, 'path': str(path), 'status': state})
    for role in ('brief', 'research', 'content', 'agent_review', 'review_surface', 'comparison_image', 'native_layout'):
        check(role, data.get(role))
    for candidate in data.get('candidates', []):
        for role in ('source', 'review', 'product_graph'):
            check(role, candidate.get(role), candidate.get('id'))
        for preview in candidate.get('previews', []):
            check('preview-' + str(preview.get('viewport')), preview.get('file', preview), candidate.get('id'))
    state = State(data['workflow_state'])
    guards = {row['id']: row for row in workflow._GRAPH['guards']}
    next_events = [{'event': edge['event'], 'to': edge['to'],
                    'guards': [{'id': g, 'authority': guards[g]['authority'], 'requires_actual_user_turn': guards[g]['authority'] == 'human'}
                               for g in edge.get('guards', [])]}
                   for edge in workflow._GRAPH['edges'] if edge['from'] == state.value]
    selection = None
    if selection_path:
        try:
            verified = require_selected(selection_path)
            selection = {'status': 'verified', 'candidate_id': verified.get('candidate_id'), 'candidate_sha256': verified.get('candidate_sha256')}
        except SelectionRequired as exc:
            selection = {'status': 'not-admitted', 'reason': str(exc)}
    graph = 'current' if data.get('workflow_graph_sha256') == workflow.graph_hash() else 'outdated'
    counts = {name: sum(1 for item in inputs if item['status'] == name) for name in ('current', 'stale', 'missing')}
    return {'workflow_state': state.value, 'workflow_symbol': state.name, 'review_id': data.get('review_id'), 'graph': graph,
            'sync_drift': sync_workflow.check(), 'inputs': inputs, 'next_events': next_events, 'selection': selection, 'writes': [],
            'notice': 'status는 상태 설명일 뿐 선택·승인·전이가 아닙니다. 사람 guard는 실제 사용자 턴이 필요합니다.',
            'summary': f"{state.value}: current {counts['current']}, stale {counts['stale']}, missing {counts['missing']}; workflow graph {graph}"}


def read(record):
    return json.loads(current(record).read_text())


class Source(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags, self.text, self.script, self.inside = [], [], [], None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.inside = tag
        else:
            self.tags.append(tag)

    def handle_endtag(self, tag):
        if tag == self.inside:
            self.inside = None

    def handle_data(self, text):
        if self.inside == 'script':
            self.script.append(text)
        elif self.inside is None:
            self.text.append(text)


def _image(record):
    from PIL import Image, ImageFilter
    path = current(record)
    with Image.open(path) as source:
        source.verify()
    with Image.open(path) as source:
        size = source.size
        image = source.convert('L').resize((64, 96)).filter(ImageFilter.FIND_EDGES)
        # Shape evidence, deliberately insensitive to a simple palette swap.
        pixels = list(image.tobytes())
        threshold = max(24, sorted(pixels)[int(len(pixels) * .85)])
        return size, [value > threshold for value in pixels]


def _product_graph_errors(graph):
    """Schema errors the production bundle would raise for this exact graph, checked before a human selects it."""
    import sys
    scripts = str(Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import graph as product_graph
    errors, _ = product_graph.validate_graph(graph)
    return errors


def _layout_signature(html):
    properties = re.compile(r'\b(position|display|width|height|min-width|max-width|min-height|max-height|inset(?:-\w+)?|top|right|bottom|left|margin(?:-\w+)?|padding(?:-\w+)?|gap|row-gap|column-gap|grid(?:-\w+)?|flex(?:-\w+)?|align-items|align-content|align-self|justify-content|justify-items|justify-self|order|overflow(?:-\w+)?|transform|aspect-ratio)\s*:\s*([^;{}]+)', re.I)
    styles = '\n'.join(re.findall(r'<style\b[^>]*>(.*?)</style\s*>', html, re.I | re.S))
    return sorted((name.lower(), re.sub(r'\s+', ' ', value.strip().lower()))
                  for name, value in properties.findall(styles))


def _candidate(candidate, content):
    import annotation_contract
    import design_foundations
    html = current(candidate['source']).read_text()
    overlay = current(candidate['review']).read_text()
    graph = read(candidate['product_graph'])
    schema_errors = _product_graph_errors(graph)
    if schema_errors:
        raise ValueError('Candidate product graph would be rejected by production (design_bundle/design_graph); fix it before review: ' + '; '.join(schema_errors[:8]))
    notes = annotation_contract.derive_notes(graph)
    source_path, review_path = current(candidate['source']), current(candidate['review'])
    relative_source = os.path.relpath(source_path, review_path.parent) if source_path != review_path else ''
    for note in notes:
        note['target'] = relative_source + '#' + note['target_id']
    note_report = annotation_contract.validate_notes(notes, graph, stage='draft', source_html={relative_source: html}, review_html=overlay)
    if not note_report['passed']:
        raise ValueError('Draft semantic notes invalid: ' + json.dumps(note_report['errors'], ensure_ascii=False))
    foundation = design_foundations.derive_foundations(graph)
    foundation_report = design_foundations.validate_foundations(None, foundation, stage='plan')
    if not foundation_report['ok']:
        raise ValueError('Draft token/component palette proposal invalid: ' + json.dumps(foundation_report['failures'], ensure_ascii=False))
    foundation_review = design_foundations.validate_foundations_review(foundation, overlay)
    if not foundation_review['ok']:
        raise ValueError('Draft palette/token roles not visibly reviewed: ' + json.dumps(foundation_review['failures'], ensure_ascii=False))
    source = Source(html)
    visible = re.sub(r'\s+', ' ', ' '.join(source.text))
    for text in content.get('required_text', []):
        if re.sub(r'\s+', ' ', text) not in visible:
            raise ValueError('Candidate omits shared representative content: ' + text)
    if len(content.get('required_text', [])) < 2:
        raise ValueError('Shared representative content needs at least two actual text anchors')
    previews = candidate.get('previews', [])
    if {p.get('viewport') for p in previews} != {'mobile', 'desktop'}:
        raise ValueError('Actual mobile and desktop visible direction artifacts required')
    images = {}
    for preview in previews:
        size, edges = _image(preview['file'])
        if list(size) != [preview['width'], preview['height']]:
            raise ValueError('Direction raster viewport differs from actual artifact')
        if not (240 <= size[0] <= 600 if preview['viewport'] == 'mobile' else size[0] >= 1000):
            raise ValueError('Invalid comparable direction viewport')
        images[preview['viewport']] = {'size': size, 'edges': edges, 'sha256': preview['file']['sha256']}
    script = re.sub(r'/\*.*?\*/|//[^\n]*', '', '\n'.join(source.script), flags=re.S)
    script = re.sub(r'([\"\']).*?\1', 'STRING', script, flags=re.S)
    signatures = {'structure': digest({'tags': source.tags, 'layout': _layout_signature(html)}), 'interaction': digest(re.findall(r'[A-Za-z_$][\w$]*|[{}()[\].;=+!?:<>]+', script))}
    expected = digest({key: candidate[key] for key in ('id', 'title', 'composition', 'typography', 'interaction', 'source', 'review', 'product_graph', 'previews')})
    if candidate.get('sha256') != expected:
        raise ValueError('Candidate definition/hash changed')
    return {'candidate': candidate, 'images': images, 'signatures': signatures, 'notes': notes,
            'note_report': note_report, 'foundations': foundation, 'foundation_report': foundation_report}


def review_packet_sha256(data):
    keys = ('review_id', 'workflow_graph_sha256', 'project_root', 'brief', 'research', 'content', 'candidates', 'agent_review', 'review_destination', 'native_target', 'native_layout')
    return digest({key: data.get(key) for key in keys})


def _requests_figma(text):
    from review_destination import resolve
    return resolve(text) == 'figma'


def _figma_scope(data):
    declared = data.get('review_destination')
    if declared not in ('local', 'figma'):
        raise ValueError('Explicit local/figma review destination required')
    graph_requires = any(read(c['product_graph']).get('requires_figma') or
        any(n.get('type') == 'figma' for n in read(c['product_graph']).get('nodes', [])) for c in data['candidates'])
    from review_destination import resolve
    return resolve(current(data['brief']).read_text(), explicit=declared, graph_requires=graph_requires) == 'figma'


def _native_review(manifest, data, readback_path=None):
    import figma_draft
    record = data.get('native_review', {})
    path = Path(readback_path) if readback_path else current(record.get('readback'))
    if record and record.get('packet_sha256') != review_packet_sha256(data):
        raise ValueError('Native draft review belongs to outdated direction/candidate bytes')
    report = figma_draft.verify_native_review(Path(manifest), path)
    if not report.get('passed'):
        raise ValueError('Actual native draft review evidence incomplete: ' + json.dumps(report.get('errors'), ensure_ascii=False))
    if not report.get('file_key') or not report.get('page_id'):
        raise ValueError('Actual native review file/page identity required')
    return report


def validate_draft(path, *, require_agent_review=True, _data=None, require_native_review=True):
    path = Path(path).absolute()
    data = _data if _data is not None else json.loads(path.read_text())
    if data.get('schema') != 'figma-flow-design-directions-v1' or data.get('workflow_graph_sha256') != workflow.graph_hash():
        raise ValueError('Unknown/outdated direction workflow graph')
    phase = State(data['workflow_state'])
    project = Path(data['project_root']).resolve()
    records = [data['brief'], data['research'], data['content']]
    if data.get('agent_review'):
        records.append(data['agent_review'])
    if data.get('review_surface'):
        records.append(data['review_surface'])
    if data.get('comparison_image'):
        records.append(data['comparison_image'])
    if data.get('native_layout'):
        records.append(data['native_layout'])
    for candidate in data.get('candidates', []):
        records.extend(candidate[k] for k in ('source', 'review', 'product_graph'))
        records.extend(p['file'] for p in candidate.get('previews', []))
    if any(not Path(record['path']).resolve().is_relative_to(project) for record in records):
        raise ValueError('Candidate input escapes the declared project root')
    native_scope = _figma_scope(data)
    current(data['brief']); current(data['research'])
    content = read(data['content'])
    candidates = data.get('candidates', [])
    if len(candidates) not in (2, 3) or len({c.get('id') for c in candidates}) != len(candidates):
        raise ValueError('Exactly two or three independent visible candidates required')
    checked = [_candidate(candidate, content) for candidate in candidates]
    if native_scope and data.get('native_layout'):
        from draft_token_plan import foundation_bindings
        layout = read(data['native_layout'])
        proposed = {row['id']: row for row in layout['candidates']}
        if len(proposed) != len(layout['candidates']) or set(proposed) != {c['id'] for c in candidates}:
            raise ValueError('Expected one authored native layout per reviewed direction')
        for candidate in candidates:
            foundation_bindings(proposed[candidate['id']], read(candidate['product_graph']))
    for index, first in enumerate(checked):
        for second in checked[index + 1:]:
            for field in ('composition', 'typography', 'interaction'):
                if first['candidate'][field].strip().casefold() == second['candidate'][field].strip().casefold():
                    raise ValueError('Direction alternatives must materially distinguish composition, type and interaction framing')
            if first['signatures'] == second['signatures']:
                raise ValueError('Cosmetic duplicate source/interaction structure is not an independent direction')
            for viewport in ('mobile', 'desktop'):
                a, b = first['images'][viewport], second['images'][viewport]
                if a['size'] != b['size']:
                    raise ValueError('Compare all concepts at the same representative viewport')
                distance = sum(x != y for x, y in zip(a['edges'], b['edges'])) / len(a['edges'])
                if a['sha256'] == b['sha256'] or distance < .025:
                    raise ValueError('Same-byte/cosmetic direction images do not establish distinct composition')
    if require_agent_review:
        review = read(data.get('agent_review'))
        if review.get('role') != 'agent' or review.get('draft_content_sha256') != digest(candidates):
            raise ValueError('Current concrete agent review of executed artifacts required')
        observations = review.get('candidates', [])
        if {r.get('id') for r in observations} != {c['id'] for c in candidates}:
            raise ValueError('Agent must inspect every actual direction artifact')
        for candidate in candidates:
            item = next(r for r in observations if r['id'] == candidate['id'])
            if item.get('candidate_sha256') != candidate['sha256'] or any(not isinstance(item.get(k), str) or not item[k].strip() for k in ('composition', 'typography', 'interaction', 'truth_and_notes')):
                raise ValueError('Generic/stale agent judgement is not concrete direction review')
    if require_agent_review:
        surface = current(data['review_surface'])
        if surface.read_text() != _gallery(data, surface.parent):
            raise ValueError('Displayed review surface differs from exact candidate links/images')
    if require_agent_review and require_native_review and native_scope and phase == State.WAIT_SELECTION:
        _native_review(path, data)
    record = pin(path) if path.is_file() else {'path': str(path), 'sha256': digest(data)}
    return {'data': data, 'draft': record, 'checked': checked}


def user_record_root():
    return Path.home() / '.codex/sessions'


def _messages(path):
    hasher, offset = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for line in stream:
            offset += len(line)
            hasher.update(line)
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get('payload', {})
            role, text = None, ''
            if record.get('type') == 'response_item' and payload.get('type') == 'message':
                role = payload.get('role')
                text = '\n'.join(c.get('text', '') for c in payload.get('content', []) if isinstance(c, dict))
            elif record.get('type') == 'response_item' and payload.get('type') == 'function_call' and payload.get('name', '').split('.')[-1] in ('request_user_input', 'request_user_input_async'):
                role, text = 'assistant', payload.get('arguments', '')
            elif record.get('type') == 'event_msg' and payload.get('type') in ('user_message', 'agent_message'):
                role = 'user' if payload['type'] == 'user_message' else 'assistant'
                text = payload.get('message', '')
            if role in ('user', 'assistant'):
                yield {'role': role, 'text': text, 'prefix_length': offset, 'prefix_sha256': hasher.hexdigest(),
                       'timestamp': record.get('timestamp'),
                       'visible_final': record.get('type') == 'response_item' and payload.get('type') == 'message'
                       and role == 'assistant' and payload.get('phase') == 'final_answer'}


def _title_choice(candidates, text):
    """Recognize a leading exact title and a bounded affirmative Korean decision."""
    mentioned = []
    for candidate in candidates:
        names = (candidate['id'], candidate['title'])
        if any(re.search(r'(?<![\w-])' + re.escape(name) + r'(?![A-Za-z0-9_-])', text, re.I) for name in names):
            mentioned.append(candidate)
    if len(mentioned) != 1:
        return None
    candidate = mentioned[0]
    title = re.escape(candidate['title'])
    subject = '(?:' + '|'.join((title, '"' + title + '"', "'" + title + "'", '“' + title + '”', '‘' + title + '’', '「' + title + '」')) + ')'
    decision = (r'(?:선택(?:해\s*줘|해\s*주세요|할게(?:요)?|하겠습니다)|'
                r'(?:본제작(?:까지|으로)?\s*)?진행(?:해\s*줘|해\s*주세요|하자|할게(?:요)?))')
    if not re.fullmatch(subject + r'(?:(?:으로|로|을|를)\s*|\s+)' + decision + r'(?:[.!。]\s*[\s\S]*)?', text):
        return None
    if re.search(r'(?:선택|결정|진행|본제작|제작)[^.!。\n]{0,16}(?:하지\s*(?:마|말)|하지\s*않|보류|취소|나중)', text):
        return None
    if re.search(r'잠깐|보류|취소|아니[,，]|(?:아직|나중)[^.!。\n]{0,12}(?:시작|진행|제작)|둘\s*다|전부\s*(?:같이\s*)?(?:제작|진행)', text):
        return None
    return candidate


def _native_presentation(text, candidates, report, observed_at, presented_at):
    """Require labeled links for every candidate in the actual verified native review."""
    if report.get('passed') is not True or not report.get('file_key'):
        return False
    try:
        observed = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
        presented = datetime.fromisoformat(presented_at.replace('Z', '+00:00'))
        if observed.tzinfo is None or presented.tzinfo is None or observed > presented:
            return False
    except (AttributeError, TypeError, ValueError):
        return False
    visible = re.sub(r'```[\s\S]*?```|`[^`\n]*`', '', text)
    links = re.findall(r'(?<!!)\[([^]\n]+)\]\((https://[^\s<>]+)\)', visible)
    shown = set()
    for label, target in links:
        parsed = urlsplit(target)
        parts = parsed.path.strip('/').split('/')
        if (parsed.hostname not in ('figma.com', 'www.figma.com') or len(parts) < 2 or
                parts[0] not in ('design', 'file') or parts[1] != report['file_key']):
            continue
        nodes = parse_qs(parsed.query).get('node-id', [])
        if len(nodes) != 1:
            continue
        node_id = nodes[0].replace('-', ':')
        for candidate in candidates:
            labels = (candidate['title'], candidate['id'])
            if not any(re.fullmatch(re.escape(name) + r'(?:\s+Figma)?', label.strip(), re.I) for name in labels):
                continue
            if any(row.get('id') == node_id and row.get('key', '').startswith(candidate['id'] + '.')
                   for row in report.get('screens', [])):
                shown.add(candidate['id'])
    return shown == {candidate['id'] for candidate in candidates}


def _human(draft, source, *, expected=None):
    path = Path(source).absolute()
    if not path.resolve().is_relative_to(user_record_root().resolve()) or path.is_symlink() or not path.is_file():
        raise ValueError('Actual managed user-turn evidence required; self-written approval declarations are not admitted')
    messages = _messages(path)
    data, draft_pin = draft['data'], draft['draft']
    presented, answer, recorded, revoked_at = False, None, None, 0
    native_report, native_anchor, observed_at = None, False, None
    by_id = {c['id'].casefold(): c for c in data['candidates']}
    for message in messages:
        if message['role'] == 'assistant' and data['review_id'] in message['text'] and draft_pin['sha256'] in message['text']:
            presented, native_anchor = True, False
        elif message['role'] == 'assistant' and message['visible_final'] and 'figma.com/' in message['text'] and data.get('review_destination') == 'figma' and data.get('native_review'):
            if native_report is None:
                native_report = _native_review(draft_pin['path'], data)
                observed_at = read(data['native_review']['readback']).get('observed_at')
            matches = _native_presentation(message['text'], data['candidates'], native_report, observed_at, message['timestamp'])
            if matches or native_anchor:
                presented, native_anchor = matches, True
        if message['role'] != 'user':
            continue
        text = message['text'].strip()
        wrapped = re.fullmatch(r'<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>', text, re.S)
        if wrapped:
            try:
                replies = json.loads(wrapped.group(1))
            except ValueError:
                replies = []
            if len(replies) == 1 and isinstance(replies[0], dict):
                question = replies[0].get('question', '')
                if data['review_id'] in question and draft_pin['sha256'] in question and replies[0].get('questionItemId'):
                    presented = True
                    text = replies[0].get('answer', '')
                else:
                    continue
            else:
                continue
        if not presented or not isinstance(text, str):
            continue
        if re.search(r'\breselect\b|\brevoke\b|^rework$|\brework\s+(?:the\s+)?(?:directions?|selection)\b|cancel.*selection|선택\s*취소|'
                     r'다시\s*(?:선택|고를)(?!\s*(?:할\s*)?필요\s*없|.{0,4}안\s*해도)(?:할게|하겠|해\s*줘|하자|할래|래|게)|(?:시안|방향)(?:을|를)?\s*다시\s*(?:선택|고르)(?!.{0,6}(?:필요\s*없|안\s*해도))|'
                     r'^(?:reject|none|둘다아니|전부거절)$', text, re.I):
            revoked_at = message['prefix_length']
            answer = None
            continue
        # Legacy exact IDs remain valid; title prose must be an unambiguous affirmative decision.
        matched = next((c for identity, c in by_id.items() if re.fullmatch(re.escape(identity) + r'(?:\s+' + re.escape(c['sha256']) + r')?', text.strip(), re.I)), None)
        if matched is None:
            matched = _title_choice(data['candidates'], text)
        if matched:
            answer = dict(message, candidate=matched)
            if expected and message['prefix_length'] == expected.get('prefix_length'):
                recorded = answer
    if answer is None:
        raise ValueError('No actual exact user selection after current presentation, or choice was revoked')
    if expected is not None:
        if recorded is None or recorded['prefix_length'] <= revoked_at or answer['candidate']['id'] != recorded['candidate']['id']:
            raise ValueError('Selection was revoked or superseded by a newer actual choice')
        answer = recorded
    result = {'path': str(path), 'prefix_length': answer['prefix_length'], 'prefix_sha256': answer['prefix_sha256'],
              'text_sha256': hashlib.sha256(answer['text'].encode()).hexdigest(), 'candidate_id': answer['candidate']['id']}
    if expected is not None and result != expected:
        raise ValueError('User selection source prefix changed')
    return result, answer['candidate']


def _no_assets(selected):
    data = validate_draft(selected['draft_path'])['data']
    graph = read(selected['product_graph'])
    brief = current(data['brief']).read_text()
    source = current(selected['candidate']['source']).read_text()
    declared = graph.get('asset_roles') or graph.get('production_assets') or graph.get('game_id')
    if declared or re.search(r'game|게임|ゲーム|\blogos?\b|\bicons?\b|로고|아이콘|캐릭터|키아트|key.art', brief, re.I) or re.search(r'<img\b|\.png|\.jpe?g', source, re.I):
        raise ValueError('Selected scope requires actual asset production; no-asset branch denied')
    return data, graph


def verify_asset_pack(selection_path, batch_path, receipts_path):
    from PIL import Image
    import design_review
    selected = require_selected(selection_path)
    batch_path, receipts_path = Path(batch_path).absolute(), Path(receipts_path).absolute()
    batch = json.loads(batch_path.read_text())
    _resolver(Guard.BATCH_CURRENT, {'selection': selection_path, 'batch_path': batch_path, 'batch': batch})
    receipts = json.loads(receipts_path.read_text())
    base = (receipts_path.parent / receipts.get('path_base', '.')).resolve()
    roles = {r['id'] for r in batch['roles']}
    assets = receipts.get('assets', [])
    if not assets or {a.get('role_id') for a in assets} != roles:
        raise ValueError('Actual returned files for every frozen role required before native/implementation')
    expected_pins = {key: selected[key] for key in ('selection_sha256', 'candidate_sha256', 'workflow_graph_sha256')}
    expected_pins['product_graph_sha256'] = selected['product_graph']['sha256']
    batch_sha = pin(batch_path)['sha256']
    sources = []
    for asset in assets:
        source = current(asset['source'], base)
        with Image.open(source) as image:
            image.verify()
        generation = asset.get('generation', {})
        event_path = current(generation['evidence'], base)
        event = json.loads(event_path.read_text())
        call, output = event.get('input', {}), event.get('output', {})
        if (asset.get('batch_id') != batch['batch_id'] or generation.get('tool') != 'image_gen.imagegen' or
            event.get('tool') != generation['tool'] or event.get('tool_call_id') != generation.get('tool_call_id') or
            call.get('batch_sha256') != batch_sha or asset['role_id'] not in call.get('role_ids', []) or
            any(call.get(key) != value for key, value in expected_pins.items())):
            raise ValueError('Returned generation is unbound to actual selected batch/role/tool identity')
        managed = Path(event.get('result', {}).get('generated_image_path', output.get('image_path', '')))
        if not managed.is_absolute() or not managed.resolve().is_relative_to(design_review.generated_artifact_root().resolve()) or managed.stem != generation['tool_call_id']:
            raise ValueError('Known original imagegen artifact identity required, not a self-asserted asset receipt')
        original = source.read_bytes()
        if not managed.is_file() or managed.read_bytes() != original or output.get('sha256') != asset['source']['sha256']:
            raise ValueError('Actual returned original bytes/hash differ')
        derivative = current(asset['derivative'], base).read_bytes()
        design_review.verify_derivative(original, derivative, asset['derivative'].get('operations', []))
        sources.append({'role_id': asset['role_id'], 'source': pin(source), 'generation': pin(event_path)})
    return {'selection': selected, 'batch': pin(batch_path), 'receipt': pin(receipts_path), 'sources': sources,
            'boundary': 'Actual local managed artifact/byte chain checked; platform execution authenticity remains separately observed.'}


def verify_native(selection_path, readback_path, contract_path):
    import annotation_contract
    import design_foundations
    import native_handoff
    selected = require_selected(selection_path)
    graph = read(selected['product_graph'])
    data = json.loads(Path(readback_path).read_text())
    expected = json.loads(Path(contract_path).read_text())
    declaration = expected.get('annotation_contract', {})
    if declaration.get('product_graph', graph) != graph:
        raise ValueError('Native semantic contract differs from selected immutable design graph')
    expected['mode'] = 'strict-creation'
    expected['annotation_contract'] = {'mode': 'strict-creation', 'product_graph': graph,
        'notes': declaration.get('notes', annotation_contract.derive_notes(graph))}
    planned = design_foundations.derive_foundations(graph)
    actual_contract = expected.get('design_foundations', planned)
    for field in ('roles',):
        project = lambda rows: [{k: row.get(k) for k in ('name', 'kind', 'token', 'alias', 'value')} for row in rows]
        if project(actual_contract.get(field, [])) != project(planned.get(field, [])):
            raise ValueError('Native foundation meaning differs from selected planned role contract')
    semantic = native_handoff.evaluate(data, expected, expected.get('page_id'))
    foundations = design_foundations.validate_foundations(data, actual_contract, stage='native')
    if not semantic['passed'] or not foundations['ok']:
        raise ValueError('Native semantic/usable palette/type-spacing-radius foundation evidence missing: ' +
                         json.dumps({'semantic': semantic.get('errors'), 'foundations': foundations.get('failures')}, ensure_ascii=False))
    return {'readback': pin(readback_path), 'contract': pin(contract_path), 'semantic': semantic, 'foundations': foundations}


def _resolver(guard, evidence):
    if guard == Guard.BRIEF_CURRENT:
        current(evidence['brief'])
        return VerifiedFact(guard, evidence['brief']['sha256'], evidence['brief']['sha256'], 'controller')
    if guard == Guard.RESEARCH_CURRENT:
        current(evidence['research'])
        return VerifiedFact(guard, evidence['research']['sha256'], evidence['research']['sha256'], 'controller')
    if guard == Guard.CANDIDATES_CURRENT:
        result = validate_draft(evidence['draft'], require_agent_review=evidence.get('require_agent_review', True), _data=evidence.get('draft_data'))
        return VerifiedFact(guard, digest(result['data']['candidates']), result['draft']['sha256'], 'controller')
    if guard == Guard.HUMAN_SELECTION_CURRENT:
        result = require_selected(evidence['selection'])
        return VerifiedFact(guard, result['candidate_sha256'], result['human']['prefix_sha256'], 'human')
    if guard in (Guard.FIGMA_REVIEW_SCOPE, Guard.NON_FIGMA_REVIEW_SCOPE):
        data = evidence.get('draft_data') or validate_draft(evidence['draft'], require_agent_review=False, require_native_review=False)['data']
        native = _figma_scope(data)
        if native != (guard == Guard.FIGMA_REVIEW_SCOPE):
            raise ValueError('Requested native/local review branch contradicts declared destination')
        return VerifiedFact(guard, review_packet_sha256(data), data['brief']['sha256'], 'controller')
    if guard == Guard.NATIVE_REVIEW_CURRENT:
        data = evidence.get('draft_data') or validate_draft(evidence['draft'], require_native_review=False)['data']
        report = _native_review(evidence['draft'], data, evidence.get('native_readback'))
        raw = pin(evidence.get('native_readback') or data['native_review']['readback']['path'])
        return VerifiedFact(guard, review_packet_sha256(data), raw['sha256'], 'controller')
    if guard == Guard.NO_ASSET_SCOPE:
        result = require_selected(evidence['selection'])
        data, graph = _no_assets(result)
        return VerifiedFact(guard, result['product_graph']['sha256'], data['brief']['sha256'], 'controller')
    if guard == Guard.NON_FIGMA_SCOPE:
        result = require_selected(evidence['selection'])
        graph = read(result['product_graph'])
        if any(n.get('type') == 'figma' for n in graph.get('nodes', [])) or graph.get('requires_figma'):
            raise ValueError('Selected graph requires actual native handoff')
        return VerifiedFact(guard, result['product_graph']['sha256'], result['draft_sha256'], 'controller')
    if guard == Guard.NATIVE_CURRENT:
        result = verify_native(evidence['selection'], evidence['native_readback'], evidence['native_contract'])
        return VerifiedFact(guard, result['readback']['sha256'], result['contract']['sha256'], 'controller')
    if guard == Guard.GENERATED_ASSETS_CURRENT:
        result = verify_asset_pack(evidence['selection'], evidence['batch_path'], evidence['asset_receipts'])
        return VerifiedFact(guard, result['batch']['sha256'], result['receipt']['sha256'], 'controller')
    if guard == Guard.BATCH_CURRENT:
        result = require_selected(evidence['selection'])
        batch = evidence.get('batch') or json.loads(Path(evidence['batch_path']).read_text())
        selected = batch.get('design_selection', {})
        expected = {key: result[key] for key in ('selection_sha256', 'candidate_sha256', 'workflow_graph_sha256')}
        expected['product_graph_sha256'] = result['product_graph']['sha256']
        if any(selected.get(key) != value for key, value in expected.items()):
            raise ValueError('Batch lacks exact admitted user selection/candidate hashes')
        source_base = Path(evidence['batch_path']).absolute().parent if evidence.get('batch_path') else None
        current(batch['concept'], source_base)
        for reference in batch.get('references', []):
            current(reference, source_base)
        if not batch.get('roles'):
            raise ValueError('Complete planned batch roles required')
        return VerifiedFact(guard, digest(batch), result['selection_sha256'], 'controller')
    raise ValueError('No trusted executable verifier for requested workflow guard: ' + guard.name)


def _gallery(data, out):
    from direction_review_surface import render_surface
    return render_surface(data, out)


def _write_surface(data, out):
    from direction_review_surface import write_surface
    return write_surface(data, out)


def create_draft(project, brief, research, spec, out, *, judgement=None, review_destination=None):
    assert_workflow_sync()
    project, out = Path(project).resolve(), Path(out).absolute()
    if not out.resolve().is_relative_to(project):
        raise ValueError('Draft output must stay inside selected project')
    def located(value):
        path = Path(value)
        path = path if path.is_absolute() else project / path
        if path.is_symlink() or not path.resolve().is_relative_to(project):
            raise ValueError('Candidate input escapes declared project root or is a symlink')
        return path.resolve()
    brief_pin, research_pin = pin(located(brief)), pin(located(research))
    if not current(research_pin).read_text().strip():
        raise ValueError('Actual brief/research precedes direction candidates')
    stage = workflow.transition(State.BRIEF, Event.RESEARCH, evidence={'brief': brief_pin}, resolver=_resolver)
    source = json.loads(located(spec).read_text()) if not isinstance(spec, dict) else spec
    content = pin(located(source['content']['path']))
    candidates = []
    for item in source.get('candidates', []):
        candidate = {key: item[key] for key in ('id', 'title', 'composition', 'typography', 'interaction')}
        candidate.update(source=pin(located(item['source'])), review=pin(located(item['review'])), product_graph=pin(located(item['graph'])),
                         previews=[dict(viewport=p['viewport'], width=p['width'], height=p['height'], file=pin(located(p['path']))) for p in item['previews']])
        candidate['sha256'] = digest(candidate)
        candidates.append(candidate)
    from review_destination import resolve
    graph_requires = any(read(c['product_graph']).get('requires_figma') or any(n.get('type') == 'figma' for n in read(c['product_graph']).get('nodes', [])) for c in candidates)
    destination = resolve(current(brief_pin).read_text(), explicit=review_destination or source.get('review_destination'), graph_requires=bool(graph_requires))
    data = {'schema': 'figma-flow-design-directions-v1', 'revision': 1, 'review_id': str(uuid.uuid4()),
            'workflow_graph_sha256': workflow.graph_hash(), 'workflow_state': stage.value, 'workflow_symbol': stage.name,
            'project_root': str(project), 'brief': brief_pin, 'research': research_pin, 'content': content, 'candidates': candidates,
            'review_destination': destination,
            'native_target': source.get('native_target', {'mode': 'current-design-file'} if destination == 'figma' else None),
            'scope': 'exploratory-only', 'native_annotations': 'planned-not-applied',
            'boundary': 'Static supplied artifacts and local managed-event recognition are not cryptographic proof of human identity or GUI execution. Host must show these real artifacts and wait for the actual user turn.'}
    layout_record = source.get('native_layout') or (source.get('native_target') or {}).get('layout')
    if layout_record:
        layout_record = {'path': layout_record} if isinstance(layout_record, str) else layout_record
        actual_layout = pin(located(layout_record['path']))
        if layout_record.get('sha256') and layout_record['sha256'] != actual_layout['sha256']:
            raise ValueError('Authored native layout differs from exact supplied pin')
        target_layout = (data.get('native_target') or {}).get('layout')
        if target_layout and (pin(located(target_layout['path'])) != actual_layout or target_layout.get('sha256', actual_layout['sha256']) != actual_layout['sha256']):
            raise ValueError('Native target/layout references disagree')
        data['native_layout'] = actual_layout
        if target_layout:
            data['native_target']['layout'] = actual_layout
    if judgement:
        data['agent_review'] = pin(located(judgement))
    # All candidate checks and graph transition guards run before any output mutation.
    manifest = out / 'directions.json'
    validate_draft(manifest, require_agent_review=False, _data=data)
    stage = workflow.transition(stage, Event.PREPARE_CANDIDATES,
        evidence={'draft': str(manifest), 'draft_data': data, 'research': research_pin, 'require_agent_review': False}, resolver=_resolver)
    data.update(workflow_state=stage.value, workflow_symbol=stage.name)
    out.mkdir(parents=True, exist_ok=False)
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    surface = _write_surface(data, out)
    if judgement:
        return review_draft(manifest, judgement)
    return {'manifest': str(manifest), 'workflow_state': stage.value, 'workflow_symbol': stage.name,
            'draft_content_sha256': digest(candidates), 'comparison_image': surface['comparison_image'],
            'executed': ['validate-existing-visible-candidates', 'write-exploratory-gallery'],
            'next_action': 'Agent must inspect actual images/notes/palette, record concrete judgement, then run review. No production.'}


def review_draft(manifest, judgement):
    manifest = Path(manifest).absolute()
    data = validate_draft(manifest, require_agent_review=False)['data']
    if State(data['workflow_state']) not in (State.SELECTION_READY, State.NATIVE_REVIEW_PENDING, State.WAIT_SELECTION):
        raise ValueError('Review cannot bypass the canonical candidate phase')
    data['agent_review'] = pin(judgement)
    # A gallery is an exploratory artifact, never production or approval.
    surface = manifest.parent / 'review.html'
    gallery = _gallery(data, manifest.parent)
    data['review_surface'] = {'path': str(surface), 'sha256': hashlib.sha256(gallery.encode()).hexdigest()}
    # Validate jury and current files before changing the owned manifest.
    written = _write_surface(data, manifest.parent)
    data['review_surface'] = pin(written['review_page'])
    data['comparison_image'] = pin(written['comparison_image'])
    validate_draft(manifest, _data=data)
    if State(data['workflow_state']) == State.SELECTION_READY:
        event = Event.PREPARE_NATIVE_DRAFT if _figma_scope(data) else Event.REQUEST_SELECTION
        stage = workflow.transition(State.SELECTION_READY, event,
            evidence={'draft': str(manifest), 'draft_data': data}, resolver=_resolver)
        data.update(workflow_state=stage.value, workflow_symbol=stage.name)
    written = _write_surface(data, manifest.parent)
    data['review_surface'] = pin(written['review_page'])
    data['comparison_image'] = pin(written['comparison_image'])
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    actual = pin(manifest)
    if State(data['workflow_state']) != State.WAIT_SELECTION:
        return {'manifest': str(manifest), 'draft_sha256': actual['sha256'], 'packet_sha256': review_packet_sha256(data),
                'workflow_state': data['workflow_state'], 'workflow_symbol': data['workflow_symbol'],
                'review_page': str(surface), 'comparison_image': written['comparison_image'],
                'executed': ['validate-agent-review', 'write-exploratory-review-surface'],
                'pending': 'Actual native draft import/readback with annotations, foundations and prototype+return is required before human selection.'}
    question = f"Review {data['review_id']}\nManifest SHA256 {actual['sha256']}\n"
    question += '\n'.join(f"{c['id']}: {c['title']} · {c['sha256']}" for c in data['candidates'])
    question += '\nShow these actual candidate images and their review links together. Ask the human which exact candidate to carry forward, then wait. Reply with one candidate id; campaign type numbers or delegation are not style approval.\n'
    (manifest.parent / 'selection-prompt.txt').write_text(question)
    return {'manifest': str(manifest), 'draft_sha256': actual['sha256'], 'workflow_state': data['workflow_state'],
            'workflow_symbol': data['workflow_symbol'], 'review_page': str(surface), 'comparison_image': written['comparison_image'],
            'question': str(manifest.parent / 'selection-prompt.txt'), 'executed': ['validate-agent-review', 'write-human-review-surface'],
            'pending': 'Actual user choice; production remains barred.'}


def record_selection(manifest, user_event, out):
    assert_workflow_sync()
    draft = validate_draft(manifest)
    if State(draft['data']['workflow_state']) != State.WAIT_SELECTION:
        raise ValueError('Current graph does not admit user selection from this phase')
    human, candidate = _human(draft, user_event)
    out = Path(out).absolute()
    if out != Path(manifest).absolute().parent / 'selection.json':
        raise ValueError('Selection must use the current review-owned selection.json endpoint')
    previous = json.loads(out.read_text()) if out.is_file() else None
    if previous and previous.get('schema') == 'figma-flow-design-selection-revocation-v1' and human['path'] == previous.get('revoked_user_source_path') and human['prefix_length'] <= previous['after_user_prefix_length']:
        raise ValueError('A fresh actual user decision is required after reselection')
    if previous and previous.get('schema') not in ('figma-flow-design-selection-v1', 'figma-flow-design-selection-revocation-v1'):
        raise ValueError('Refuse to overwrite foreign selection data')
    if previous and previous.get('schema') == 'figma-flow-design-selection-v1':
        old = previous.get('human', {})
        if previous.get('self_path') != str(out) or not Path(old.get('path', '')).resolve().is_relative_to(user_record_root().resolve()) or Path(old['path']).is_symlink():
            raise ValueError('Foreign/forged prior selection record')
        old_message = next((m for m in _messages(old['path']) if m['prefix_length'] == old.get('prefix_length')), None)
        if old_message is None or old_message['role'] != 'user' or old_message['prefix_sha256'] != old.get('prefix_sha256'):
            raise ValueError('Managed user history was rewritten; cannot replace approval from altered evidence')
        try:
            still_current = require_selected(out)
            if still_current['candidate_sha256'] == candidate['sha256']:
                return still_current
        except SelectionRequired:
            pass
    result = {'schema': 'figma-flow-design-selection-v1', 'self_path': str(out), 'draft': draft['draft'], 'candidate_id': candidate['id'],
              'candidate_sha256': candidate['sha256'], 'human': human, 'workflow_graph_sha256': workflow.graph_hash(),
              'workflow_state': State.SELECTED.value, 'workflow_symbol': State.SELECTED.name,
              'native_review': draft['data'].get('native_review'),
              'review_destination': draft['data']['review_destination'],
              'authority_boundary': 'Known managed user-turn record matched after exact presentation. Local CLI cannot cryptographically authenticate a person; host must have observed the actual user decision.'}
    # The human fact comes from parsed source records, never a caller-provided approval bool.
    def resolver(guard, evidence):
        if guard == Guard.HUMAN_SELECTION_CURRENT:
            _human(draft, user_event, expected=human)
            return VerifiedFact(guard, candidate['sha256'], human['prefix_sha256'], 'human')
        return _resolver(guard, evidence)
    stage = workflow.transition(State.WAIT_SELECTION, Event.SELECT, evidence={'draft': str(manifest)}, resolver=resolver)
    result['workflow_state'] = stage.value
    if previous:
        history = out.parent / 'history'
        history.mkdir(exist_ok=True)
        snapshot = history / (pin(out)['sha256'] + '.json')
        if not snapshot.exists():
            snapshot.write_bytes(out.read_bytes())
        if previous.get('schema') == 'figma-flow-design-selection-v1':
            invalidation = workflow.transition_result(State.SELECTED, Event.RESELECT, evidence={'draft': str(manifest)}, resolver=_resolver)
            result['invalidated_active_records'] = invalidation['invalidates']
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w' if previous else 'x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    return require_selected(out)


def require_selected(selection_path, project_root=None):
    try:
        assert_workflow_sync()
        if not selection_path:
            raise ValueError('Actual user-selected direction required before production')
        selection_pin = pin(selection_path)
        selection = json.loads(Path(selection_path).read_text())
        # Compare normalized lexical paths: a project manifest reaches the record as 'checks/001/../../review/selection.json'.
        if selection.get('self_path') != os.path.normpath(str(Path(selection_path).absolute())):
            raise ValueError('Archived/copied selection records are not the active review endpoint')
        if selection.get('schema') != 'figma-flow-design-selection-v1' or selection.get('workflow_graph_sha256') != workflow.graph_hash() or State(selection['workflow_state']) != State.SELECTED:
            raise ValueError('Unknown/stale selection state or graph')
        draft = validate_draft(current(selection['draft']))
        if State(draft['data']['workflow_state']) != State.WAIT_SELECTION:
            raise ValueError('Direction selection no longer admitted by current review state')
        human, candidate = _human(draft, selection['human']['path'], expected=selection['human'])
        if candidate['id'] != selection.get('candidate_id') or candidate['sha256'] != selection.get('candidate_sha256'):
            raise ValueError('Selected exact candidate/hash mismatch')
        if project_root and Path(project_root).resolve() != Path(draft['data']['project_root']).resolve():
            raise ValueError('Selection belongs to a different project')
        return {'state': State.SELECTED.value, 'workflow_graph_sha256': workflow.graph_hash(), 'draft_path': str(current(selection['draft'])),
                'draft_sha256': selection['draft']['sha256'], 'selection_path': str(Path(selection_path).absolute()),
                'selection_sha256': selection_pin['sha256'], 'candidate_id': candidate['id'], 'candidate_sha256': candidate['sha256'],
                'product_graph': candidate['product_graph'], 'candidate': candidate, 'human': human,
                'review_destination': draft['data']['review_destination'], 'native_review': draft['data'].get('native_review')}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SelectionRequired(f'{State.WAIT_SELECTION.name}: {exc}') from exc


def guard_production(selection_path, *, event=Event.FREEZE_BATCH, batch=None, batch_path=None, asset_receipts=None, product_graph=None, native_readback=None, native_contract=None):
    try:
        selected = require_selected(selection_path)
        if product_graph and pin(product_graph)['sha256'] != selected['product_graph']['sha256']:
            raise ValueError('Production graph differs from exact user-selected candidate')
        evidence = {'selection': str(selection_path), 'batch': batch, 'batch_path': batch_path, 'asset_receipts': asset_receipts, 'native_readback': native_readback, 'native_contract': native_contract}
        if event == Event.FREEZE_BATCH:
            result = workflow.transition_result(State.SELECTED, event, evidence=evidence, resolver=_resolver)
        elif event == Event.GENERATE:
            result = workflow.transition_result(State.BATCH_FROZEN, event, evidence=evidence, resolver=_resolver)
        elif event == Event.HANDOFF_NATIVE:
            if selected['review_destination'] != 'figma' or not selected.get('native_review'):
                raise ValueError('Production native destination requires actual reviewed Figma draft before human choice')
            if batch_path or asset_receipts:
                if not batch_path or not asset_receipts:
                    raise ValueError('Both actual frozen batch and returned generated asset receipts required')
                workflow.transition_result(State.BATCH_FROZEN, Event.GENERATE, evidence=evidence, resolver=_resolver)
                result = workflow.transition_result(State.GENERATION, event, evidence=evidence, resolver=_resolver)
            else:
                result = workflow.transition_result(State.SELECTED, event, evidence=evidence, resolver=_resolver)
        elif event == Event.IMPLEMENT:
            if native_readback or native_contract:
                if not native_readback or not native_contract:
                    raise ValueError('Both actual native readback and resolved strict contract required')
                guard_production(selection_path, event=Event.HANDOFF_NATIVE, batch_path=batch_path,
                                 asset_receipts=asset_receipts, product_graph=product_graph)
                result = workflow.transition_result(State.NATIVE, event, evidence=evidence, resolver=_resolver)
            elif batch_path or asset_receipts:
                if not batch_path or not asset_receipts:
                    raise ValueError('Both actual batch and returned asset files required')
                result = workflow.transition_result(State.GENERATION, event, evidence=evidence, resolver=_resolver)
            else:
                result = workflow.transition_result(State.SELECTED, event, evidence=evidence, resolver=_resolver)
        else:
            raise ValueError('Requested event lacks an executable normal verifier')
        return dict(selected, state=result['state'].value, invalidates=result['invalidates'], event=event.value,
                    effect_status='admitted-not-executed', executed=['verify-current-inputs-and-canonical-transition'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError) as exc:
        if isinstance(exc, SelectionRequired):
            raise
        raise SelectionRequired(f'{State.WAIT_SELECTION.name}: {exc}') from exc


IMPLEMENTATION_NODE_TYPES = {'requirement', 'acceptance', 'code', 'test', 'reference'}
IMPLEMENTATION_MUTABLE_FIELDS = {'status', 'source'}


def implementation_fidelity_errors(selected_graph, implementation_graph):
    """Ways an implementation graph departs from the exact user-selected direction.

    The implementation may only add coverage (requirement/acceptance/code/test/reference nodes and edges
    touching them) and update `status`/`source` of selected nodes. Everything the human reviewed —
    every selected node's other fields, every selected edge, design foundations and the draft prototype —
    must be identical.
    """
    errors = []
    selected_nodes = {n.get('id'): n for n in selected_graph.get('nodes', [])}
    implemented_nodes = {n.get('id'): n for n in implementation_graph.get('nodes', []) if isinstance(n, dict)}
    for identity, node in selected_nodes.items():
        other = implemented_nodes.get(identity)
        if other is None:
            errors.append(f'selected node removed: {identity}')
            continue
        for field in sorted((set(node) | set(other)) - IMPLEMENTATION_MUTABLE_FIELDS):
            if node.get(field) != other.get(field):
                errors.append(f'selected node {identity} changed field {field}')
    for identity, node in implemented_nodes.items():
        if identity not in selected_nodes and node.get('type') not in IMPLEMENTATION_NODE_TYPES:
            errors.append(f'implementation may only add {"/".join(sorted(IMPLEMENTATION_NODE_TYPES))} nodes, not {node.get("type")}: {identity}')
    key = lambda e: (e.get('from'), e.get('to'), e.get('type'))
    selected_edges = {key(e) for e in selected_graph.get('edges', [])}
    implemented_edges = {key(e) for e in implementation_graph.get('edges', []) if isinstance(e, dict)}
    for edge in sorted(selected_edges - implemented_edges, key=str):
        errors.append(f'selected edge removed: {edge[0]} -[{edge[2]}]-> {edge[1]}')
    for edge in sorted(implemented_edges - selected_edges, key=str):
        if edge[0] in selected_nodes and edge[1] in selected_nodes:
            errors.append(f'new edge between selected nodes: {edge[0]} -[{edge[2]}]-> {edge[1]}')
    for field in sorted(set(selected_graph) | set(implementation_graph)):
        if field in ('nodes', 'edges', 'stage', 'scope'):
            continue
        if selected_graph.get(field) != implementation_graph.get(field):
            errors.append(f'selected graph field changed: {field}')
    return errors


def require_implementation_selection(selection_path, product_graph):
    selected = require_selected(selection_path)
    if pin(product_graph)['sha256'] == selected['product_graph']['sha256']:
        return selected
    errors = implementation_fidelity_errors(read(selected['product_graph']), json.loads(Path(product_graph).read_text()))
    if errors:
        raise SelectionRequired('Implementation graph differs from exact user-selected candidate: ' + '; '.join(errors[:6]))
    return selected


def reselect(selection_path):
    selected = require_selected(selection_path)
    path = Path(selection_path).absolute()
    previous = json.loads(path.read_text())
    result = workflow.transition_result(State.SELECTED, Event.RESELECT,
        evidence={'draft': selected['draft_path']}, resolver=_resolver)
    history = path.parent / 'history'
    history.mkdir(exist_ok=True)
    snapshot = history / (selected['selection_sha256'] + '.json')
    if not snapshot.exists():
        snapshot.write_bytes(path.read_bytes())
    # Drop active downstream references, preserve immutable historic evidence; never delete artwork.
    record = {'schema': 'figma-flow-design-selection-revocation-v1', 'self_path': str(path),
              'workflow_graph_sha256': workflow.graph_hash(), 'workflow_state': result['state'].value,
              'workflow_symbol': result['state'].name, 'draft': previous['draft'],
              'after_user_prefix_length': Path(selected['human']['path']).stat().st_size,
              'revoked_user_source_path': selected['human']['path'],
              'invalidated_active_records': result['invalidates'], 'archived_selection': pin(snapshot)}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return record


def admit_native_draft(manifest_path):
    assert_workflow_sync()
    result = validate_draft(manifest_path, require_native_review=False)
    data = result['data']
    if not _figma_scope(data):
        raise ValueError('Native draft action requires explicitly requested native review destination')
    state = State(data['workflow_state'])
    if state == State.SELECTION_READY:
        stage = workflow.transition(state, Event.PREPARE_NATIVE_DRAFT,
            evidence={'draft': str(manifest_path)}, resolver=_resolver)
    elif state == State.NATIVE_REVIEW_PENDING:
        stage = state
    else:
        raise ValueError('Native draft preparation is not admitted from current graph phase')
    return {'state': stage.value, 'workflow_symbol': stage.name, 'workflow_graph_sha256': workflow.graph_hash(),
            'packet_sha256': review_packet_sha256(data), 'manifest': result['draft'], 'candidates': data['candidates'],
            'scope': 'exploratory-only', 'production_admitted': False, 'effect_status': 'admitted-not-executed'}


def verify_native_review(manifest_path, readback_path):
    assert_workflow_sync()
    manifest_path = Path(manifest_path).absolute()
    result = validate_draft(manifest_path, require_native_review=False)
    data = result['data']
    if State(data['workflow_state']) != State.NATIVE_REVIEW_PENDING or not _figma_scope(data):
        raise ValueError('Only requested pending native review can admit actual readback')
    report = _native_review(manifest_path, data, readback_path)
    data['native_review'] = {'readback': pin(readback_path), 'packet_sha256': review_packet_sha256(data),
                             'report': report, 'evidence_boundary': 'Supplied actual native getter evidence; not automatic prototype playback or platform-origin authentication.'}
    stage = workflow.transition(State.NATIVE_REVIEW_PENDING, Event.REQUEST_SELECTION,
        evidence={'draft': str(manifest_path), 'draft_data': data, 'native_readback': str(readback_path)}, resolver=_resolver)
    data.update(workflow_state=stage.value, workflow_symbol=stage.name)
    written = _write_surface(data, manifest_path.parent)
    data['review_surface'], data['comparison_image'] = pin(written['review_page']), pin(written['comparison_image'])
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return review_draft(manifest_path, data['agent_review']['path'])
