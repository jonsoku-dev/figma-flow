"""Verify and serve the owned production workspace fixture through its SHA-256 manifest.

Only regular, manifest-listed files whose bytes match the declared digest are read or served.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'skills/figma-flow/scripts'))
sys.path.insert(0, str(REPO / 'tools'))
from graph import validate_graph  # noqa: E402
import review_graph  # noqa: E402

DEFAULT_ROOT = REPO / 'examples/owned-production-workspace'
SCHEMA = 'figma-flow-owned-production-workspace-manifest-v1'
RECEIPT_SCHEMA = 'figma-flow-owned-production-workspace-receipt-v1'
MANIFEST = 'manifest.json'
MAX_BYTES = 2 * 1024 * 1024
LAYERS = {'reference-input', 'owned-public-baseline', 'generated-private-output'}
PUBLIC_RETENTION = 'repository-history'
PRIVATE_RETENTION = 'private-evidence-untracked'
MEDIA_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json',
    '.svg': 'image/svg+xml',
    '.md': 'text/markdown; charset=utf-8',
}
IGNORED_NAMES = {'.DS_Store', '__pycache__'}
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
HEX_COLOR = re.compile(r'#[0-9a-f]{6}\Z')
AUTHORITY = re.compile(r'(?<![/\\])//(?=[^\s\\])')
SCHEME_BEFORE = re.compile(r'([A-Za-z][A-Za-z0-9+.-]*):\Z')
URL_END = re.compile(r'[\s"\'<>()`\\]')
SVG_NAMESPACE = 'http://www.w3.org/2000/svg'
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost'}
NETWORK_FETCH = re.compile(r'(?i)(?:src|href|action)\s*=\s*["\']?//|url\(|@import|@font-face')
SENSITIVE = {
    'email address': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+'),
    'personal home path': re.compile(r'(?i)/Users/|/home/|\b[a-z]:\\users\\'),
    'credential marker': re.compile(r'(?i)\bbearer\s+[a-z0-9._-]{8}|\bapi[_-]?key\b|\baccess[_-]?token\b|\bsession[_-]?id\b|\bpassword\s*[:=]'),
    'Figma file reference': re.compile(r'(?i)figma\.com/(?:file|design|proto)/'),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class WorkspaceError(Exception):
    def __init__(self, problems, status=400):
        self.problems = list(problems)
        self.status = status
        super().__init__('; '.join(self.problems))


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def path_problem(rel):
    if not isinstance(rel, str) or not rel:
        return 'path must be a nonempty string'
    if '\x00' in rel or '\\' in rel:
        return f'path contains NUL or backslash: {rel!r}'
    if rel.startswith('/') or re.match(r'[A-Za-z]:', rel):
        return f'absolute path: {rel!r}'
    parts = rel.split('/')
    if any(part in ('', '.', '..') for part in parts) or PurePosixPath(rel).as_posix() != rel:
        return f'path escapes or is not normalized: {rel!r}'
    return None


def read_approved(root, rel, expected_sha256):
    """Open one manifest path with the lstat, containment, and digest checks applied at the read itself."""
    problem = path_problem(rel)
    if problem:
        raise WorkspaceError([problem], 404)
    root = Path(root)
    current = root
    for part in rel.split('/'):
        current = current / part
        if current.is_symlink():
            raise WorkspaceError([f'symlink rejected: {rel}'], 403)
    try:
        before = os.lstat(current)
    except FileNotFoundError:
        raise WorkspaceError([f'approved file missing: {rel}'], 404) from None
    if not stat.S_ISREG(before.st_mode):
        raise WorkspaceError([f'not a regular file: {rel}'], 403)
    if not current.resolve().is_relative_to(root.resolve()):
        raise WorkspaceError([f'path resolves outside the fixture: {rel}'], 403)
    fd = os.open(current, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise WorkspaceError([f'file changed while opening: {rel}'], 409)
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise WorkspaceError([f'file exceeds {MAX_BYTES} bytes: {rel}'], 413)
    actual = sha256_hex(data)
    if actual != expected_sha256:
        raise WorkspaceError([f'digest drift for {rel}: manifest {expected_sha256}, actual {actual}'], 409)
    return data


def _read_manifest(root):
    path = Path(root) / MANIFEST
    if path.is_symlink() or not path.is_file():
        raise WorkspaceError([f'{MANIFEST} must be a regular file in the fixture'])
    raw = path.read_bytes()
    try:
        return raw, json.loads(raw)
    except json.JSONDecodeError as error:
        raise WorkspaceError([f'{MANIFEST} is not JSON: {error}']) from None


def approved_entries(manifest):
    """Return path -> entry for well-formed public file declarations and the problems found."""
    problems = []
    entries = {}
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        return {}, ['manifest files must be a nonempty list']
    for index, entry in enumerate(files):
        where = f'files[{index}]'
        if not isinstance(entry, dict):
            problems.append(f'{where} must be an object')
            continue
        rel = entry.get('path')
        problem = path_problem(rel)
        if problem:
            problems.append(f'{where}: {problem}')
            continue
        if rel == MANIFEST or rel in entries:
            problems.append(f'{where}: duplicate or self-referencing path {rel}')
            continue
        expected = {
            'layer': 'owned-public-baseline', 'sharing_scope': 'public', 'retention': PUBLIC_RETENTION,
            'ownership': 'repo-authored', 'license': 'MIT',
        }
        for key, value in expected.items():
            if entry.get(key) != value:
                problems.append(f'{where}.{key} must be {value!r} for {rel}')
        if not isinstance(entry.get('role'), str) or not entry['role']:
            problems.append(f'{where}.role is required for {rel}')
        if not isinstance(entry.get('sha256'), str) or not SHA256.match(entry['sha256']):
            problems.append(f'{where}.sha256 must be 64 lowercase hex characters for {rel}')
        if type(entry.get('serve')) is not bool:
            problems.append(f'{where}.serve must be a boolean for {rel}')
        if entry.get('media_type') != MEDIA_TYPES.get(PurePosixPath(rel).suffix):
            problems.append(f'{where}.media_type does not match the allowed type for {rel}')
        entries[rel] = entry
    return entries, problems


def _manifest_problems(manifest):
    problems = []
    if manifest.get('schema') != SCHEMA:
        problems.append(f'manifest schema must be {SCHEMA}')
    ownership = manifest.get('ownership') or {}
    if ownership.get('license') != 'MIT' or ownership.get('license_path') != '../../LICENSE':
        problems.append('ownership must declare the repository MIT LICENSE')
    if ownership.get('authored_in_repo') is not True:
        problems.append('ownership.authored_in_repo must be true')
    for key in ('third_party_sources', 'third_party_licenses_claimed'):
        if ownership.get(key) != []:
            problems.append(f'ownership.{key} must be empty')
    for key in ('external_media_assets', 'external_font_requests', 'external_network_requests'):
        if ownership.get(key) != 0:
            problems.append(f'ownership.{key} must be 0')
    if set(manifest.get('artifact_layers') or {}) != LAYERS:
        problems.append(f'artifact_layers must be exactly {sorted(LAYERS)}')
    outputs = manifest.get('private_generated_outputs')
    if not isinstance(outputs, list) or not outputs:
        problems.append('private_generated_outputs must list the untracked runtime outputs')
    for index, entry in enumerate(outputs or []):
        if (entry.get('layer'), entry.get('sharing_scope'), entry.get('retention'), entry.get('git_tracked')) != (
                'generated-private-output', 'private', PRIVATE_RETENTION, False):
            problems.append(f'private_generated_outputs[{index}] must be private, untracked, and {PRIVATE_RETENTION}')
    return problems


def _undeclared(root, entries):
    problems = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        for name in sorted(dirnames + filenames):
            if name in IGNORED_NAMES:
                continue
            path = here / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                problems.append(f'symlink rejected: {rel}')
            elif path.is_file() and rel != MANIFEST and rel not in entries:
                problems.append(f'undeclared file: {rel}')
        dirnames[:] = [name for name in dirnames if name not in IGNORED_NAMES and not (here / name).is_symlink()]
    return problems


def _strip_js_comments(text):
    """Blank out JavaScript comments while keeping string and template literal text."""
    out = []
    index, size, quote = 0, len(text), None
    while index < size:
        char = text[index]
        if quote:
            step = 2 if char == '\\' else 1
            out.append(text[index:index + step])
            if char == quote:
                quote = None
            index += step
        elif char in '\'"`':
            quote = char
            out.append(char)
            index += 1
        elif text.startswith('//', index) or text.startswith('/*', index):
            close = text.find('\n', index) if text[index + 1] == '/' else text.find('*/', index + 2)
            stop = size if close < 0 else (close if text[index + 1] == '/' else close + 2)
            out.append(' ' * (stop - index))
            index = stop
        else:
            out.append(char)
            index += 1
    return ''.join(out)


def _allowed_authority(url, scheme):
    if scheme is not None and url == SVG_NAMESPACE:
        return True
    if scheme is not None and scheme.lower() not in ('http', 'https'):
        return False
    try:
        parts = urlsplit(url if scheme is not None else 'http:' + url)
        parts.port
    except ValueError:
        return False
    return parts.username is None and parts.password is None and parts.hostname in LOOPBACK_HOSTS


def external_urls(view, *, scheme_relative=True):
    """Return every // authority in the text that is not the SVG namespace or explicit loopback."""
    found = []
    for match in AUTHORITY.finditer(view):
        start = match.start()
        before = SCHEME_BEFORE.search(view[max(0, start - 32):start])
        scheme = before.group(1) if before else None
        if scheme is None and not scheme_relative:
            continue
        stop = URL_END.search(view, start)
        token = view[start:stop.start() if stop else len(view)]
        if scheme is None and token == '//':
            continue
        url = f'{scheme}:{token}' if scheme is not None else token
        if not _allowed_authority(url, scheme):
            found.append(url)
    return found


