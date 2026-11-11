"""Compile graph meaning for display; supplied readback never authenticates origin."""
import copy
import hashlib
import json
import re

from annotation_contract import SEMANTIC_FIELDS, derive_notes


SCHEMA = 'figma-flow-readable-spec-v1'
NATIVE_SCHEMA = 'figma-flow-native-spec-v1'
HUMAN_SCHEMA = 'figma-flow-human-annotation-v1'
DISPLAY_FIELDS = ('purpose', 'precondition', 'behavior', 'result', 'failure', 'journey')
SECTION_FIELDS = ('purpose', 'precondition', 'behavior', 'result', 'failure', 'journey', 'platform_scope')
SECTION_TITLES = {
    'ko': {'summary': '요약', 'purpose': '목적', 'precondition': '사용 조건', 'behavior': '동작', 'result': '결과',
           'failure': '예외와 복구', 'journey': '사용 순서', 'platform_scope': 'Figma·웹 범위'},
    'en': {'summary': 'Summary', 'purpose': 'Purpose', 'precondition': 'Conditions', 'behavior': 'Behavior', 'result': 'Result',
           'failure': 'Errors and recovery', 'journey': 'User flow', 'platform_scope': 'Figma and web scope'},
    'ja': {'summary': '概要', 'purpose': '目的', 'precondition': '利用条件', 'behavior': '動作', 'result': '結果',
           'failure': '例外と復旧', 'journey': '利用手順', 'platform_scope': 'Figma・Webの範囲'},
}
SPEC_LABELS = {'ko': '전체 스펙 보기', 'en': 'View full specification', 'ja': '仕様の詳細を見る'}


