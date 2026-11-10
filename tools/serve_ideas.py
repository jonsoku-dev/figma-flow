#!/usr/bin/env python3
"""Serve one explicitly selected catalog draft with a single local build."""
import argparse
import contextlib
import io
import hashlib
import hmac
import json
import mimetypes
import os
import shlex
import stat
import tempfile
import re
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import idea_catalog
import check_project
from promote_idea import require_selection


def digest(data):
    return hashlib.sha256(data).hexdigest()


def trace_bytes(root, parts):
    # Open each component without following links, including the final file.
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(child).st_mode) or os.fstat(child).st_nlink != 1:
                raise ValueError('Trace must be a regular file')
            with os.fdopen(child, 'rb', closefd=False) as stream:
                return stream.read()
        finally:
            os.close(child)
    finally:
        os.close(fd)


def snapshot_app(out):
    files = {}
    total = 0
    root = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        app = os.open('app', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            def walk(fd, prefix=''):
                nonlocal total
                for name in os.listdir(fd):
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    relative = prefix + name
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            walk(child, relative + '/')
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                        try:
                            current = os.fstat(child)
                            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                                continue
                            with os.fdopen(child, 'rb', closefd=False) as stream:
                                content = stream.read(50_000_001)
                            total += len(content)
                            if total > 50_000_000 or len(files) >= 2000:
                                raise ValueError('Preview exceeds local snapshot limit')
                            files['/' + relative] = content
                        finally:
                            os.close(child)
            walk(app)
        finally:
            os.close(app)
    finally:
        os.close(root)
    if '/index.html' not in files:
        raise ValueError('Preview needs a regular app/index.html')
    return files


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.headers.get('Host') != self.server.host:
            self.send_error(403)
            return
        try:
            path = unquote(urlsplit(self.path).path, errors='strict')
        except ValueError:
            self.send_error(400)
            return
        if '\\' in path or '\x00' in path or any(part in ('.', '..') for part in path.split('/')):
            self.send_error(404)
            return
        if path == '/':
            path = '/index.html'
        data = self.server.files.get(path)
        if data is None:
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(data)


def start_preview(out, expected=None):
    files = snapshot_app(out)
    if expected is not None and (any(digest(data) not in expected.get(name, set()) for name, data in files.items()) or '/index.html' not in expected):
        raise ValueError('Reviewed app files are not fully pinned or have changed')
    server = ThreadingHTTPServer(('127.0.0.1', 0), PreviewHandler)
    server.daemon_threads = True
    server.files = files
    server.host = '127.0.0.1:' + str(server.server_port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def verify_reviewed(out, manifest_path, idea, catalog_hash, graph_hash, brief_hash):
    out = out.absolute()
    manifest_path = Path(manifest_path).absolute()
    if out.is_symlink() or manifest_path.parent != out / 'admission' or not re.fullmatch(r'manifest-[0-9]+\.json', manifest_path.name):
        raise ValueError('Reviewed manifest must be in this project’s admission directory')
    if any(path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1) for path in out.rglob('*')):
        raise ValueError('Reviewed project must not contain links')
    def read_json(path):
        return json.loads(check_project.ssot.read_local(path, capture=True)[1])
    request = read_json(out / 'promotion-request.json')
    receipt = read_json(out / 'logs/acceptance.json')
    status = read_json(out / 'promotion-status.json')
    if status.get('phase') != 'accepted' or request.get('idea') != idea or receipt.get('inputs') != request.get('inputs'):
        raise ValueError('Project has no matching accepted promotion receipt')
    for name, expected, file in [('catalog', catalog_hash, 'promotion-catalog.json'),
                                  ('draft', graph_hash, 'draft.json'), ('brief', brief_hash, 'brief.md')]:
        if request['inputs'][name]['sha256'] != expected or check_project.ssot.read_local(out / file)[0] != expected:
            raise ValueError('Reviewed project input differs from selected draft')
    for item in receipt['receipts']:
        if item.get('exit_code') != 0 or item.get('passed') is not True:
            raise ValueError('Reviewed test receipt did not pass')
        name = item['receipt']
        if Path(name).name != name or check_project.ssot.read_local(out / 'evidence/promotion-receipts' / name)[0] != item['receipt_sha256']:
            raise ValueError('Reviewed test receipt changed')
    if not receipt['receipts'] or receipt.get('admission') != 'admission/summary.json':
        raise ValueError('Reviewed receipt is incomplete')
    manifest = read_json(manifest_path)
    check_project.ssot.validate_manifest(manifest)
    base = read_json(out / 'admission/manifest-001.json')
    check_project.ssot.validate_manifest(base)
    if base.get('revision') != 1 or base.get('parent_sha256') is not None:
        raise ValueError('Invalid original admission baseline')
    if base['inputs']['graph']['sha256'] != receipt['artifacts']['graph.json'] or base['inputs']['bindings']['sha256'] != receipt['artifacts']['bindings.json']:
        raise ValueError('Original admission does not match acceptance receipt')
    chain = manifest
    while chain['revision'] > 1:
        parents = []
        for candidate in (out / 'admission').glob('manifest-*.json'):
            data = read_json(candidate)
            check_project.ssot.validate_manifest(data)
            if data.get('manifest_sha256') == chain.get('parent_sha256') and data.get('revision') == chain['revision'] - 1:
                parents.append(data)
        if len(parents) != 1:
            raise ValueError('Reviewed manifest lineage is incomplete or ambiguous')
        chain = parents[0]
    if chain['manifest_sha256'] != base['manifest_sha256']:
        raise ValueError('Reviewed manifest is from another acceptance lineage')
    if manifest.get('scope') != 'local-only':
        raise ValueError('Reviewed manifest must be local-only')
    for key, name in [('brief', 'brief.md'), ('graph', 'graph.json'), ('bindings', 'bindings.json')]:
        if (manifest_path.parent / manifest['inputs'][key]['path']).resolve() != (out / name).resolve():
            raise ValueError('Reviewed manifest belongs to another project')
    app_pins = {}
    def check_refs(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and value.get('availability') in ('local-hashed', 'missing'):
                target = (manifest_path.parent / value['path']).resolve()
                if not target.is_relative_to(out.resolve()):
                    raise ValueError('Reviewed manifest references another project')
                if value['availability'] == 'local-hashed' and target.is_relative_to((out / 'app').resolve()):
                    app_pins.setdefault('/' + target.relative_to((out / 'app').resolve()).as_posix(), set()).add(value['sha256'])
            for item in value.values():
                check_refs(item)
        elif isinstance(value, list):
            for item in value:
                check_refs(item)
    check_refs(manifest)
    for name, sha in receipt.get('app_sha256', {}).items():
        path = Path(name)
        if not path.is_absolute() and path.parts[:1] == ('app',) and '..' not in path.parts:
            app_pins.setdefault('/' + Path(*path.parts[1:]).as_posix(), set()).add(sha)
    graph = read_json(out / 'graph.json')
    draft = read_json(out / 'draft.json')
    actual = {n['id']: n['type'] for n in graph['nodes']}
    if any(actual.get(n['id']) != n['type'] for n in draft['nodes']) or {n['id'] for n in graph['nodes'] if n['type'] == 'screen'} != set(request['screen_ids']):
        raise ValueError('Reviewed graph no longer matches selected draft scope')
    edges = {(e['from'], e['to'], e['type']) for e in graph['edges']}
    if not {(e['from'], e['to'], e['type']) for e in draft['edges']} <= edges:
        raise ValueError('Reviewed graph no longer preserves selected draft links')
    bindings = read_json(out / 'bindings.json')
    references = [n.get('source') for n in graph['nodes']] + list(bindings.get('authorities', {}).values())
    references += [ref for refs in bindings.get('evidence', {}).values() for ref in refs]
    for ref in references:
        if not isinstance(ref, str) or not ref or urlsplit(ref).scheme or '#' in ref or not (out / ref).resolve().is_relative_to(out.resolve()):
            raise ValueError('Reviewed graph references outside the project')
    errors, _ = check_project.graph.validate_graph(graph, strict_local=True)
    if errors:
        raise ValueError('Reviewed graph fails strict local validation')
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = check_project.ssot.main(['check', str(manifest_path)])
    if result != 0:
        raise ValueError('Reviewed project is stale or unavailable')
    return app_pins


class IdeaServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, catalog, idea, graph, brief, out, open_reviewed=None, *, selection_path=None):
        catalog = Path(catalog).absolute()
        if catalog.is_dir():
            catalog = catalog / 'catalog.json'
        graph, brief, out = (Path(p).absolute() for p in (graph, brief, out))
        raw_catalog, raw_graph, raw_brief = (check_project.ssot.read_local(p, capture=True)[1] for p in (catalog, graph, brief))
        data = json.loads(raw_catalog)
        selected = [p for p in data['projects'] if p.get('label') == idea and p.get('status') == 'draft']
        if len(selected) != 1 or selected[0].get('graph_sha256') != digest(raw_graph):
            raise ValueError('Selected draft is missing or graph does not match the catalog')
        reviewed_pins = None
        if open_reviewed:
            reviewed_pins = verify_reviewed(out, open_reviewed, idea, digest(raw_catalog), digest(raw_graph), digest(raw_brief))
        elif out.exists() or out.is_symlink():
            raise ValueError('Output must be a new directory')
        self.selection_path = Path(selection_path).absolute() if selection_path else None
        self.graph_path = graph
        self.brief_path = brief
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.state = 'ready'
        self.message = '준비됨 · 앱 만들기를 누르면 생성이 시작됩니다.'
        self.out = out
        self.preview = None
        self.closed = False
        self.command = [sys.executable, str(Path(__file__).with_name('promote_idea.py')),
                        '--catalog', str(catalog), '--idea', idea, '--graph', str(graph),
                        '--brief', str(brief), '--out', str(out),
                        '--catalog-sha256', digest(raw_catalog), '--graph-sha256', digest(raw_graph),
                        '--brief-sha256', digest(raw_brief)]
        if self.selection_path:
            self.command += ['--selection', str(self.selection_path)]
        self.artifacts = {}
        root = catalog.parent.resolve()
        for item in data['projects']:
            trace = item.get('trace')
            if isinstance(trace, str) and re.fullmatch(r'projects/[0-9]{3}/trace\.html', trace):
                try:
                    self.artifacts['/' + trace] = trace_bytes(root, Path(trace).parts)
                except (OSError, ValueError):
                    item['trace'] = None
            else:
                item['trace'] = None
        self.page = idea_catalog.render(data, {'idea': idea, 'token': self.token, 'reviewed': bool(open_reviewed)}).encode()
        super().__init__(('127.0.0.1', 0), Handler)
        self.host = '127.0.0.1:' + str(self.server_port)
        self.origin = 'http://' + self.host
        if open_reviewed:
            try:
                self.preview = start_preview(out, reviewed_pins)
                self.state = 'succeeded'
                self.message = '검증된 기존 앱: ' + str(out)
            except Exception:
                super().server_close()
                raise

    def start_build(self):
        with self.lock:
            if self.state != 'ready':
                return False
            require_selection({'design_intent': 'create'}, self.graph_path, self.selection_path, self.brief_path)
            self.state = 'running'
            self.message = '생성 중입니다. 완료될 때까지 기다려 주세요.'
        threading.Thread(target=self.run_build, daemon=True).start()
        return True

    def current_status(self):
        with self.lock:
            state, message, preview = self.state, self.message, self.preview
        if state == 'running':
            try:
                raw = check_project.ssot.read_local(self.out / 'promotion-status.json', capture=True)[1]
                phase = json.loads(raw).get('phase')
                phases = {'prepared': '준비 완료', 'generating': '앱 생성 중', 'validating': '결과 검증 중',
                          'testing': '테스트 실행 중', 'admitting': '최종 검사 중',
                          'accepted': '완료 처리 중', 'partial-failed': '실패 처리 중'}
                if phase in phases:
                    message = phases[phase] + ' · ' + str(self.out)
            except (OSError, ValueError, UnicodeError, AttributeError):
                pass
        return {'state': state, 'message': message, 'preview_url': 'http://' + preview.host + '/' if state == 'succeeded' and preview else None}

    def run_build(self):
        try:
            require_selection({'design_intent': 'create'}, self.graph_path, self.selection_path, self.brief_path)
            with tempfile.TemporaryFile() as errors:
                result = subprocess.run(self.command, stdout=subprocess.DEVNULL, stderr=errors, check=False)
                errors.seek(0, os.SEEK_END)
                size = errors.tell()
                errors.seek(max(0, size - 1000))
                detail = errors.read().decode('utf-8', errors='replace')
            detail = ''.join(c if c.isprintable() else ' ' for c in detail).strip()[:1000]
            preview = None
            preview_error = None
            if result.returncode == 0:
                try:
                    preview = start_preview(self.out)
                except (OSError, ValueError) as exc:
                    preview_error = str(exc)
            with self.lock:
                closed = self.closed
                if result.returncode == 0:
                    self.preview = None if closed else preview
                    self.state = 'succeeded'
                    self.message = '생성 및 검사 완료: ' + str(self.out)
                    if preview_error:
                        command = 'python3 -m http.server --bind 127.0.0.1 --directory ' + shlex.quote(str(self.out / 'app')) + ' 8000'
                        self.message += ' · 미리보기 시작 실패: ' + preview_error + ' · 별도 터미널: ' + command
                else:
                    self.state = 'failed'
                    self.message = '생성 실패 (종료 코드 ' + str(result.returncode) + '). 출력 및 로그: ' + str(self.out) + (' · ' + detail if detail else '')
            if closed and preview:
                preview.shutdown()
                preview.server_close()
        except (OSError, ValueError) as exc:
            with self.lock:
                self.state, self.message = 'failed', '생성 실행 실패: ' + str(exc)

    def server_close(self):
        with self.lock:
            self.closed = True
            preview, self.preview = self.preview, None
        if preview:
            preview.shutdown()
            preview.server_close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_data(self, code, body, content_type, trace=False):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'" if trace else "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') == self.server.host

    def authorized(self):
        return hmac.compare_digest(self.headers.get('X-Build-Token', ''), self.server.token)

    def do_GET(self):
        if not self.valid_host():
            return self.send_data(403, b'Forbidden', 'text/plain')
        if self.path in ('/', '/index.html'):
            return self.send_data(200, self.server.page, 'text/html; charset=utf-8')
        if self.path == '/api/status' and self.authorized():
            body = json.dumps(self.server.current_status(), ensure_ascii=False).encode()
            return self.send_data(200, body, 'application/json; charset=utf-8')
        if self.path in self.server.artifacts:
            return self.send_data(200, self.server.artifacts[self.path], 'text/html; charset=utf-8', trace=True)
        return self.send_data(404, b'Not found', 'text/plain')

    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin') != self.server.origin
                or not self.authorized() or self.path != '/api/build'
                or self.headers.get('Content-Length', '0') != '0'
                or self.headers.get('Transfer-Encoding')):
            return self.send_data(403, b'Forbidden', 'text/plain')
        try:
            started = self.server.start_build()
        except ValueError as exc:
            return self.send_data(409, str(exc).encode('utf-8'), 'text/plain; charset=utf-8')
        if not started:
            return self.send_data(409, b'Already started', 'text/plain')
        return self.send_data(202, b'Accepted', 'text/plain')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('catalog', 'idea', 'graph', 'brief', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--open-reviewed', metavar='MANIFEST')
    parser.add_argument('--selection', type=Path)
    args = parser.parse_args()
    try:
        server = IdeaServer(args.catalog, args.idea, args.graph, args.brief, args.out, args.open_reviewed, selection_path=args.selection)
        print('Open: ' + server.origin + '/', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