def scan_text(rel, text):
    views = [(text, not rel.endswith('.js'))]
    if rel.endswith('.js'):
        views.append((_strip_js_comments(text), True))
    if rel.endswith('.json'):
        try:
            views.append((json.dumps(json.loads(text), ensure_ascii=False), True))
        except json.JSONDecodeError:
            pass
    problems = []
    for view, scheme_relative in views:
        for url in external_urls(view, scheme_relative=scheme_relative):
            problems.append(f'external URL in {rel}: {url}')
        if NETWORK_FETCH.search(view):
            problems.append(f'network fetch syntax in {rel}')
        for label, pattern in SENSITIVE.items():
            if pattern.search(view):
                problems.append(f'{label} in {rel}')
    return list(dict.fromkeys(problems))


def _graph_problems(graph, entries):
    errors, _ = validate_graph(graph)
    problems = [f'graph: {error}' for error in errors]
    if problems:
        return problems
    allowed_sources = set(entries) | {MANIFEST}
    by_id = {node['id']: node for node in graph['nodes']}
    for node in graph['nodes']:
        if node.get('layer') not in LAYERS:
            problems.append(f'graph node {node["id"]} has no declared layer')
        if node.get('layer') == 'generated-private-output' and (node['type'], node['status']) != ('figma', 'planned'):
            problems.append(f'graph node {node["id"]} in the private layer must be a planned figma node')
        source = node.get('source')
        if source is not None and source.split('#', 1)[0] not in allowed_sources:
            problems.append(f'graph node {node["id"]} source is not a manifest path: {source}')
    for screen in (node for node in graph['nodes'] if node['type'] == 'screen'):
        states = [by_id[edge['to']] for edge in graph['edges'] if edge['from'] == screen['id'] and edge['type'] == 'has state']
        if sum(1 for state in states if state.get('initial') is True) != 1:
            problems.append(f'screen {screen["id"]} needs exactly one initial state')
        routes = [state.get('route') for state in states]
        if len(set(routes)) != len(routes) or not all(isinstance(route, str) and route for route in routes):
            problems.append(f'screen {screen["id"]} state routes must be unique nonempty strings')
    workspace = graph.get('workspace') or {}
    media = [item.get('asset') for item in workspace.get('evidence', [])] + [(workspace.get('empty_media') or {}).get('asset')]
    for asset in media:
        entry = entries.get(asset)
        if not entry or entry.get('role') != 'media' or entry.get('serve') is not True:
            problems.append(f'graph media is not an approved served manifest asset: {asset}')
    for name, value in (workspace.get('tokens') or {}).items():
        if name != 'font-sans' and not (isinstance(value, str) and HEX_COLOR.match(value)):
            problems.append(f'token {name} must be a lowercase sRGB hex color')
    return problems