def spec_label_prelude():
    """Bind the native runtime to this module's link labels and spec schemas."""
    binding = {'labels': SPEC_LABELS, 'schemas': {'readable': SCHEMA, 'native': NATIVE_SCHEMA, 'human': HUMAN_SCHEMA}}
    return 'var FLOW_SPEC = ' + _json(binding) + ';\nvar FLOW_SPEC_LABELS = FLOW_SPEC.labels;\n'


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _sha(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _meaning_hash(specification):
    fields = ('schema', 'id', 'kind', 'screen_id', 'target_id', 'title', 'meaning', 'trace')
    value = {key: specification[key] for key in fields}
    if specification.get('presentation') == 'connected-spec-v2':
        value.update({key: specification[key] for key in ('presentation', 'locale', 'sections', 'display_text')})
    return _sha(value)


def _projection(meaning, locale):
    if locale not in SECTION_TITLES:
        raise ValueError('specification_locale must be ko, en or ja')
    sections = [{'key': field, 'title': SECTION_TITLES[locale][field], 'body': meaning[field].strip()}
                for field in SECTION_FIELDS if isinstance(meaning.get(field), str) and meaning[field].strip()]
    return sections, '\n\n'.join(section['title'] + '\n' + section['body'] for section in sections)


def connected_annotation_markdown(spec, file_key, text_node_id):
    """Return the connected native annotation markdown and its exact Figma URL."""
    locale = spec.get('locale')
    summary = spec.get('annotation_text')
    if locale not in SPEC_LABELS or not isinstance(file_key, str) or not file_key or not isinstance(text_node_id, str) or not text_node_id:
        raise ValueError('connected annotation requires locale, file key and text node ID')
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError('connected annotation requires a source-grounded summary')
    if len(summary.strip()) > 360:
        raise ValueError('connected annotation summary exceeds 360 characters; add a graph summary')
    from urllib.parse import quote
    url = 'https://www.figma.com/design/' + quote(file_key, safe="~!*'()-._") + '?node-id=' + quote(text_node_id.replace(':', '-'), safe="~!*'()-._")
    return {'markdown': spec['title'] + '\n' + summary.strip() + '\n\n[' + SPEC_LABELS[locale] + '](' + url + ')', 'url': url}


def connected_board_reference(nodes, parents, target_id, specification, *, page_id, source_owner_hash):
    """Find the unique observed, owned full-spec entry, never a metadata-only link."""
    found = []
    for text in nodes.values():
        board = nodes.get(parents.get(text['id']), {})
        marker = board.get('designNoteBoard')
        key = board.get('semanticKey') or board.get('semantic_id') or board.get('key')
        text_key = text.get('semanticKey') or text.get('semantic_id') or text.get('key')
        if (text.get('type') == 'TEXT' and text.get('visible') is not False
                and text.get('hyperlink') == {'type': 'NODE', 'value': target_id}
                and text.get('characters') == specification['title'] + '\n' + specification['display_text']
                and marker == {'pageId': page_id, 'sourceHash': source_owner_hash}
                and parents.get(board.get('id')) == page_id
                and isinstance(key, str) and isinstance(text_key, str) and text_key.startswith(key + ':')):
            found.append({'boardId': board['id'], 'textNodeId': text['id'], 'key': text_key[len(key) + 1:]})
    return found[0] if len(found) == 1 else None


def _trace(graph, node, screen_id, by_id):
    relationships = []

    def links(source, relation, target_type):
        found = []
        for edge in graph.get('edges', []):
            if (isinstance(edge, dict) and edge.get('from') == source and edge.get('type') == relation
                    and by_id.get(edge.get('to'), {}).get('type') == target_type):
                link = {key: edge[key] for key in ('from', 'to', 'type')}
                if link not in relationships:
                    relationships.append(link)
                found.append(edge['to'])
        return sorted(set(found))

    requirements = sorted({edge['from'] for edge in graph.get('edges', [])
                           if isinstance(edge, dict) and edge.get('to') == screen_id
                           and edge.get('type') == 'appears on'
                           and by_id.get(edge.get('from'), {}).get('type') == 'requirement'})
    acceptance, tests = set(), set()
    covered = bool(requirements)
    for requirement in requirements:
        links(requirement, 'appears on', 'screen')
        # Only this screen's relationship belongs to this target's trace.
        relationships[:] = [edge for edge in relationships
                            if edge['type'] != 'appears on' or edge['to'] == screen_id]
        criteria = links(requirement, 'accepted by', 'acceptance')
        covered &= bool(criteria)
        acceptance.update(criteria)
        for criterion in criteria:
            checks = links(criterion, 'checked by', 'test')
            covered &= bool(checks)
            tests.update(checks)
    authority = {}
    if 'source' in node:
        authority['node_source'] = copy.deepcopy(node['source'])
    if 'annotation_authority' in node:
        authority['annotation_authority'] = copy.deepcopy(node['annotation_authority'])
    if 'annotation_authority' in graph:
        authority['graph_annotation_authority'] = copy.deepcopy(graph['annotation_authority'])

    def references(identities):
        return [{key: copy.deepcopy(by_id[identity][key]) for key in
                 ('id', 'type', 'title', 'status', 'source') if key in by_id[identity]}
                for identity in sorted(identities)]

    return {'status': 'complete' if covered else 'partial' if requirements else 'unverified',
            'requirements': references(requirements), 'acceptance': references(acceptance),
            'tests': references(tests),
            'relationships': sorted(relationships, key=lambda edge: (edge['from'], edge['type'], edge['to'])),
            'source_authority': authority,
            'authority_basis': 'canonical-graph-relationships; external references not read'}


def derive_specifications(graph, *, source_graph_sha256=None):
    """Project existing annotations without filling missing meaning from titles."""
    notes = derive_notes(graph)
    if source_graph_sha256 is not None and not re.fullmatch(r'[0-9a-fA-F]{64}', source_graph_sha256):
        raise ValueError('source_graph_sha256 must be a SHA256 hex digest')
    source_hash = source_graph_sha256.lower() if source_graph_sha256 is not None else _sha(graph)
    encoding = 'file-bytes-sha256' if source_graph_sha256 is not None else 'canonical-json-sha256:utf-8:sorted-keys:compact'
    locale = graph.get('specification_locale', 'ko')
    if locale not in SECTION_TITLES:
        raise ValueError('specification_locale must be ko, en or ja')
    by_id = {node['id']: node for node in graph['nodes']}
    specifications = []
    for note in notes:
        node = by_id[note.get('action', note['id'])]
        meaning = {key: copy.deepcopy(note[key]) for key in SEMANTIC_FIELDS if key in note}
        if 'action' in note:
            meaning['action'] = note['action']
        summary = note.get('summary') or note.get('behavior') or note.get('purpose')
        annotation_text = summary.strip()
        if len(annotation_text) > 360:
            raise ValueError('annotation summary exceeds 360 characters; add a graph summary: ' + note['id'])
        sections, display_text = _projection(meaning, locale)
        spec = {'schema': SCHEMA, 'presentation': 'connected-spec-v2', 'locale': locale,
                **{key: note[key] for key in ('id', 'kind', 'screen_id', 'target_id')},
                'title': node.get('title', ''), 'meaning': meaning,
                'annotation_text': annotation_text, 'sections': sections,
                'source_graph_sha256': source_hash, 'source_graph_encoding': encoding,
                'display_text': display_text,
                'trace': _trace(graph, node, note['screen_id'], by_id)}
        spec['meaning_sha256'] = _meaning_hash(spec)
        specifications.append(spec)
    return specifications


def validate_specification(expected, observed, *, native_id=None, semantic_key=None,
                           require_trace=True, require_source_revision=True, source_owner_hash=None,
                           annotations=None, file_key=None, board_ref=None):
    """Compare a rederived specification with independently supplied native fields."""
    report = {'schema': 'figma-flow-specification-validation-v1', 'passed': False,
              'status': 'blocked', 'errors': [], 'unverified': [],
              'evidence': 'supplied-native-readback-not-origin-authentication'}
    errors, unverified = report['errors'], report['unverified']
    try:
        if not isinstance(expected, dict) or expected.get('schema') != SCHEMA:
            raise ValueError('current compiled specification required')
        if expected.get('meaning_sha256') != _meaning_hash(expected):
            errors.append('expected meaning hash is invalid')
        if expected.get('presentation') == 'connected-spec-v2':
            sections, display_text = _projection(expected.get('meaning', {}), expected.get('locale'))
            if expected.get('sections') != sections or expected.get('display_text') != display_text:
                errors.append('expected specification projection differs from graph meaning')
        if not isinstance(observed, dict) or observed.get('schema') != NATIVE_SCHEMA:
            raise ValueError('native specification wrapper required')
        if observed.get('state') != 'applied':
            errors.append('native specification state must be applied')
        key = expected['target_id'] if semantic_key is None else semantic_key
        if not key or observed.get('semantic_key') != key:
            errors.append('native semantic_key missing or mismatched')
        if native_id is None:
            unverified.append('actual native_id binding not supplied')
        elif observed.get('target_id') != native_id:
            errors.append('native target_id missing or mismatched')
        owner = observed.get('source_owner_hash')
        if not isinstance(owner, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', owner):
            errors.append('source_owner_hash must be a SHA256 hex digest')
        elif source_owner_hash is not None and owner != source_owner_hash:
            errors.append('source_owner_hash mismatched')
        actual = observed.get('specification')
        if not isinstance(actual, dict):
            raise ValueError('actual compiled specification missing')
        for field in ('schema', 'id', 'kind', 'screen_id', 'target_id', 'title', 'meaning',
                      'meaning_sha256', 'display_text', 'trace'):
            if field not in actual or actual[field] != expected[field]:
                errors.append('specification differs: ' + field)
        if expected.get('presentation') == 'connected-spec-v2':
            for field in ('presentation', 'locale', 'sections', 'annotation_text'):
                if actual.get(field) != expected.get(field):
                    errors.append('specification differs: ' + field)
            if actual.get('annotation_text') != (expected.get('meaning', {}).get('summary') or expected.get('meaning', {}).get('behavior') or expected.get('meaning', {}).get('purpose', '')).strip():
                errors.append('annotation_text differs from graph meaning')
            human = observed.get('human_annotation')
            if not isinstance(human, dict) or human.get('schema') != HUMAN_SCHEMA:
                errors.append('connected native human annotation wrapper required')
            else:
                index, raw, board = human.get('index'), human.get('annotation'), human.get('board')
                if type(index) is not int or index < 0 or not isinstance(raw, dict):
                    errors.append('human annotation raw snapshot and index required')
                elif not isinstance(annotations, list):
                    unverified.append('actual native annotations not supplied')
                elif index >= len(annotations) or annotations[index] != raw or sum(item == raw for item in annotations) != 1:
                    errors.append('human annotation raw snapshot is not uniquely present at its index')
                elif not isinstance(board, dict):
                    errors.append('human annotation board binding required')
                elif board_ref is None:
                    unverified.append('actual connected board reference not supplied')
                elif any(board.get(field) != board_ref.get(field) for field in ('boardId', 'textNodeId', 'key')):
                    errors.append('human annotation board reference mismatched')
                else:
                    try:
                        canonical = connected_annotation_markdown(expected, file_key, board['textNodeId'])
                        if sum(isinstance(item, dict) and item.get('labelMarkdown') == canonical['markdown'] for item in annotations) != 1:
                            errors.append('connected native annotation must be unique by canonical content')
                        if raw.get('labelMarkdown') != canonical['markdown']:
                            errors.append('human annotation markdown is not the canonical connected specification')
                        if human.get('url') != canonical['url']:
                            errors.append('human annotation URL mismatched')
                    except (ValueError, KeyError, TypeError) as exc:
                        errors.append(str(exc))
        elif 'human_annotation' in observed:
            errors.append('legacy specification cannot claim a connected human annotation')
        if actual.get('meaning_sha256') != _meaning_hash(actual):
            errors.append('actual meaning hash is invalid')
        if require_source_revision:
            for field in ('source_graph_sha256', 'source_graph_encoding'):
                if not expected.get(field) or actual.get(field) != expected[field]:
                    errors.append('source revision missing or mismatched: ' + field)
        legacy = observed.get('legacy_annotations')
        if (not isinstance(legacy, list) or any(
                not isinstance(item, dict) or type(item.get('index')) is not int or item['index'] < 0
                or not isinstance(item.get('annotation'), dict) for item in legacy)):
            errors.append('legacy_annotations must retain indexed annotation objects')
        elif len({item['index'] for item in legacy}) != len(legacy):
            errors.append('legacy annotation indexes must be unique')
        if expected['trace'].get('status') != 'complete':
            unverified.append('canonical requirement/acceptance/test trace incomplete')
        if require_trace and unverified:
            report['status'] = 'unverified'
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(str(exc))
    report['passed'] = not errors and not unverified
    report['status'] = 'passed' if report['passed'] else 'blocked' if errors else 'unverified'
    return report


def render_screen_spec(graph, *, source_graph_sha256=None):
    """Render the same projection; this generated document is not another SSOT."""
    lines = ['# Screen specifications', '',
             'Generated from canonical graph annotations; not a second source of truth.',
             'External source references are retained, not claims that their contents were read.', '']
    for spec in derive_specifications(graph, source_graph_sha256=source_graph_sha256):
        lines.extend(['## ' + spec['title'], '', spec['display_text'], '',
                      '<details>', '<summary>Technical references</summary>', '', '```json',
                      json.dumps(spec, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False),
                      '```', '', '</details>', ''])
    return '\n'.join(lines)
