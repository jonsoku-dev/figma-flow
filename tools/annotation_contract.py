"""Validate authored semantics against their graph and supplied artifacts, not provenance."""
from html.parser import HTMLParser
import copy
import re
from urllib.parse import unquote, urlsplit


TEXT_FIELDS = ('purpose', 'behavior', 'precondition', 'result', 'failure', 'design_choice', 'journey')
SEMANTIC_FIELDS = TEXT_FIELDS + ('first_action', 'functional_states', 'visual_variant', 'control_id')


def _meaningful(value):
    return (isinstance(value, str) and len(value.strip()) >= 6 and
            not re.search(r'^(?:todo|tbd|placeholder|pending|미정|작성 필요|확인 필요|button|control|screen)\s*[.:_-]*$', value.strip(), re.I))


def derive_notes(product_graph):
    """Project canonical graph annotations; missing meaning is never inferred from titles."""
    nodes = product_graph.get('nodes') if isinstance(product_graph, dict) else None
    if not isinstance(nodes, list) or any(not isinstance(n, dict) or not isinstance(n.get('id'), str) for n in nodes):
        raise ValueError('canonical product graph nodes required')
    by_id = {n['id']: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError('duplicate canonical graph IDs')
    notes = []
    for node in nodes:
        kind, identity = node.get('type'), node['id']
        if kind not in ('screen', 'action'):
            continue
        meaning = node.get('annotation')
        if not isinstance(meaning, dict):
            raise ValueError('structured annotation required: ' + identity)
        required = ('purpose', 'journey') if kind == 'screen' else ('purpose', 'behavior', 'result')
        if any(not _meaningful(meaning.get(field)) for field in required):
            raise ValueError('meaningful ' + '/'.join(required) + ' required: ' + identity)
        for field in TEXT_FIELDS:
            if field in meaning and not _meaningful(meaning[field]):
                raise ValueError('placeholder/empty annotation ' + field + ': ' + identity)
        screen_id = identity if kind == 'screen' else node.get('source_screen')
        if by_id.get(screen_id, {}).get('type') != 'screen':
            raise ValueError('action source screen is not canonical: ' + identity)
        controls = [meaning.get('control_id')]
        if kind == 'action':
            if 'control_ids' in meaning:
                controls = meaning['control_ids']
                if 'control_id' in meaning or not isinstance(controls, list) or not controls:
                    raise ValueError('action requires control_id or nonempty control_ids: ' + identity)
            if any(not isinstance(control, str) or not control.strip() for control in controls) or len(set(controls)) != len(controls):
                raise ValueError('action requires unique control IDs: ' + identity)
        states = meaning.get('functional_states')
        if kind == 'action' and (not isinstance(states, list) or not states):
            raise ValueError('functional state IDs required: ' + identity)
        if states is not None:
            if not isinstance(states, list) or not states or any(not isinstance(state, str) for state in states):
                raise ValueError('functional states must be canonical state IDs: ' + identity)
            for state in states:
                current = by_id.get(state, {})
                if current.get('type') != 'state' or any(str(value).casefold() in ('primary', 'secondary', 'quiet') for value in (state, current.get('title', ''))):
                    raise ValueError('visual variant or noncanonical functional state: ' + str(state))
        if kind == 'screen':
            actions = [n for n in nodes if n.get('type') == 'action' and n.get('source_screen') == identity]
            first = meaning.get('first_action')
            if actions and first not in {n['id'] for n in actions}:
                raise ValueError('screen first_action must reference its canonical action: ' + identity)
        for control in controls if kind == 'action' else [identity]:
            note = {key: copy.deepcopy(meaning[key]) for key in SEMANTIC_FIELDS if key in meaning}
            note.update(id=identity + '@' + control if kind == 'action' and len(controls) > 1 else identity,
                        kind=kind, screen_id=screen_id, target_id=control, status='planned', provenance='planned-not-native')
            if kind == 'action':
                note.update(action=identity, control_id=control)
            notes.append(note)
    if not notes:
        raise ValueError('canonical annotated screens/actions required')
    if len({note['id'] for note in notes}) != len(notes):
        raise ValueError('expanded annotation note IDs must remain unique')
    return notes


class _HTML(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.visible = set(), [], []
        self.hidden = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        hidden = (bool(self.hidden and self.hidden[-1][1]) or tag in ('script', 'style', 'template', 'noscript') or
                  'hidden' in attrs or attrs.get('aria-hidden') == 'true' or
                  bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style', ''), re.I)))
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.hidden.append((tag, hidden))
        if tag == 'a' and attrs.get('href') and not hidden:
            self.links.append(attrs['href'])

    def handle_endtag(self, tag):
        for index in range(len(self.hidden) - 1, -1, -1):
            if self.hidden[index][0] == tag:
                del self.hidden[index:]
                break

    def handle_data(self, data):
        if not self.hidden or not self.hidden[-1][1]:
            self.visible.append(data)


def validate_notes(notes, product_graph, stage='draft', *, source_html=None, review_html=None):
    """Compare exact canonical meaning; optional HTML checks require visible linked draft notes."""
    report = {'schema': 'figma-flow-annotation-contract-v1', 'passed': False, 'status': 'blocked',
              'stage': stage, 'errors': [], 'notes': [], 'evidence': 'supplied-source-validation-only'}
    errors = report['errors']
    try:
        if stage not in ('draft', 'native'):
            raise ValueError('annotation stage must be draft or native')
        canonical = derive_notes(product_graph)
        if not isinstance(notes, list) or any(not isinstance(note, dict) for note in notes):
            raise ValueError('structured notes list required')
        by_id = {note.get('id'): note for note in notes}
        if len(by_id) != len(notes) or set(by_id) != {note['id'] for note in canonical}:
            raise ValueError('notes must cover exactly the canonical annotated screens/actions')
        sources = None
        if source_html is not None:
            source_html = {'': source_html} if isinstance(source_html, str) else source_html
            if not isinstance(source_html, dict) or not source_html or any(not isinstance(html, str) for html in source_html.values()):
                raise ValueError('source HTML text or filename/text mapping required')
            sources = {name: _HTML(html) for name, html in source_html.items()}
        review = _HTML(review_html) if isinstance(review_html, str) else None
        if (sources is None) != (review is None):
            raise ValueError('source and review HTML must be checked together')
        for expected in canonical:
            note = by_id[expected['id']]
            for field in ('id', 'kind', 'screen_id', 'target_id', 'action') + SEMANTIC_FIELDS:
                if note.get(field) != expected.get(field):
                    errors.append('annotation differs from canonical ' + field + ': ' + expected['id'])
            if stage == 'draft' and (note.get('status') != 'planned' or note.get('provenance') != 'planned-not-native' or note.get('native') is True):
                errors.append('draft must explicitly remain planned, not native: ' + expected['id'])
            if sources is not None:
                target = note.get('target', '#' + expected['target_id'])
                parsed = urlsplit(target)
                anchor = unquote(parsed.fragment)
                chosen = [sources[parsed.path]] if parsed.path in sources else list(sources.values()) if not parsed.path else []
                if parsed.scheme or parsed.netloc or anchor != expected['target_id'] or not any(anchor in html.ids for html in chosen):
                    errors.append('annotated target anchor missing from source: ' + expected['id'])
                if target not in review.links:
                    errors.append('review lacks visible link to annotated target: ' + expected['id'])
                visible = ' '.join(' '.join(review.visible).split())
                for field in TEXT_FIELDS:
                    if expected.get(field) and ' '.join(expected[field].split()) not in visible:
                        errors.append('review hides/misses meaningful ' + field + ': ' + expected['id'])
                if not re.search(r'planned|계획|예정', visible, re.I) or not re.search(r'not native|네이티브.*아님|Figma.*아님', visible, re.I):
                    errors.append('review must visibly identify planned, not native notes')
            report['notes'].append(copy.deepcopy(note))
        if stage == 'native':
            errors.append('native validation requires actual readback; use validate_native_annotations')
    except (ValueError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    report['passed'] = not errors
    report['status'] = 'passed' if report['passed'] else 'blocked'
    return report


def _native_claim_errors(node, nodes, parents, text):
    errors = []
    if re.search(r'nine[ -]slice|9[ -]slice|나인[ -]?슬라이스', text, re.I):
        slices = {}
        expected = {'tl': ('MIN', 'MIN'), 't': ('STRETCH', 'MIN'), 'tr': ('MAX', 'MIN'),
                    'l': ('MIN', 'STRETCH'), 'c': ('STRETCH', 'STRETCH'), 'r': ('MAX', 'STRETCH'),
                    'bl': ('MIN', 'MAX'), 'b': ('STRETCH', 'MAX'), 'br': ('MAX', 'MAX')}
        for child in nodes.values():
            if parents.get(child['id']) != node['id'] or child.get('type') != 'RECTANGLE':
                continue
            suffix = child.get('name', '').rsplit('.skin.', 1)[-1]
            if suffix in expected and any(p.get('type') == 'IMAGE' and p.get('imageHash') for p in child.get('fills', []) if isinstance(p, dict)):
                constraints = child.get('constraints', {})
                if (constraints.get('horizontal'), constraints.get('vertical')) == expected[suffix] and child.get('width', 0) > 0 and child.get('height', 0) > 0:
                    slices[suffix] = child
        geometry = set(slices) == set(expected)
        if geometry:
            try:
                close = lambda a, b: abs(a - b) < 0.01
                for row in (('tl', 't', 'tr'), ('l', 'c', 'r'), ('bl', 'b', 'br')):
                    left, middle, right = [slices[key] for key in row]
                    geometry &= (close(left['x'], 0) and close(left['x'] + left['width'], middle['x']) and
                                 close(middle['x'] + middle['width'], right['x']) and
                                 close(right['x'] + right['width'], node['width']) and
                                 close(left['y'], middle['y']) and close(middle['y'], right['y']) and
                                 close(left['height'], middle['height']) and close(middle['height'], right['height']))
                for column in (('tl', 'l', 'bl'), ('t', 'c', 'b'), ('tr', 'r', 'br')):
                    top, middle, bottom = [slices[key] for key in column]
                    geometry &= (close(top['y'], 0) and close(top['y'] + top['height'], middle['y']) and
                                 close(middle['y'] + middle['height'], bottom['y']) and
                                 close(bottom['y'] + bottom['height'], node['height']) and
                                 close(top['x'], middle['x']) and close(middle['x'], bottom['x']) and
                                 close(top['width'], middle['width']) and close(middle['width'], bottom['width']))
            except (KeyError, TypeError):
                geometry = False
        if not geometry:
            errors.append('unsupported native nine-slice claim: ' + node['id'])
    if re.search(r'content[ -]hug|content hug|콘텐츠.*허그', text, re.I):
        if node.get('layoutMode') not in ('HORIZONTAL', 'VERTICAL') or not (
                node.get('layoutSizingHorizontal') == 'HUG' or node.get('layoutSizingVertical') == 'HUG' or
                node.get('primaryAxisSizingMode') == 'AUTO' or node.get('counterAxisSizingMode') == 'AUTO'):
            errors.append('unsupported native content-hug claim: ' + node['id'])
    if re.search(r'(?:States|기능 상태)\s*:\s*(?:Primary|Secondary|Quiet)(?:\s*[,/]|\s*\.)', text, re.I):
        errors.append('visual variants presented as functional states: ' + node['id'])
    return errors


def validate_native_annotations(readback, declaration, page_id=None):
    """Strict creation only: actual node.annotations must retain the source semantic contract."""
    from native_handoff import normalize, annotations
    report = {'schema': 'figma-flow-native-annotation-contract-v1', 'passed': False, 'status': 'blocked',
              'errors': [], 'nodes': [], 'evidence': 'supplied-native-readback-not-origin-authentication'}
    errors = report['errors']
    try:
        if not isinstance(declaration, dict) or declaration.get('mode') != 'strict-creation':
            raise ValueError('explicit strict-creation annotation declaration required')
        graph = declaration.get('product_graph')
        expected = derive_notes(graph)
        supplied = declaration.get('notes')
        semantic_report = validate_notes(supplied, graph)
        errors.extend(semantic_report['errors'])
        if not semantic_report['passed']:
            return report
        nodes, parents = normalize(readback)
        selected = page_id or readback.get('pageId')
        def within(identity):
            seen = set()
            while identity and identity not in seen:
                if identity == selected:
                    return True
                seen.add(identity)
                identity = parents.get(identity)
            return False
        if not selected:
            raise ValueError('selected native page required')
        supplied = {note['id']: note for note in supplied}
        for note in expected:
            declared = supplied[note['id']]
            identity, key = declared.get('native_id'), declared.get('native_key', note['target_id'])
            found = [node for node in nodes.values() if (node['id'] == identity if identity else
                     key in (node.get('semanticKey'), node.get('key'), node.get('semantic_id')))]
            if len(found) != 1 or not within(found[0]['id']):
                errors.append('missing/ambiguous annotation target on selected native page: ' + note['id'])
                continue
            node = found[0]
            text = '\n'.join(annotations(node))
            if not text:
                errors.append('actual native annotations missing: ' + node['id'])
            for field in TEXT_FIELDS + ('first_action', 'action'):
                if note.get(field) and note[field] not in text:
                    errors.append('native annotation lacks canonical ' + field + ': ' + node['id'])
            for state in note.get('functional_states', []):
                if state not in text:
                    errors.append('native annotation lacks functional state: ' + node['id'] + ' ' + state)
            if note.get('visual_variant') and note['visual_variant'] not in text:
                errors.append('native annotation lacks visual variant: ' + node['id'])
            errors.extend(_native_claim_errors(node, nodes, parents, text))
            report['nodes'].append({'id': node['id'], 'semantic_id': note['id'], 'native_annotations': annotations(node)})
        # Unsupported claims on other annotated objects cannot hide outside the required controls.
        for node in nodes.values():
            if within(node['id']):
                errors.extend(error for error in _native_claim_errors(node, nodes, parents, '\n'.join(annotations(node))) if error not in errors)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(str(exc))
    report['passed'] = not errors
    report['status'] = 'passed' if report['passed'] else 'blocked'
    return report