def review_selection(graph):
    return [node['id'] for node in graph['nodes'] if node['type'] in ('requirement', 'screen', 'state')]


def verify(root=DEFAULT_ROOT):
    """Check the fixture and return a receipt with input and output digests, or raise WorkspaceError."""
    return _verified_snapshot(root)[0]


def _verified_snapshot(root):
    """Return the receipt and the exact approved entries parsed from the one manifest read that was verified."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise WorkspaceError([f'fixture root must be a real directory: {root.name}'])
    manifest_raw, manifest = _read_manifest(root)
    entries, problems = approved_entries(manifest)
    problems += _manifest_problems(manifest)
    problems += scan_text(MANIFEST, manifest_raw.decode('utf-8'))
    problems += _undeclared(root, entries)
    contents = {}
    for rel, entry in entries.items():
        try:
            contents[rel] = read_approved(root, rel, entry.get('sha256'))
        except WorkspaceError as error:
            problems += error.problems
            continue
        try:
            problems += scan_text(rel, contents[rel].decode('utf-8'))
        except UnicodeDecodeError:
            problems.append(f'approved file is not UTF-8 text: {rel}')
    graph_rel = manifest.get('canonical_graph')
    if graph_rel not in contents:
        problems.append(f'canonical graph {graph_rel!r} is not an approved readable file')
        raise WorkspaceError(problems)
    try:
        graph = json.loads(contents[graph_rel])
    except json.JSONDecodeError as error:
        raise WorkspaceError(problems + [f'canonical graph is not JSON: {error}']) from None
    if graph.get('id') != manifest.get('id'):
        problems.append('manifest id must equal the graph id')
    problems += _graph_problems(graph, entries)
    if problems:
        raise WorkspaceError(problems)

    selection = review_selection(graph)
    projected, projected_source_sha = review_graph.project_graph(root / graph_rel, selection)
    graph_sha = sha256_hex(contents[graph_rel])
    if projected_source_sha != graph_sha:
        raise WorkspaceError(['graph changed between the approved read and the review projection'], 409)
    by_id = {node['id']: node for node in graph['nodes']}
    screens = []
    for node in graph['nodes']:
        if node['type'] != 'screen':
            continue
        states = [by_id[edge['to']] for edge in graph['edges'] if edge['from'] == node['id'] and edge['type'] == 'has state']
        screens.append({'id': node['id'], 'route': node['route'],
                        'states': [{'id': state['id'], 'route': state['route'], 'initial': state['initial']} for state in states]})
    receipt = {
        'schema': RECEIPT_SCHEMA,
        'workspace': manifest['id'],
        'inputs': {
            'manifest_sha256': sha256_hex(manifest_raw),
            'files': [{'path': rel, 'sha256': entries[rel]['sha256'], 'bytes': len(contents[rel]),
                       'serve': entries[rel]['serve']} for rel in sorted(entries)],
        },
        'screens': screens,
        'viewports': graph['workspace']['viewports'],
        'outputs': {
            'review_projection': {
                'source_graph_sha256': projected_source_sha,
                'node_ids': selection,
                'edge_count': len(projected['edges']),
                'selection_sha256': review_graph.selection_sha256(projected),
            },
        },
    }
    return receipt, entries


def _outside(root, path):
    return not Path(path).resolve().is_relative_to(Path(root).resolve())


def write_new(root, path, text):
    if not _outside(root, path):
        raise WorkspaceError([f'refusing to write private output inside the public fixture: {path}'])
    with open(path, 'x', encoding='utf-8') as handle:
        handle.write(text)


def make_handler(root, entries, access_log=None):
    served = {rel: entry for rel, entry in entries.items() if entry['serve']}

    class Handler(BaseHTTPRequestHandler):
        server_version = 'owned-production-workspace'
        sys_version = ''

        def _respond(self, head_only):
            raw = urlsplit(self.path).path
            rel = unquote(raw)[1:] if raw.startswith('/') else None
            if rel == '':
                rel = 'index.html'
            status, body, entry = 404, b'not an approved fixture file\n', None
            if rel is not None and path_problem(rel) is None and rel in served:
                entry = served[rel]
                try:
                    body, status = read_approved(root, rel, entry['sha256']), 200
                except WorkspaceError as error:
                    status, body = error.status, (error.problems[0] + '\n').encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', entry['media_type'] if status == 200 else 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Security-Policy', CSP)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            if access_log is not None:
                record = {'path': rel if rel is not None else raw, 'status': status,
                          'sha256': sha256_hex(body) if status == 200 else None}
                with open(access_log, 'a', encoding='utf-8') as handle:
                    handle.write(json.dumps(record, sort_keys=True) + '\n')

        def do_GET(self):
            self._respond(False)

        def do_HEAD(self):
            self._respond(True)

        def log_message(self, fmt, *args):
            sys.stderr.write('owned-production-workspace: ' + (fmt % args) + '\n')

    return Handler


def make_server(root=DEFAULT_ROOT, host='127.0.0.1', port=8893, access_log=None):
    if host not in ('127.0.0.1', 'localhost'):
        raise WorkspaceError(['serve binds to loopback only (127.0.0.1 or localhost)'])
    if access_log is not None and not _outside(root, access_log):
        raise WorkspaceError(['the access log must be written outside the public fixture'])
    receipt, entries = _verified_snapshot(root)
    return ThreadingHTTPServer((host, port), make_handler(Path(root), entries, access_log)), receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('verify', help='Check the manifest allowlist, digests, text policy, and graph.')
    check.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    check.add_argument('--receipt', type=Path, help='New private receipt path outside the fixture.')
    serve = commands.add_parser('serve', help='Serve approved files on loopback after verify passes.')
    serve.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8893)
    serve.add_argument('--access-log', type=Path, help='Private JSONL of served paths, statuses, and digests.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            receipt = verify(args.root)
            text = json.dumps(receipt, indent=2, sort_keys=True) + '\n'
            if args.receipt:
                write_new(args.root, args.receipt, text)
            print(json.dumps({'status': 'ok', 'files': len(receipt['inputs']['files']),
                              'manifest_sha256': receipt['inputs']['manifest_sha256'],
                              'selection_sha256': receipt['outputs']['review_projection']['selection_sha256'],
                              'receipt_sha256': sha256_hex(text.encode('utf-8'))}))
            return 0
        server, receipt = make_server(args.root, args.host, args.port, args.access_log)
        host, port = server.server_address[:2]
        print(f'Serving {len(receipt["inputs"]["files"])} approved files at http://{host}:{port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except WorkspaceError as error:
        for problem in error.problems:
            print(f'owned-production-workspace: {problem}', file=sys.stderr)
        return 1
    except OSError as error:
        print(f'owned-production-workspace: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
