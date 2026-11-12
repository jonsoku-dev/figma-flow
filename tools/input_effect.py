#!/usr/bin/env python3
"""Project declared local inputs into a consumption record.

This is not an arbitrary HTML, URL, or TSX importer. It reads fixtures the
regression program already placed on disk, records which facts each file
actually contributes, and refuses to treat omitted or conflicting inputs as
consumed. Text extraction is not a browser render, and visual_quality stays
unverified.
"""
import hashlib
import json
import re
from collections import deque
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit

import design_directions
import design_system

SCHEMA = 'figma-flow-input-effect-v1'
RESULT_SCHEMA = 'figma-flow-input-effect-result-v3'
URL_SCHEMA = 'figma-flow-url-snapshot-v1'
INPUT_NAMES = ('html', 'url', 'design-system')
RENDER_STATUSES = {'rendered', 'text-only', 'js-required', 'redirect', 'login-required', 'not-found', 'rate-limited'}
FAILURE_STATUSES = {'redirect', 'login-required', 'not-found', 'rate-limited'}
INSTRUCTION = re.compile(r'(?i)ignore previous instructions|you are now|overwrite brief\.md|run this command')
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
RUNTIME_NAMES = {
    'button': 'Button',
    'field': 'Field',
    'table': 'Table',
    'dialog': 'Dialog',
    'tabs': 'Tabs',
    'nav': 'Nav',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    raw = value if isinstance(value, (bytes, bytearray)) else canonical(value).encode()
    return hashlib.sha256(raw).hexdigest()


def _root(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Fixture root must be a real directory')
    return root.resolve()


def locate(root, relative, *, require_file=True):
    """Resolve a safe local path, requiring a file except for source-state checks."""
    root = _root(root)
    if not isinstance(relative, str) or not relative or '\\' in relative or relative.startswith('/'):
        raise ValueError('Input path must be a relative path inside the fixture root')
    parts = PurePosixPath(relative).parts
    if not parts or any(part in ('', '.', '..') for part in parts):
        raise ValueError('Input path escapes the fixture root')
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Input path is a symlink')
    resolved = current.resolve()
    if not resolved.is_relative_to(root) or require_file and not current.is_file():
        raise ValueError('Input path escapes the fixture root or is not a file')
    return current


def _load_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Unreadable JSON input') from error
    if not isinstance(value, dict):
        raise ValueError('JSON input must be an object')
    return value


def _quarantine(text):
    return [match.group(0) for match in INSTRUCTION.finditer(text)]


def _relative_asset(html_path, root, url):
    root = _root(root)
    html_path = Path(html_path).resolve()
    if url.startswith('#'):
        return {'ref': url, 'status': 'external-unverified'}
    if '\\' in url:
        return {'ref': url, 'status': 'rejected'}
    try:
        reference = urlsplit(url)
    except ValueError:
        return {'ref': url, 'status': 'rejected'}
    if reference.scheme or reference.netloc:
        return {'ref': url, 'status': 'external-unverified'}
    local = unquote(reference.path)
    if local.startswith('/') or '\\' in local or '\x00' in local:
        return {'ref': url, 'status': 'rejected'}
    parts = PurePosixPath(local).parts
    if not parts:
        return {'ref': url, 'status': 'rejected'}
    current = html_path.parent
    for part in parts:
        if part == '..':
            if current == root:
                return {'ref': url, 'status': 'rejected'}
            current = current.parent
            continue
        if part in ('', '.'):
            continue
        current = current / part
        if current.is_symlink():
            return {'ref': url, 'status': 'rejected'}
    resolved = current.resolve()
    if not resolved.is_relative_to(root):
        return {'ref': url, 'status': 'rejected'}
    return {
        'ref': url,
        'status': 'present' if current.is_file() else '404',
        'path': current.relative_to(root).as_posix(),
    }


class _HTMLAssets(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.styles = []
        self.inline_styles = []
        self._style = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() in {'link', 'script', 'img'}:
            key = 'href' if tag.lower() == 'link' else 'src'
            if attrs.get(key):
                ref = attrs[key]
                rel = set((attrs.get('rel') or '').lower().split())
                is_stylesheet = tag.lower() == 'link' and ('stylesheet' in rel or (attrs.get('type') or '').lower() == 'text/css' or ref.split('?', 1)[0].split('#', 1)[0].lower().endswith('.css'))
                kind = 'stylesheet' if is_stylesheet else 'script' if tag.lower() == 'script' else 'image' if tag.lower() == 'img' else attrs.get('as')
                self.references.append((ref, is_stylesheet, kind))
        if attrs.get('style'):
            self.inline_styles.append(attrs['style'])
        if tag.lower() == 'style':
            self._style = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() == 'style' and self._style is not None:
            self.styles.append(''.join(self._style))
            self._style = None

    def handle_endtag(self, tag):
        if tag.lower() == 'style' and self._style is not None:
            self.styles.append(''.join(self._style))
            self._style = None

    def handle_data(self, data):
        if self._style is not None:
            self._style.append(data)

    def close(self):
        pending = self.rawdata
        super().close()
        if self._style is not None:
            self._style.append(pending)
            self.styles.append(''.join(self._style))
            self._style = None


def _css_parser():
    try:
        import tinycss2
    except ImportError as error:
        raise ValueError('CSS dependency tracking requires optional package tinycss2; install requirements-optional.txt') from error
    return tinycss2


def _css_references(data, *, declarations=False, environment_encoding=None):
    tinycss2 = _css_parser()
    if declarations:
        rules = tinycss2.parse_declaration_list(data.decode('utf-8'), skip_comments=True, skip_whitespace=True)
        encoding = None
    else:
        rules, encoding = tinycss2.parse_stylesheet_bytes(data, environment_encoding=environment_encoding, skip_comments=True, skip_whitespace=True)
    references = []

    def function_url(token):
        args = [item for item in token.arguments if item.type not in {'whitespace', 'comment'}]
        if len(args) == 1 and args[0].type == 'string':
            return args[0].value
        return tinycss2.serialize(args).strip() if args else ''

    def walk(tokens):
        for token in tokens:
            is_import = token.type == 'at-rule' and token.lower_at_keyword == 'import'
            if is_import and token.prelude:
                first = next((item for item in token.prelude if item.type not in {'whitespace', 'comment'}), None)
                if first is not None and first.type == 'string':
                    references.append((first.value, 'import'))
                elif first is not None and first.type == 'url':
                    references.append((first.value, 'import'))
                elif first is not None and first.type == 'function' and first.lower_name == 'url':
                    references.append((function_url(first), 'import'))
            elif token.type == 'url':
                references.append((token.value, 'url'))
            elif token.type == 'function' and token.lower_name == 'url':
                references.append((function_url(token), 'url'))
            elif token.type == 'function':
                walk(token.arguments)
            for name in ('prelude', 'content', 'value'):
                if is_import and name == 'prelude':
                    continue
                nested = getattr(token, name, None)
                if isinstance(nested, (list, tuple)) and nested:
                    walk(nested)

    walk(rules)
    return references, encoding


def _css_text(data):
    tinycss2 = _css_parser()
    _rules, encoding = tinycss2.parse_stylesheet_bytes(data, skip_comments=True, skip_whitespace=True)
    return data.decode(encoding.name)


def _asset_kind(ref):
    if not isinstance(ref, str):
        return 'file'
    try:
        extension = PurePosixPath(urlsplit(ref).path.lower()).suffix
    except ValueError:
        return 'file'
    if extension in {'.woff', '.woff2', '.ttf', '.otf', '.eot'}:
        return 'font'
    if extension in {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif', '.apng', '.bmp', '.ico'}:
        return 'image'
    if extension == '.css':
        return 'stylesheet'
    if extension in {'.js', '.mjs', '.cjs'}:
        return 'script'
    return 'file'


def _ingress(asset, source, kind=None):
    copied = dict(asset)
    inferred = _asset_kind(asset.get('ref', ''))
    copied['kind'] = inferred if inferred != 'file' else kind if kind in {'font', 'image', 'stylesheet', 'script'} else 'file'
    if source:
        copied['sources'] = [source]
    return copied


def _merge_ingress(assets):
    """One asset keeps every stylesheet or document that referenced it."""
    merged = {}
    order = []
    for asset in assets:
        identity = {key: value for key, value in asset.items() if key != 'sources'}
        key = canonical({name: identity[name] for name in ('path', 'kind', 'status')}) if isinstance(identity.get('path'), str) else canonical(identity)
        if key not in merged:
            merged[key] = {**identity, 'sources': list(asset.get('sources') or [])}
            order.append(key)
            continue
        for source in asset.get('sources') or []:
            if source not in merged[key]['sources']:
                merged[key]['sources'].append(source)
    return [merged[key] for key in order]


def html_channel(path, root, *, required_facts=None):
    root = _root(root)
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    source = design_directions.Source(text)
    title_match = TITLE.search(text)
    title = re.sub(r'\s+', ' ', title_match.group(1)).strip() if title_match else ''
    visible = re.sub(r'\s+', ' ', ' '.join(source.text)).strip()
    parser = _HTMLAssets()
    parser.feed(text)
    parser.close()
    assets = []
    css_queue = deque()
    seen_css = set()
    direct_css_paths = set()
    html_relative = Path(path).resolve().relative_to(root).as_posix()
    for ref, is_stylesheet, kind in parser.references:
        asset = _ingress(_relative_asset(path, root, ref), html_relative, kind)
        assets.append(asset)
        if is_stylesheet and asset.get('status') == 'present':
            css_queue.append((locate(root, asset['path']), asset['path'], None))
            direct_css_paths.add(asset['path'])
    for style in parser.styles:
        refs, encoding = _css_references(style.encode('utf-8'))
        for ref, kind in refs:
            assets.append(_ingress(_relative_asset(path, root, ref), html_relative, 'stylesheet' if kind == 'import' else None))
            asset = assets[-1]
            if kind == 'import' and asset.get('status') == 'present':
                css_queue.append((locate(root, asset['path']), asset['path'], encoding))
    for style in parser.inline_styles:
        refs, _encoding = _css_references(style.encode('utf-8'), declarations=True)
        for ref, _kind in refs:
            assets.append(_ingress(_relative_asset(path, root, ref), html_relative))
    while css_queue:
        css_path, css_relative, environment_encoding = css_queue.popleft()
        encoding_key = environment_encoding.name if environment_encoding else None
        css_key = (css_relative, encoding_key)
        if css_key in seen_css:
            continue
        seen_css.add(css_key)
        refs, child_encoding = _css_references(css_path.read_bytes(), environment_encoding=environment_encoding)
        for ref, kind in refs:
            asset = _ingress(_relative_asset(css_path, root, ref), css_relative, 'stylesheet' if kind == 'import' else None)
            assets.append(asset)
            if asset.get('status') == 'present' and (kind == 'import' or asset.get('path', '').lower().endswith('.css')):
                css_queue.append((locate(root, asset['path']), asset['path'], child_encoding))
    assets = _merge_ingress(assets)
    layout = list(design_directions._layout_signature(text))
    for css_relative in sorted(direct_css_paths):
        css_path = locate(root, css_relative)
        layout.extend(design_directions._layout_signature('<style>' + _css_text(css_path.read_bytes()) + '</style>'))
    facts = {}
    if title:
        facts['screen-title'] = title
    gaps = sorted({value for name, value in layout if name == 'gap'})
    unresolved = {}
    if len(gaps) == 1:
        facts['surface-gap'] = gaps[0]
    elif len(gaps) > 1:
        if required_facts is None or 'surface-gap' in required_facts:
            raise ValueError('HTML fixture must declare one gap fact')
        unresolved['surface-gap'] = gaps
    result = {
        'facts': facts,
        'title': title,
        'layout': layout,
        'assets': assets,
        'visible_sha256': digest(visible.encode()),
        'quarantine': _quarantine(text),
        'render': 'unverified',
    }
    if unresolved:
        result['unresolved_facts'] = unresolved
    return result


def url_channel(path):
    data = _load_json(path)
    if data.get('schema') != URL_SCHEMA or data.get('channel') not in {'local-file-fixture', 'user-text-url'}:
        raise ValueError('URL snapshot schema is invalid')
    required = ('original_url', 'final_url', 'observed_at', 'viewport', 'body_location', 'render_status', 'principles', 'observation_limit', 'cause')
    if any(not data.get(key) and data.get(key) != [] for key in required if key != 'principles'):
        raise ValueError('URL snapshot is missing collection fields')
    if data['render_status'] not in RENDER_STATUSES:
        raise ValueError('URL snapshot render status is invalid')
    if not isinstance(data['principles'], list) or not isinstance(data['viewport'], dict):
        raise ValueError('URL snapshot principles or viewport is invalid')
    if not isinstance(data['observation_limit'], str) or not data['observation_limit'].strip():
        raise ValueError('URL snapshot must keep its observation limit')
    capture = data.get('capture')
    reference_complete = data['render_status'] == 'rendered' and isinstance(capture, dict) and isinstance(capture.get('sha256'), str) and len(capture['sha256']) == 64
    if data['render_status'] in FAILURE_STATUSES | {'js-required'}:
        if data.get('unknown_body') is not True or data['principles']:
            raise ValueError('Unrendered URL status cannot invent a body or an adopted principle')
    adopted, excluded = [], []
    for principle in data['principles']:
        if not isinstance(principle, dict):
            raise ValueError('URL principle must be an object')
        if principle.get('adopted') is True:
            if any(not isinstance(principle.get(key), str) or not principle[key].strip() for key in ('id', 'text', 'target', 'decision')):
                raise ValueError('Adopted URL principle needs an id, text, target, and decision')
            adopted.append(principle['id'])
        elif principle.get('adopted') is False and isinstance(principle.get('decision'), str) and principle['decision'].strip():
            if not isinstance(principle.get('id'), str) or not principle['id'].strip():
                raise ValueError('Excluded URL principle needs an id')
            excluded.append(principle['id'])
    references = data.get('references', [])
    if not isinstance(references, list):
        raise ValueError('URL references must be a list')
    for reference in references:
        if not isinstance(reference, dict) or any(not isinstance(reference.get(key), str) or not reference[key].strip() for key in ('id', 'original_url', 'render_status', 'decision')):
            raise ValueError('URL reference is incomplete')
        if reference.get('adopted') is True:
            raise ValueError('A secondary reference cannot be adopted from this snapshot')
        excluded.append(reference['id'])
    facts = {}
    if adopted:
        facts['reference-principle'] = ','.join(adopted)
    if excluded:
        facts['excluded-principle'] = ','.join(excluded)
    return {
        'facts': facts,
        'original_url': data['original_url'],
        'final_url': data['final_url'],
        'observed_at': data['observed_at'],
        'viewport': data['viewport'],
        'render_status': data['render_status'],
        'reference_complete': reference_complete,
        'observation_limit': data['observation_limit'],
        'cause': data['cause'],
        'principles': data['principles'],
        'references': references,
        'quarantine': _quarantine(path.read_text(encoding='utf-8')),
    }


def design_channel(path, root, expected_version):
    data = _load_json(path)
    compiled = design_system.compile_design(data)
    parent = path.parent
    siblings = {
        'package.json': parent / 'package.json',
        'axes.json': parent / 'axes.json',
        'theme.css': parent / 'theme.css',
        'components.json': parent / 'components.json',
        'runtime.js': parent / 'runtime.js',
    }
    loaded = {}
    for name, sibling in siblings.items():
        relative = sibling.resolve().relative_to(root).as_posix()
        loaded[name] = locate(root, relative)
    package = _load_json(loaded['package.json'])
    version = package.get('version')
    if expected_version is not None and version != expected_version:
        raise ValueError('Design-system package version does not match the pinned fixture')
    if not isinstance(version, str) or not version:
        raise ValueError('Design-system package version is missing')
    axes = _load_json(loaded['axes.json'])
    design_system.attach_declared_axes(compiled['components'], axes.get('components') or {})
    unsupported = axes.get('unsupported')
    if not isinstance(unsupported, list) or not unsupported:
        raise ValueError('Design-system axes must report unsupported axes')
    components = _load_json(loaded['components.json'])
    runtime = loaded['runtime.js'].read_text(encoding='utf-8')
    theme = loaded['theme.css'].read_text(encoding='utf-8')
    brand = compiled['tokens'].get('color.brand', {}).get('value')
    if not isinstance(brand, str) or brand not in theme:
        raise ValueError('theme.css does not consume the compiled brand token')
    for token_name, export_name in RUNTIME_NAMES.items():
        entry = components.get(token_name)
        if not isinstance(entry, dict) or entry.get('runtime') != export_name:
            raise ValueError('Design-system component map does not match the runtime names')
        source = locate(root, entry['source'])
        if export_name not in source.read_text(encoding='utf-8') or f'function {export_name}' not in runtime:
            raise ValueError('Design-system runtime does not expose a declared component')
        if token_name not in compiled['components']:
            raise ValueError('Compiled design system dropped a declared component')
    facts = {'component-set': ','.join(sorted(compiled['components']))}
    gap = compiled['tokens'].get('space.gap')
    if gap:
        facts['surface-gap'] = gap['value']
    if brand:
        facts['brand-token'] = brand
    return {
        'facts': facts,
        'package_version': version,
        'package_name': package.get('name'),
        'unsupported_axes': unsupported,
        'variant_axes': {name: component['variant_axes'] for name, component in compiled['components'].items() if 'variant_axes' in component},
        'components': sorted(compiled['components']),
        'brand_token': brand,
        'tsx_execution': 'not-run',
        'runtime_checked': True,
        'quarantine': _quarantine(runtime),
        'extra_files': [sibling.resolve().relative_to(root).as_posix() for sibling in siblings.values()],
    }


def _brief_channel(path, facts_path):
    text = path.read_text(encoding='utf-8')
    facts = _load_json(facts_path)
    if not facts:
        raise ValueError('Brief facts are empty')
    found = {}
    for key, value in facts.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value or value not in text:
            raise ValueError('Brief fact is not present in the brief')
        found[key] = value
    return {'facts': found, 'quarantine': _quarantine(text)}


def _decisions(authority, channels):
    rules = authority.get('facts')
    if not isinstance(rules, dict) or not rules:
        raise ValueError('Authority facts are missing')
    decisions, blocked = [], []
    for fact, rule in rules.items():
        if not isinstance(rule, dict):
            raise ValueError('Authority rule must be an object')
        priority = rule.get('priority')
        if priority is not None and (not isinstance(priority, list) or not all(isinstance(item, str) for item in priority)):
            raise ValueError('Authority priority must be a source list')
        present = {}
        for source, channel in channels.items():
            if fact in channel['facts']:
                present[source] = channel['facts'][fact]
        if not present:
            continue
        if len(present) > 1 and not priority:
            blocked.append({'fact': fact, 'values': present})
            continue
        winner = None
        if priority:
            for source in priority:
                if source in present:
                    winner = source
                    break
            if winner is None:
                blocked.append({'fact': fact, 'values': present, 'priority': priority})
                continue
        else:
            winner = next(iter(present))
        decisions.append({
            'fact': fact,
            'source': winner,
            'value': present[winner],
            'rejected': {key: value for key, value in present.items() if key != winner},
        })
    return decisions, blocked


def project(root, spec):
    root = _root(root)
    if not isinstance(spec, dict) or spec.get('schema') != SCHEMA:
        raise ValueError('Unknown input-effect schema')
    brief = locate(root, spec.get('brief', ''))
    facts = locate(root, spec.get('facts', ''))
    authority_path = locate(root, spec.get('authority', ''))
    authority = _load_json(authority_path)
    fact_rules = authority.get('facts')
    required_facts = fact_rules if isinstance(fact_rules, dict) else ()
    channels = {'brief': _brief_channel(brief, facts)}
    sources = [
        {'path': spec['brief'], 'sha256': digest(brief.read_bytes())},
        {'path': spec['facts'], 'sha256': digest(facts.read_bytes())},
        {'path': spec['authority'], 'sha256': digest(authority_path.read_bytes())},
    ]
    inputs = spec.get('inputs') or {}
    if not isinstance(inputs, dict) or any(name not in INPUT_NAMES for name in inputs):
        raise ValueError('Unknown input channel')
    if 'html' in inputs:
        path = locate(root, inputs['html'])
        channels['html'] = html_channel(path, root, required_facts=required_facts)
        sources.append({'path': inputs['html'], 'sha256': digest(path.read_bytes())})
        source_paths = {item['path'] for item in sources}
        for asset in channels['html']['assets']:
            relative = asset.get('path')
            if relative and relative not in source_paths:
                asset_path = locate(root, relative, require_file=False)
                sources.append({'path': relative, 'sha256': digest(asset_path.read_bytes()) if asset_path.is_file() else None})
                source_paths.add(relative)
    if 'url' in inputs:
        path = locate(root, inputs['url'])
        channels['url'] = url_channel(path)
        sources.append({'path': inputs['url'], 'sha256': digest(path.read_bytes())})
    if 'design-system' in inputs:
        path = locate(root, inputs['design-system'])
        channels['design-system'] = design_channel(path, root, spec.get('expected_package_version'))
        sources.append({'path': inputs['design-system'], 'sha256': digest(path.read_bytes())})
        for relative in channels['design-system']['extra_files']:
            sources.append({'path': relative, 'sha256': digest(locate(root, relative).read_bytes())})
    decisions, blocked = _decisions(authority, channels)
    quarantine = [item for channel in channels.values() for item in channel.get('quarantine', [])]
    for decision in decisions:
        if any(phrase in str(decision['value']) for phrase in quarantine):
            raise ValueError('Material instructions cannot become authority')
    consumption = {}
    for name, channel in channels.items():
        source = next(item for item in sources if name == 'brief' and item['path'] == spec['brief'] or name == 'html' and item['path'] == inputs.get('html') or name == 'url' and item['path'] == inputs.get('url') or name == 'design-system' and item['path'] == inputs.get('design-system'))
        consumption[name] = {'sha256': source['sha256'], 'facts': sorted(channel['facts'])}
    material = {'blocked': blocked, 'consumption': consumption, 'decisions': decisions, 'sources': sources}
    reference_complete = bool(channels.get('url', {}).get('reference_complete', False)) if 'url' in channels else False
    return {
        'schema': RESULT_SCHEMA,
        'status': 'blocked' if blocked else 'projected',
        'visual_quality': 'unverified',
        'decisions': decisions,
        'blocked': blocked,
        'channels': channels,
        'consumption': consumption,
        'digest_material': material,
        'digest': digest(material),
        'sources': sources,
        'quarantine': quarantine,
        'reference_complete': reference_complete,
        'limits': [
            'visual quality is unverified',
            'text extraction and HTTP status are not a browser render',
            'TSX files were not executed',
            'local HTML and CSS dependencies are tracked without executing scripts or resolving external URLs',
        ],
    }


def freshness(record, root):
    if not isinstance(record, dict) or not isinstance(record.get('sources'), list):
        raise ValueError('Projection record has no source hashes')
    if record.get('schema') != RESULT_SCHEMA:
        raise ValueError('Projection record schema is outdated; regenerate the projection before checking freshness')
    changed = []
    for item in record['sources']:
        path = locate(root, item['path'], require_file=False)
        current = digest(path.read_bytes()) if path.is_file() else None
        if current != item.get('sha256'):
            changed.append(item['path'])
    return {'status': 'stale' if changed else 'current', 'changed': changed, 'previous_digest': record.get('digest')}


def write_record(root, record, relative_out):
    root = _root(root)
    if not isinstance(relative_out, str) or not relative_out:
        raise ValueError('Record output must be a relative path')
    parts = PurePosixPath(relative_out).parts
    if not parts or any(part in ('', '.', '..') for part in parts):
        raise ValueError('Record output escapes the fixture root')
    current = root
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError('Record output parent is unsafe')
    target = current / parts[-1]
    if target.exists() or target.is_symlink():
        raise ValueError('Refusing to overwrite an existing record or input')
    source_paths = {item['path'] for item in record.get('sources', [])}
    if relative_out in source_paths:
        raise ValueError('Refusing to overwrite an input')
    if not target.resolve().is_relative_to(root):
        raise ValueError('Record output escapes the fixture root')
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return target


def confirm_input_record_route():
    """The one HTML asset route. Preparation copies a validated record; it does not grow a new flag."""
    return {
        'producer': 'input_effect.project',
        'channel': 'html_channel',
        'freshness': 'input_effect.freshness',
        'store': 'input_effect.write_record',
        'task_boundary': 'figma_workspace.prepare',
        'consumer': 'private task artifact',
        'not_consumer': 'ImportPanel',
            'cli_flag': '--input-record',
    }


def _safe_ref(value):
    if not isinstance(value, str) or not value:
        return ''
    path = value.replace('\\', '/')
    if (path.startswith('/') and not path.startswith('//')) or path.startswith('~') or re.match(r'^[A-Za-z]:/', path):
        return PurePosixPath(path.split('?', 1)[0].split('#', 1)[0]).name
    try:
        parts = urlsplit(value)
        hostname = parts.hostname or ''
        port = parts.port
    except ValueError:
        return ''
    if parts.scheme or parts.netloc:
        host = '[' + hostname + ']' if ':' in hostname else hostname
        if port is not None:
            host += ':' + str(port)
        return urlunsplit((parts.scheme, host, parts.path, '', ''))
    path = parts.path.replace('\\', '/')
    if path.startswith('/') or path.startswith('~') or '/Users/' in path:
        return PurePosixPath(path).name
    return path


def summarize_input_record(record):
    """Hash the private record and return only relative, status-preserving rows."""
    if not isinstance(record, dict) or record.get('schema') != RESULT_SCHEMA:
        raise ValueError('Invalid input record')
    channels = record.get('channels')
    assets = channels.get('html', {}).get('assets') if isinstance(channels, dict) else None
    if not isinstance(assets, list):
        raise ValueError('Invalid input record')
    allowed = {'present', '404', 'rejected', 'external-unverified'}
    rows = []
    for asset in assets:
        if not isinstance(asset, dict) or asset.get('status') not in allowed:
            raise ValueError('Invalid input record')
        raw_kind = asset.get('kind')
        kind = raw_kind if isinstance(raw_kind, str) and raw_kind in {'font', 'image', 'stylesheet', 'script', 'file'} else _asset_kind(asset.get('ref', ''))
        shown = _safe_ref(asset.get('ref', ''))
        sources = asset.get('sources', [])
        if not isinstance(sources, list):
            raise ValueError('Invalid asset sources')
        source = ', '.join(dict.fromkeys(filter(None, (_safe_ref(value) for value in [*sources, asset.get('source', '')]))))
        rows.append({
            'ref': shown,
            'kind': kind,
            'status': asset['status'],
            'source': source,
            'digest': digest(canonical({'kind': kind, 'ref': shown, 'source': source, 'status': asset['status']}).encode())[:12],
        })
    payload = canonical(record).encode()
    return {'sha256': digest(payload), 'summary': rows, 'bytes': payload}


def contrast_css_browser_loading(root, *, requested_paths=None):
    """Compare inventory with an explicit observation from the caller's approved browser."""
    root = _root(root)
    page = root / 'index.html'
    if not page.is_file():
        raise ValueError('Browser contrast requires index.html')
    if not isinstance(requested_paths, list) or len(requested_paths) > 4096:
        raise ValueError('An approved browser observation of relative request paths is required')
    for value in requested_paths:
        if not isinstance(value, str) or not value or len(value) > 2048 or urlsplit(value).query or urlsplit(value).fragment:
            raise ValueError('Browser observations require bounded relative paths')
        locate(root, value, require_file=False)
    listed = [{'path': asset['path'], 'status': asset['status']} for asset in html_channel(page, root, required_facts=())['assets'] if asset.get('path')]
    return {'list': listed, 'browser': {'requested': sorted(set(requested_paths)), 'source': 'provided-observation'}, 'separate': True}
