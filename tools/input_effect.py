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
from pathlib import Path, PurePosixPath

import design_directions
import design_system

SCHEMA = 'figma-flow-input-effect-v1'
RESULT_SCHEMA = 'figma-flow-input-effect-result-v1'
URL_SCHEMA = 'figma-flow-url-snapshot-v1'
INPUT_NAMES = ('html', 'url', 'design-system')
RENDER_STATUSES = {'rendered', 'text-only', 'js-required', 'redirect', 'login-required', 'not-found', 'rate-limited'}
FAILURE_STATUSES = {'redirect', 'login-required', 'not-found', 'rate-limited'}
INSTRUCTION = re.compile(r'(?i)ignore previous instructions|you are now|overwrite brief\.md|run this command')
ASSET = re.compile(r'<(link|script|img)\b([^>]*)>', re.I)
ATTR = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I)
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


def locate(root, relative):
    """Resolve one relative file and reject escapes, absolute paths, and symlinks."""
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
    if not resolved.is_relative_to(root) or not current.is_file():
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
    if url.startswith(('#', 'data:', 'http:', 'https:', '//', '/')) or '\\' in url or '?' in url:
        return {'ref': url, 'status': 'external-unverified'}
    parts = PurePosixPath(url).parts
    if not parts or any(part in ('', '.', '..') for part in parts):
        return {'ref': url, 'status': 'rejected'}
    current = html_path.parent
    for part in parts:
        current = current / part
        if current.is_symlink():
            return {'ref': url, 'status': 'rejected'}
    resolved = current.resolve()
    if not resolved.is_relative_to(root):
        return {'ref': url, 'status': 'rejected'}
    return {'ref': url, 'status': 'present' if current.is_file() else '404'}


def html_channel(path, root):
    text = path.read_text(encoding='utf-8')
    source = design_directions.Source(text)
    title_match = TITLE.search(text)
    title = re.sub(r'\s+', ' ', title_match.group(1)).strip() if title_match else ''
    visible = re.sub(r'\s+', ' ', ' '.join(source.text)).strip()
    assets = []
    for _tag, attrs in ASSET.findall(text):
        found = ATTR.search(attrs)
        if found:
            assets.append(_relative_asset(path, root, found.group(1)))
    layout = list(design_directions._layout_signature(text))
    for asset in assets:
        if asset['status'] == 'present' and asset['ref'].endswith('.css'):
            css_path = path.parent.joinpath(*PurePosixPath(asset['ref']).parts)
            layout.extend(design_directions._layout_signature('<style>' + css_path.read_text(encoding='utf-8') + '</style>'))
    facts = {}
    if title:
        facts['screen-title'] = title
    gaps = sorted({value for name, value in layout if name == 'gap'})
    if len(gaps) == 1:
        facts['surface-gap'] = gaps[0]
    elif len(gaps) > 1:
        raise ValueError('HTML fixture must declare one gap fact')
    return {
        'facts': facts,
        'title': title,
        'layout': layout,
        'assets': assets,
        'visible_sha256': digest(visible.encode()),
        'quarantine': _quarantine(text),
        'render': 'unverified',
    }


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
        channels['html'] = html_channel(path, root)
        sources.append({'path': inputs['html'], 'sha256': digest(path.read_bytes())})
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
    material = {'blocked': blocked, 'consumption': consumption, 'decisions': decisions}
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
        ],
    }


def freshness(record, root):
    if not isinstance(record, dict) or not isinstance(record.get('sources'), list):
        raise ValueError('Projection record has no source hashes')
    changed = []
    for item in record['sources']:
        current = digest(locate(root, item['path']).read_bytes())
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
